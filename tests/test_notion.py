"""Tests for ditto.notion — NotionPage parsing logic."""

from datetime import datetime
from ditto.notion import NotionPage


def _make_page(
    page_id="page-1",
    name_parts=None,
    title=None,
    author=None,
    archived=False,
    in_trash=False,
):
    """Build a minimal Notion page dict for testing."""
    properties = {}

    # Name (quote text)
    if name_parts is None:
        name_parts = [{"plain_text": "To be or not to be."}]
    properties["Name"] = {"title": name_parts}

    # TITLE
    if title is not None:
        properties["TITLE"] = {"rich_text": [{"plain_text": title}]}
    else:
        properties["TITLE"] = {"rich_text": []}

    # AUTHOR
    if author is not None:
        properties["AUTHOR"] = {"rich_text": [{"plain_text": author}]}
    else:
        properties["AUTHOR"] = {"rich_text": []}

    return {
        "id": page_id,
        "archived": archived,
        "in_trash": in_trash,
        "properties": properties,
    }


def _file_image_block(url="https://example.com/img.jpg", expiry="2026-12-31T00:00:00.000Z"):
    """Build a Notion file-type image block."""
    return {
        "type": "file",
        "file": {"url": url, "expiry_time": expiry},
    }


def _external_image_block(url="https://cdn.example.com/img.jpg"):
    """Build a Notion external-type image block."""
    return {
        "type": "external",
        "external": {"url": url},
    }


class TestNotionPage:
    def test_full_page_with_file_image(self):
        """All fields extracted from a complete page with a file-hosted image."""
        page = _make_page(page_id="abc-123", title="Hamlet", author="Shakespeare")
        image = _file_image_block()

        np = NotionPage(page, image)

        assert np.page_id == "abc-123"
        assert np.quote == "To be or not to be."
        assert np.title == "Hamlet"
        assert np.author == "Shakespeare"
        assert np.image_url == "https://example.com/img.jpg"
        assert isinstance(np.image_expiry_time, datetime)

    def test_external_image(self):
        """External image URL stored, expiry is None."""
        page = _make_page()
        image = _external_image_block(url="https://cdn.example.com/photo.png")

        np = NotionPage(page, image)

        assert np.image_url == "https://cdn.example.com/photo.png"
        assert np.image_expiry_time is None

    def test_no_image_block(self):
        """image_url and image_expiry_time are None when no image block is provided."""
        np = NotionPage(_make_page())

        assert np.image_url is None
        assert np.image_expiry_time is None

    def test_missing_title_and_author(self):
        """Title and author default to 'Unknown' when the rich_text arrays are empty."""
        page = _make_page(title=None, author=None)

        np = NotionPage(page)

        assert np.title == "Unknown"
        assert np.author == "Unknown"

    def test_empty_name_parts(self):
        """Empty name parts list produces an empty quote string."""
        page = _make_page(name_parts=[])

        np = NotionPage(page)

        assert np.quote == ""

    def test_multi_part_name(self):
        """Multiple plain_text parts are concatenated."""
        parts = [{"plain_text": "Hello, "}, {"plain_text": "World!"}]
        page = _make_page(name_parts=parts)

        np = NotionPage(page)

        assert np.quote == "Hello, World!"

    def test_repr(self):
        """__repr__ returns a readable identifier."""
        np = NotionPage(_make_page(page_id="xyz"))
        assert repr(np) == "NotionPage[xyz]"
