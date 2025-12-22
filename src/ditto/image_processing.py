from loguru import logger
from wand.image import Image

from ditto import text_rendering


def process_image(raw_path: str, output_path: str, dimensions: tuple[int, int],
                  quote: str, title: str, author: str) -> bool:
    """Processes an image by performing resizing, cropping, color adjustments,
    sharpening, dithering, adding text, and saving the output.

    This function operates on an image, preparing it for e-ink display by adjusting
    its dimensions, modulating color properties, sharpening details, applying a
    specified dithering method, overlaying text, and saving the final output
    to a specified path.

    Args:
        raw_path (str): Path to the input raw image file.
        output_path (str): Path where the processed image will be saved.
        dimensions (tuple[int, int]): Target dimensions (width, height) for
            the output image.
        quote (str): Quote to be added as a text overlay on the image.
        title (str): Title to go with the quote.
        author (str): Author name to be included with the quote and title.

    Returns:
        bool: True if the image processing and saving operation completes
        successfully.
    """
    with Image(filename=raw_path) as img:
        if img.colorspace != 'srgb':
            img.transform_colorspace('srgb')

        # 1. RESIZE & CROP: Resize to the target dimensions, then crop to center.
        orig_width = img.width
        orig_height = img.height

        # First, resize to at least the width (we will crop height later)
        scale_factor = dimensions[0] / float(orig_width)
        new_width = int(orig_width * scale_factor)
        new_height = int(orig_height * scale_factor)

        # If the height is too small, resize up based on the height (we will crop later)
        if new_height < dimensions[1]:
            scale_factor = dimensions[1] / float(new_height)
            new_width = int(new_width * scale_factor)
            new_height = int(new_height * scale_factor)

        logger.debug(f"Original {orig_width}x{orig_height} resized to {new_width}x{new_height} before cropping")
        img.resize(new_width, new_height)

        img.gravity = 'center'  # Use 'center' gravity
        img.crop(width=dimensions[0], height=dimensions[1])

        logger.info(f"Cropped to {img.width}x{img.height}")

        # 2. COLOR PREP: Compensate for the ink's reflectivity
        # Modulate(brightness, saturation, hue)
        img.modulate(115, 160, 100)

        # Level(black_point, white_point, gamma)
        # Lifting gamma to 1.2-1.5 helps prevent "muddy" shadows on e-ink
        img.level(0.05, 0.95, gamma=1.3)

        # 3. SHARPENING: E-ink microcapsules have a slight bleed
        # radius=0, sigma=1.0 gives a nice crisp edge for dithering
        img.sharpen(radius=0, sigma=1.0)

        # 4. TEXT: Add the quote and author text
        text_data = text_rendering.render_text(dimensions, quote, title, author)
        with Image.from_array(text_data) as text_image:
            img.composite(text_image, left=0, top=0)

        # # 5. REMAP & DITHER: Dither the image based on the palette.
        # with Image(filename="resources/palette_7.png") as palette:
        #     # method options: 'floyd_steinberg', 'riemersma', or 'none'
        #     img.remap(affinity=palette, method='floyd_steinberg')

        # 6. SAVE: Save the image
        img.compression_quality = 70
        # img.interlace_scheme = 'no'
        # img.options['jpeg:sampling-factor'] = '1x1,1x1,1x1'
        img.save(filename=output_path)

    return True
