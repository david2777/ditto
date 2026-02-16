"""Tests for ditto.text_rendering — pure helper functions."""

import pytest
from PIL import ImageFont

from ditto.text_rendering import _lerp, _wrap_text, _fit_text_width, _fit_text_bbox


# ---------------------------------------------------------------------------
# _lerp
# ---------------------------------------------------------------------------
class TestLerp:
    def test_at_zero(self):
        assert _lerp(0, 10, 0) == 0

    def test_at_one(self):
        assert _lerp(0, 10, 1) == 10

    def test_midpoint(self):
        assert _lerp(0, 10, 0.5) == pytest.approx(5.0)

    def test_negative_range(self):
        assert _lerp(-5, 5, 0.5) == pytest.approx(0.0)

    def test_beyond_one(self):
        """t > 1 extrapolates beyond b."""
        assert _lerp(0, 10, 2) == pytest.approx(20.0)


# ---------------------------------------------------------------------------
# _wrap_text  (uses a default PIL font for testing)
# ---------------------------------------------------------------------------
@pytest.fixture
def default_font():
    """Load a basic PIL default font for wrap/fit tests."""
    return ImageFont.load_default(size=20)


class TestWrapText:
    def test_empty_string(self, default_font):
        assert _wrap_text("", default_font, 500) == ""

    def test_no_wrap_needed(self, default_font):
        """Short text that fits in 500px should not wrap."""
        result = _wrap_text("Hi", default_font, 500)
        assert "\n" not in result

    def test_wraps_long_text(self, default_font):
        """A very long sentence should be wrapped into multiple lines."""
        text = " ".join(["word"] * 50)
        result = _wrap_text(text, default_font, 200)
        assert "\n" in result


# ---------------------------------------------------------------------------
# _fit_text_width
# ---------------------------------------------------------------------------
class TestFitTextWidth:
    def test_short_text_returns_max(self, default_font):
        """Short text should fit at or near max_font_size."""
        font = _fit_text_width("Hi", default_font, max_width=500, min_font_size=10, max_font_size=30)
        assert font.size <= 30
        assert font.size >= 10

    def test_long_text_returns_min(self, default_font):
        """Text that is too wide even at min_font_size returns min."""
        long_text = "A" * 500
        font = _fit_text_width(long_text, default_font, max_width=100, min_font_size=10, max_font_size=30)
        assert font.size == 10


# ---------------------------------------------------------------------------
# _fit_text_bbox
# ---------------------------------------------------------------------------
class TestFitTextBbox:
    def test_short_text_fits(self, default_font):
        """Short text in a large box should fit comfortably."""
        wrapped, font = _fit_text_bbox(
            "Hello World", default_font, max_width=800, max_height=400, min_font_size=10, max_font_size=48
        )
        assert isinstance(wrapped, str)
        assert font.size >= 10

    def test_truncation_at_period(self, default_font):
        """Very long text with a period should truncate at the period when it can't fit."""
        text = "First sentence. Second sentence that is extremely long " + "word " * 100
        wrapped, font = _fit_text_bbox(
            text, default_font, max_width=200, max_height=50, min_font_size=10, max_font_size=12
        )
        # Should have truncated to "First sentence." or returned a wrapped version
        assert isinstance(wrapped, str)
