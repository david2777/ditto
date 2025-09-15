from typing import Optional, Tuple

from loguru import logger
from PIL.ImageFont import FreeTypeFont

from ditto.utilities.timer import Timer


def fit_text_width(text: str, font: FreeTypeFont, max_width: int, min_font_size: int = 24, max_font_size: int = 38,
                   step_size: int = 1) -> FreeTypeFont:
    """Attempted to fit in line of text to a maximum width, starting at the `max_font_size` and moving downwards
    by `step_size` steps until a match is found or `min_font_size` is reached.

    Args:
        text (str): The text to be sized.
        font (FreeTypeFont): The font to be used.
        max_width (int): The maximum width of the text.
        min_font_size (int): The minimum font height in pixel, default is 28.
        max_font_size (int): The maximum font height in pixels, default is 38.
        step_size (int): The amount of pixels to decrease on each attempt.

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


def fit_text(text: str, font: FreeTypeFont, max_width: int, max_height: int, spacing: int = 4,
             min_font_size: int = 24, max_font_size: int = 48, step_size: int = 1) -> Tuple[str, FreeTypeFont]:
    """Scale text to a given rectangle, starting at the `max_size` and working downward by the `step_size` until a
    match is found or `min_font_size` is reached.

    TODO: Do we bother trying to truncate the text as well?

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
