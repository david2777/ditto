import tomllib

# Image Formatting
WIDTH = 480
HEIGHT = 800
PADDING = 10

QUOTE_HEIGHT = 650
QUOTE_COLOR = "white"
QUOTE_FONT = "Charter.ttc"
QUOTE_FONT_INDEX = 3

TITLE_HEIGHT = 50
TITLE_COLOR = "white"
TITLE_FONT = "Charter.ttc"
TITLE_FONT_INDEX = 1

AUTHOR_HEIGHT = 35
AUTHOR_COLOR = "white"
AUTHOR_FONT = "Charter.ttc"
AUTHOR_FONT_INDEX = 0

# App
OUTPUT_DIR = None
CACHE_ENABLED = False

def _get_version():
    with open("pyproject.toml", "rb") as f:
        data = tomllib.load(f)

    version = data["project"]["version"]
    return version

VERSION = _get_version()
