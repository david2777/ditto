"""Shared pytest fixtures for Ditto tests."""

import pytest

from sqlalchemy.orm import sessionmaker

from ditto.database import QuoteManager


SAMPLE_QUOTE_DATA = [
    {
        "id": f"quote-{i}",
        "db_id": f"quote-{i}",
        "content": f"Test quote content {i}",
        "title": f"Title {i}",
        "author": f"Author {i}",
        "image_url": None,
        "image_expiry": None,
    }
    for i in range(5)
]


@pytest.fixture
def quote_manager():
    """Create a QuoteManager backed by an in-memory SQLite database."""
    qm = QuoteManager(db_url="sqlite:///:memory:")
    # Allow attribute access on detached instances returned by manager methods
    qm.Session = sessionmaker(bind=qm.engine, expire_on_commit=False)
    yield qm
    qm.engine.dispose()


@pytest.fixture
def sample_quotes(quote_manager):
    """Insert 5 sample quotes and return the list of dicts."""
    for q in SAMPLE_QUOTE_DATA:
        quote_manager.upsert_quote(q)
    return list(SAMPLE_QUOTE_DATA)
