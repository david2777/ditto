from enum import StrEnum
from requests import Request


class QueryDirection(StrEnum):
    CURRENT = "/current"
    FORWARD = "/next"
    REVERSE = "/previous"
    RANDOM = "/random"

    @staticmethod
    def from_request(request: Request):
        if request.url.path == "/current":
            return QueryDirection.CURRENT
        if request.url.path == "/next":
            return QueryDirection.FORWARD
        if request.url.path == "/previous":
            return QueryDirection.REVERSE
        if request.url.path == "/random":
            return QueryDirection.RANDOM
        else:
            return None


# Image Formatting
DEFAULT_WIDTH = 800
DEFAULT_HEIGHT = 480

PADDING_WIDTH = 0.0250  # 2.5% width
PADDING_HEIGHT = 0.0250  # 2.5% height * 4 = 10% total

QUOTE_HEIGHT = 0.775  # 77.5% height
QUOTE_COLOR = "white"
QUOTE_FONT = "resources/fonts/Charter.ttc"
QUOTE_FONT_INDEX = 3

TITLE_HEIGHT = 0.075  # 7.5% height
TITLE_COLOR = "white"
TITLE_FONT = "resources/fonts/Charter.ttc"
TITLE_FONT_INDEX = 0

AUTHOR_HEIGHT = 0.05  # 5% height
AUTHOR_COLOR = "white"
AUTHOR_FONT = "resources/fonts/Charter.ttc"
AUTHOR_FONT_INDEX = 0

# App
OUTPUT_DIR = "data"
CACHE_ENABLED = False
USE_STATIC_BG = False


def _get_toml_data():
    import tomllib

    with open("pyproject.toml", "rb") as f:
        data = tomllib.load(f)
    return data


TOML_DATA = _get_toml_data()
PROJECT_NAME = TOML_DATA["project"]["name"]
PROJECT_DESCRIPTION = TOML_DATA["project"]["description"]
VERSION = TOML_DATA["project"]["version"]

APP_META = {
    "title": PROJECT_NAME,
    "description": PROJECT_DESCRIPTION,
    "version": VERSION,
    "contact": {
        "name": "David Lee-DuVoisin",
        "url": "https://david.lee-duvoisin.com",
        "email": "daduvo11@gmail.com",
    },
    "license_info": {
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT",
    },
}
