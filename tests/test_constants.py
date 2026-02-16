"""Tests for ditto.constants — QueryDirection enum."""

import pytest
from unittest.mock import MagicMock
from ditto.constants import QueryDirection


def _make_request(path: str) -> MagicMock:
    """Create a mock Request with the given URL path."""
    req = MagicMock()
    req.url.path = path
    return req


@pytest.mark.parametrize(
    "path, expected",
    [
        ("/current", QueryDirection.CURRENT),
        ("/next", QueryDirection.FORWARD),
        ("/previous", QueryDirection.REVERSE),
        ("/random", QueryDirection.RANDOM),
    ],
)
def test_from_request_valid_paths(path, expected):
    """Each known path maps to the correct QueryDirection member."""
    assert QueryDirection.from_request(_make_request(path)) == expected


@pytest.mark.parametrize("path", ["/unknown", "/", "/quotes", ""])
def test_from_request_unknown_path(path):
    """Unknown paths return None."""
    assert QueryDirection.from_request(_make_request(path)) is None
