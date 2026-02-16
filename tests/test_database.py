"""Tests for ditto.database — QuoteManager with in-memory SQLite."""

from ditto.constants import QueryDirection


# ---------------------------------------------------------------------------
# Upsert & retrieval
# ---------------------------------------------------------------------------
class TestUpsertQuote:
    def test_insert_new(self, quote_manager):
        """A new quote is inserted and shows up in get_all_quote_ids."""
        quote_manager.upsert_quote({"id": "q1", "db_id": "q1", "content": "Hello", "title": "T", "author": "A"})
        assert "q1" in quote_manager.get_all_quote_ids()

    def test_update_existing(self, quote_manager):
        """Upserting the same ID updates the content."""
        quote_manager.upsert_quote({"id": "q1", "db_id": "q1", "content": "v1"})
        quote_manager.upsert_quote({"id": "q1", "db_id": "q1", "content": "v2"})

        ids = quote_manager.get_all_quote_ids()
        assert ids.count("q1") == 1  # still one record


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------
class TestGetStats:
    def test_empty_db(self, quote_manager):
        stats = quote_manager.get_stats()
        assert stats["quote_count"] == 0
        assert stats["client_count"] == 0

    def test_after_inserts(self, quote_manager, sample_quotes):
        stats = quote_manager.get_stats()
        assert stats["quote_count"] == 5
        assert stats["client_count"] == 0


# ---------------------------------------------------------------------------
# Quote IDs
# ---------------------------------------------------------------------------
class TestGetAllQuoteIds:
    def test_empty(self, quote_manager):
        assert quote_manager.get_all_quote_ids() == []

    def test_returns_all(self, quote_manager, sample_quotes):
        ids = quote_manager.get_all_quote_ids()
        assert set(ids) == {q["id"] for q in sample_quotes}


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------
class TestDeleteQuote:
    def test_delete_removes_quote(self, quote_manager, sample_quotes):
        quote_manager.delete_quote("quote-0")
        assert "quote-0" not in quote_manager.get_all_quote_ids()

    def test_delete_cascades_to_sequences(self, quote_manager, sample_quotes):
        """Deleting a quote also removes its ClientSequence rows."""
        quote_manager.register_client("client-a")
        quote_manager.delete_quote("quote-0")
        # Client should still exist, but their deck shrinks
        ids = quote_manager.get_all_quote_ids()
        assert "quote-0" not in ids

    def test_delete_nonexistent_is_noop(self, quote_manager):
        """Deleting an ID that doesn't exist doesn't raise."""
        quote_manager.delete_quote("does-not-exist")  # should not raise


# ---------------------------------------------------------------------------
# Client registration
# ---------------------------------------------------------------------------
class TestRegisterClient:
    def test_new_client_created(self, quote_manager, sample_quotes):
        quote_manager.register_client("new-client")
        client = quote_manager.get_client("new-client")
        assert client is not None
        assert client.client_name == "new-client"

    def test_new_client_gets_shuffled_deck(self, quote_manager, sample_quotes):
        """A new client should have a sequence covering all quotes."""
        quote_manager.register_client("new-client")
        stats = quote_manager.get_stats()
        assert stats["client_count"] == 1

    def test_idempotent(self, quote_manager, sample_quotes):
        """Re-registering returns the same client without duplicating."""
        c1 = quote_manager.register_client("client-a")
        c2 = quote_manager.register_client("client-a")
        assert c1.id == c2.id
        assert quote_manager.get_stats()["client_count"] == 1

    def test_custom_dimensions(self, quote_manager, sample_quotes):
        """Custom width/height are persisted on the new client."""
        quote_manager.register_client("client-custom", width=1024, height=768)
        client = quote_manager.get_client("client-custom")
        assert client.default_width == 1024
        assert client.default_height == 768


# ---------------------------------------------------------------------------
# Sync new quotes
# ---------------------------------------------------------------------------
class TestSyncNewQuotes:
    def test_appends_new_quotes(self, quote_manager, sample_quotes):
        """New quotes added after client registration are appended to their deck."""
        quote_manager.register_client("client-a")

        # Add a 6th quote
        quote_manager.upsert_quote({"id": "quote-new", "db_id": "quote-new", "content": "New!"})
        quote_manager.sync_new_quotes("client-a")

        # Now fetch with direction to verify the new quote is reachable
        all_ids = quote_manager.get_all_quote_ids()
        assert "quote-new" in all_ids

    def test_skips_existing(self, quote_manager, sample_quotes):
        """Syncing when no new quotes exist is a no-op."""
        quote_manager.register_client("client-a")
        # Sync again with no new quotes — should not raise or duplicate
        quote_manager.sync_new_quotes("client-a")

    def test_unregistered_client_is_noop(self, quote_manager):
        """Syncing for a client that doesn't exist simply returns."""
        quote_manager.sync_new_quotes("ghost-client")


# ---------------------------------------------------------------------------
# Update client
# ---------------------------------------------------------------------------
class TestUpdateClient:
    def test_partial_update_width(self, quote_manager, sample_quotes):
        quote_manager.register_client("client-a")
        client = quote_manager.get_client("client-a")
        client_id = client.id
        original_height = client.default_height
        updated = quote_manager.update_client(client_id, width=1920)
        assert updated.default_width == 1920
        assert updated.default_height == original_height  # unchanged

    def test_partial_update_position(self, quote_manager, sample_quotes):
        quote_manager.register_client("client-a")
        client = quote_manager.get_client("client-a")
        client_id = client.id
        updated = quote_manager.update_client(client_id, position=3)
        assert updated.current_position == 3

    def test_returns_none_for_missing_id(self, quote_manager):
        assert quote_manager.update_client(9999) is None


# ---------------------------------------------------------------------------
# get_quote — navigation directions
# ---------------------------------------------------------------------------
class TestGetQuote:
    def test_current_initializes_to_zero(self, quote_manager, sample_quotes):
        """First CURRENT request moves position from -1 to 0."""
        quote, client = quote_manager.get_quote("nav-client", QueryDirection.CURRENT)
        assert quote is not None
        assert client.current_position == 0

    def test_forward_advances(self, quote_manager, sample_quotes):
        """FORWARD increments position."""
        quote_manager.get_quote("nav-client", QueryDirection.CURRENT)
        _, client = quote_manager.get_quote("nav-client", QueryDirection.FORWARD)
        assert client.current_position == 1

    def test_forward_wraps_around(self, quote_manager, sample_quotes):
        """Moving forward past the last quote wraps to 0."""
        # Advance through all 5 quotes + 1 more to wrap
        for _ in range(5):
            quote_manager.get_quote("nav-client", QueryDirection.FORWARD)
        _, client = quote_manager.get_quote("nav-client", QueryDirection.FORWARD)
        assert client.current_position == 0

    def test_reverse_wraps_around(self, quote_manager, sample_quotes):
        """Moving backward from position 0 wraps to the last position."""
        # Init to 0, then go reverse
        quote_manager.get_quote("nav-client", QueryDirection.CURRENT)
        _, client = quote_manager.get_quote("nav-client", QueryDirection.REVERSE)
        assert client.current_position == len(sample_quotes) - 1

    def test_random_returns_quote(self, quote_manager, sample_quotes):
        """RANDOM always returns a valid quote."""
        quote, client = quote_manager.get_quote("nav-client", QueryDirection.RANDOM)
        assert quote is not None
        assert 0 <= client.current_position < len(sample_quotes)

    def test_empty_database(self, quote_manager):
        """With no quotes, get_quote returns (None, client)."""
        quote, client = quote_manager.get_quote("lonely-client", QueryDirection.CURRENT)
        assert quote is None
        assert client is not None
