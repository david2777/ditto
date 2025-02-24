import cv2
import numpy as np
from loguru import logger
from PIL import Image, ImageDraw, ImageFont

from ditto.utilities import wrap_text
from ditto.constants import WIDTH, HEIGHT, PADDING, QUOTE_HEIGHT, AUTHOR_HEIGHT, TITLE_HEIGHT


class DittoImage:
    image: np.ndarray = None

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.image = cv2.imread(file_path)

    def show(self, title: str = None):
        title = title or "Image"
        cv2.imshow(title, self.image)
        cv2.waitKey(0)
        cv2.destroyAllWindows()

    def write(self, file_path: str):
        cv2.imwrite(file_path, self.image)

    def initial_resize(self):
        height, width = self.image.shape[:2]
        logger.info(f"Input width={width}, height={height}")

        # First resize to at least the height
        scale_factor = HEIGHT / float(height)
        width = int(width * scale_factor)
        height = int(height * scale_factor)

        # If the width is still to small, resize up based on the width
        if width < WIDTH:
            scale_factor = WIDTH / float(width)
            width = int(width * scale_factor)
            height = int(height * scale_factor)

        logger.info(f"Resize width={width}, height={height}")
        self.image = cv2.resize(self.image, (width, height))

        # Super basic top down crop, will update to be context-sensitive
        logger.info(f"Crop width={WIDTH}, height={HEIGHT}")
        self.image = self.image[:HEIGHT, :WIDTH]

    def blur(self, size: int = 35, sigma: float = 5.0):
        self.image = cv2.GaussianBlur(self.image, (size, size), sigma)

    def add_text(self, quote: str, title: str, author: str):
        # Convert image from cv2 format to PIL
        rgb_image = cv2.cvtColor(self.image, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(rgb_image)

        # Add quote
        width = WIDTH - (PADDING * 2)
        height = QUOTE_HEIGHT - (PADDING * 2)

        font = ImageFont.truetype("Charter.ttc", index=3)
        text, font = wrap_text.fit_text(quote, font, width, height)

        draw = ImageDraw.Draw(pil_image)
        xy = (PADDING, PADDING)
        draw.text(xy, text, 'white', font=font, align="center")

        # Add Title
        font = ImageFont.truetype("Charter.ttc", TITLE_HEIGHT, index=1)
        font = wrap_text.fit_text_width(title, font, width, max_font_size=TITLE_HEIGHT)
        xy = (WIDTH - PADDING, HEIGHT - PADDING - AUTHOR_HEIGHT)
        draw.text(xy, title, 'white', font=font, anchor="rd")

        # Add Author
        author = f'- {author}'

        font = ImageFont.truetype("Charter.ttc", AUTHOR_HEIGHT, index=0)
        font = wrap_text.fit_text_width(author, font, width, max_font_size=AUTHOR_HEIGHT)
        xy = (WIDTH - PADDING, HEIGHT - PADDING)
        draw.text(xy, author, 'white', font=font, anchor="rd")

        # Convert back to cv2
        self.image = np.asarray(pil_image)
