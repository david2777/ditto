from math import ceil
from typing import Optional, Tuple

import numpy as np
from loguru import logger
from PIL import Image, ImageDraw, ImageFont
from PIL.ImageFont import FreeTypeFont

from ditto.constants import *
from ditto.utilities.timer import Timer


def render_text(dimensions: tuple[int, int], quote: str, title: str, author: str) -> np.ndarray:
    """Renders a text-based image with a quote, title, and author overlaid on it. The function calculates dimensions
    and positions for each text component, applies styling parameters based on preset configurations, and uses
    Pillow for drawing text. The resulting image is returned as a numpy array.

    Args:
        dimensions: A tuple indicating the width and height of the image in pixels.
        quote: A string containing the main quote to be rendered.
        title: A string containing the title text to be displayed.
        author: A string containing the author's name or attribution to be displayed.

    Returns:
        np.ndarray: A numpy array representing the rendered RGBA image.
    """
    pil_image = Image.new('RGBA', (dimensions[0], dimensions[1]), color=(0, 0, 0, 0))

    # Calculate all of our pixel values
    padding_w_pixels = int(PADDING_WIDTH * dimensions[0])
    padding_h_pixels = int(PADDING_HEIGHT * dimensions[1])
    quote_h_pixels = int(QUOTE_HEIGHT * dimensions[1])
    title_h_pixels = int(TITLE_HEIGHT * dimensions[1])
    author_h_pixels = int(AUTHOR_HEIGHT * dimensions[1])

    # Add quote
    safe_width = int(dimensions[0] - (padding_w_pixels * 2))
    safe_quote_height = int(quote_h_pixels - (padding_h_pixels * 2) - 8)

    font = ImageFont.truetype(QUOTE_FONT, index=QUOTE_FONT_INDEX)
    text, font = _fit_text_bbox(quote, font, safe_width, safe_quote_height)
    quote_stroke = ceil(_lerp(1, 4, ((font.size - 24) / 24)))

    draw = ImageDraw.Draw(pil_image)
    xy = (padding_w_pixels, padding_h_pixels)
    draw.text(xy, text, QUOTE_COLOR, font=font, align="center", stroke_width=quote_stroke, stroke_fill="black")

    # Add Title
    font = ImageFont.truetype(TITLE_FONT, title_h_pixels, index=TITLE_FONT_INDEX)
    font = _fit_text_width(title, font, safe_width, max_font_size=title_h_pixels)
    xy = (dimensions[0] - padding_w_pixels, dimensions[1] - padding_h_pixels - author_h_pixels)
    draw.text(xy, title, TITLE_COLOR, font=font, anchor="rd", stroke_width=2, stroke_fill="black")

    # Add Author
    font = ImageFont.truetype(AUTHOR_FONT, author_h_pixels, index=AUTHOR_FONT_INDEX)
    font = _fit_text_width(author, font, safe_width, max_font_size=author_h_pixels)
    xy = (dimensions[0] - padding_w_pixels, dimensions[1] - padding_h_pixels)
    logger.info(f"Drawing author {author} at xy={xy}")
    draw.text(xy, author, AUTHOR_COLOR, font=font, anchor="rd", stroke_width=2, stroke_fill="black")

    # Conver to np array and return
    return np.array(pil_image)


def _lerp(a: float, b: float, t: float) -> float:
    """Linearly interpolates between two values a and b based on a parameter t.

    Args:
        a: The starting value.
        b: The ending value.
        t: The interpolation factor.

    Returns:
        float: The interpolated value based on the inputs a, b, and t.
    """
    return a + (b - a) * t


def _fit_text_width(text: str, font: FreeTypeFont, max_width: int, min_font_size: int = 24, max_font_size: int = 38,
                    step_size: int = 1) -> FreeTypeFont:
    """Attempted to fit in line of text to a maximum width, starting at the `max_font_size` and moving downwards
    by `step_size` steps until a match is found or `min_font_size` is reached.

    Args:
        text (str): The text to be sized.
        font (FreeTypeFont): The font to be used.
        max_width (int): The maximum width of the text.
        min_font_size (int): The minimum font height in pixel, default is 28.
        max_font_size (int): The maximum font height in pixels, default is 38.
        step_size (int): The number of pixels to decrease on each attempt.

    Returns:
        FreeTypeFont: The font size to fit the text to the given width.
    """
    logger.debug(f'Trying to fit text {len(text)} character long into {max_width} wide box.')

    t = Timer()
    for font_size in reversed(range(min_font_size, max_font_size + 1, step_size)):
        logger.debug(f"Trying font size {font_size}")
        test_font = font.font_variant(size=font_size)
        line_width = int(test_font.getlength(text))
        if line_width > max_width:
            continue

        logger.debug(f"Successfully fit text using {font_size} in {t.get_elapsed_time()} seconds")
        return test_font

    logger.debug(f'Failed to fit text to {max_width}, returning min font size {min_font_size}')
    return font.font_variant(size=min_font_size)


def _fit_text_bbox(text: str, font: FreeTypeFont, max_width: int, max_height: int, spacing: int = 4,
                   min_font_size: int = 24, max_font_size: int = 96, step_size: int = 2) -> Tuple[str, FreeTypeFont]:
    """Scale text to a given rectangle, starting at the `max_size` and working downward by the `step_size` until a
    match is found or `min_font_size` is reached.

    Args:
        text (str): The text to fit.
        font (FreeTypeFont): The font being used, this should be the largest acceptable font size.
        max_width (int): The maximum width of the text in pixels.
        max_height (int): The maximum height of the text in pixels.
        spacing (Optional[int]): The spacing between the lines in pixels, default 4.
        min_font_size (Optional[int]): The minimum size of the text in pixels, default 24.
        max_font_size (Optional[int]): The maximum size of the text in pixels, default 38.
        step_size (Optional[int]): The amount to decrease with each attempt, default 1.

    Returns:
        Tuple[str, FreeTypeFont]: The wrapped text and a font size.
    """

    logger.debug(f'Trying to fit text {len(text)} character long into {max_width}x{max_height} pixels')

    max_font_size = min(max_font_size, max_width)

    t = Timer()
    for font_size in reversed(range(min_font_size, max_font_size + 1, step_size)):
        logger.debug(f"Trying font size {font_size}")
        test_font = font.font_variant(size=font_size)

        wrapped_text = _wrap_text(text, test_font, max_width)
        new_num_lines = wrapped_text.count('\n') + 1
        test_height = (new_num_lines * font_size) + (new_num_lines * spacing)

        if test_height > max_height:
            logger.debug(f"Failed total height {test_height} > {max_height}")
            continue

        logger.debug(f"Successfully fit text using {font_size} in {t.get_elapsed_time()} seconds")
        return wrapped_text, test_font

    index = text.rfind('. ')
    if index != -1:
        logger.debug(f"Unable to fit text, truncating at period and trying again.")
        return _fit_text_bbox(text[:index + 1], font, max_width, max_height, spacing, min_font_size, max_font_size,
                              step_size)

    logger.debug(f"Unable to fit text, returning min value of {min_font_size}")
    font = font.font_variant(size=min_font_size)
    wrapped_text = _wrap_text(text, font, max_width)
    return wrapped_text, font


def _wrap_text(text: str, font: FreeTypeFont, max_width: int) -> str:
    """Wraps text to a given width in pixels.

    Args:
        text (str): The text to wrap.
        font (FreeTypeFont): The font being used.
        max_width (int): The maximum width of the text in pixels.

    Returns:
        str: The wrapped text.
    """
    words = text.split()
    if not words:
        return text

    lines = [words[0]]

    for word in words[1:]:
        if not word:
            continue

        test_line = f"{lines[-1]} {word}"
        new_line_width = int(font.getlength(test_line))

        # Word is too long to fit on the current line, put word on the next line
        if new_line_width > max_width:
            lines.append(word)
        # Put the word on the current line
        else:
            lines[-1] = test_line

    return "\n".join(lines)
