import os
from math import ceil

import cv2
import numpy as np
from loguru import logger
from PIL import Image, ImageDraw, ImageFont
from pykuwahara import kuwahara

from ditto.utilities import wrap_text
from ditto.constants import *


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

class DittoImage:
    """Class representing a Ditto image.

    """
    image: np.ndarray = None
    blur_size: int = 35
    blur_sigma: float = 5.0

    file_path: str = None
    width: int = None
    height: int = None

    def __init__(self, file_path: str, width: int, height: int):
        """Initialize a Ditto image, loading the image from a file.

        Args:
            file_path (str): Path to the image file to load.
            width (int): Width of the image in pixels.
            height (int): Height of the image in pixels.
        """
        self.file_path = file_path
        self.width = width
        self.height = height
        self.image = cv2.imread(file_path)

    def show(self, title: str = None):
        """Display the image using cv2.imshow, used for debugging.

        Args:
            title (str): Title of the window.

        Returns:
            None
        """
        title = title or "Image"
        cv2.imshow(title, self.image)
        cv2.waitKey(0)
        cv2.destroyAllWindows()

    def write(self, file_path: str) -> bool:
        """Write the image to a file.

        Args:
            file_path (str): Path to the image file to write.

        Returns:
            bool: True if the image was written, False otherwise.
        """
        logger.info(f"Writing image to {file_path}")
        if not self.image.any():
            raise ValueError("Image not processed.")

        check = cv2.imwrite(file_path, self.image, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
        if not check and os.path.isdir(file_path):
            os.rmdir(file_path)

        return check

    def process(self, output_path: str, quote: str, title: str, author: str) -> bool:
        """Process the image and save it to a file.

        Args:
            output_path (str): Path to the output file.
            quote (str): Text of the quote to render onto the image.
            title (str): Text of the title to render onto the image.
            author (str): Text of the author's name to render onto the image.

        Returns:
            bool: True if the image was processed, False otherwise.
        """
        self._initial_resize()
        self._enhance()
        self._blur()
        self._add_text(quote, title, author)
        return self.write(output_path)

    def _initial_resize(self):
        """Resize the image to fit the required size.

        Returns:
            None
        """
        height, width = self.image.shape[:2]
        logger.info(f"Input width={width}, height={height}")

        # First resize to at least the height
        scale_factor = self.height / float(height)
        width = int(width * scale_factor)
        height = int(height * scale_factor)

        # If the width is still to small, resize up based on the width
        if width < self.width:
            scale_factor = self.width / float(width)
            width = int(width * scale_factor)
            height = int(height * scale_factor)

        logger.info(f"Resize width={width}, height={height}")
        self.image = cv2.resize(self.image, (width, height))

        # Super basic top down crop, will update to be context-sensitive
        logger.info(f"Crop width={self.width}, height={self.height}")
        self.image = self.image[:self.height, :self.width]

    def _enhance(self):
        """Adjust the brightness, saturation, and contrast of the image to better display on the e-ink screen.

        Returns:
            None
        """
        hsv = cv2.cvtColor(self.image, cv2.COLOR_BGR2HSV).astype("float32")
        h, s, v = cv2.split(hsv)
        s = np.clip(s * SATURATION, 0, 255)
        v = np.clip(v * BRIGHTNESS, 0, 255)
        hsv = cv2.merge([h, s, v]).astype("uint8")
        bgr = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)

        lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        l_float = (l.astype(np.float32) / 255.0) ** GAMMA
        l_int = np.clip(l_float * 255, 0, 255).astype(np.uint8)
        out = cv2.merge([l_int, a, b])

        self.image = cv2.cvtColor(out, cv2.COLOR_LAB2BGR)

    def _blur(self):
        """Blur the image.

        Returns:
            None
        """
        self.image = cv2.GaussianBlur(self.image, (self.blur_size, self.blur_size), self.blur_sigma)
        self.image = kuwahara(self.image, radius=KUWAHARA_RADIUS)

    def _add_text(self, quote: str, title: str, author: str):
        """Render the text onto the image.

        Args:
            quote (str): Text of the quote to render onto the image.
            title (str): Text of the title to render onto the image.
            author (str): Text of the author's name to render onto the image.

        Returns:
            None
        """
        # Convert image from cv2 format to PIL
        rgb_image = cv2.cvtColor(self.image, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(rgb_image)

        padding_w_pixels = int(PADDING_WIDTH * self.width)
        padding_h_pixels = int(PADDING_HEIGHT * self.height)
        quote_h_pixels = int(QUOTE_HEIGHT * self.height)
        title_h_pixels = int(TITLE_HEIGHT * self.height)
        author_h_pixels = int(AUTHOR_HEIGHT * self.height)

        # Add quote
        width = int(self.width - (padding_w_pixels * 2))
        height = int(quote_h_pixels - (padding_h_pixels * 2))

        font = ImageFont.truetype(QUOTE_FONT, index=QUOTE_FONT_INDEX)
        text, font = wrap_text.fit_text(quote, font, width, height)
        quote_stroke = ceil(_lerp(0, 4, ((font.size - 24) / 24)))

        draw = ImageDraw.Draw(pil_image)
        xy = (padding_w_pixels, padding_h_pixels)
        draw.text(xy, text, QUOTE_COLOR, font=font, align="center", stroke_width=quote_stroke, stroke_fill="black")

        # Add Title
        font = ImageFont.truetype(TITLE_FONT, title_h_pixels, index=TITLE_FONT_INDEX)
        font = wrap_text.fit_text_width(title, font, width, max_font_size=title_h_pixels)
        xy = (self.width - padding_w_pixels, self.height - padding_h_pixels - author_h_pixels)
        draw.text(xy, title, TITLE_COLOR, font=font, anchor="rd", stroke_width=2, stroke_fill="black")

        # Add Author
        author = f'- {author}'

        font = ImageFont.truetype(AUTHOR_FONT, author_h_pixels, index=AUTHOR_FONT_INDEX)
        font = wrap_text.fit_text_width(author, font, width, max_font_size=author_h_pixels)
        xy = (self.width - padding_w_pixels, self.height - padding_h_pixels)
        draw.text(xy, author, AUTHOR_COLOR, font=font, anchor="rd", stroke_width=2, stroke_fill="black")

        # Convert back to cv2 and back to BGR
        self.image = np.asarray(pil_image)
        self.image = cv2.cvtColor(self.image, cv2.COLOR_RGB2BGR)
