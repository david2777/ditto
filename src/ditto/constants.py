# Image Formatting
WIDTH = 480
HEIGHT = 800
PADDING = 10

QUOTE_HEIGHT = 650
QUOTE_COLOR = "white"
QUOTE_FONT = "resources/fonts/Charter.ttc"
QUOTE_FONT_INDEX = 3

TITLE_HEIGHT = 50
TITLE_COLOR = "white"
TITLE_FONT = "resources/fonts/Charter.ttc"
TITLE_FONT_INDEX = 1

AUTHOR_HEIGHT = 35
AUTHOR_COLOR = "white"
AUTHOR_FONT = "resources/fonts/Charter.ttc"
AUTHOR_FONT_INDEX = 0

# App
OUTPUT_DIR = 'data'
CACHE_ENABLED = False


def _get_toml_data():
    import tomllib
    with open("pyproject.toml", "rb") as f:
        data = tomllib.load(f)
    return data


TOML_DATA = _get_toml_data()
PROJECT_NAME = TOML_DATA["project"]["version"]
PROJECT_DESCRIPTION = TOML_DATA["project"]["description"]
VERSION = TOML_DATA["project"]["version"]

APP_META = {'title': PROJECT_NAME,
            'description': PROJECT_DESCRIPTION,
            'version': VERSION,
            'contact': {"name": "David Lee-DuVoisin",
                        "url": "https://david.lee-duvoisin.com",
                        "email": "daduvo11@gmail..com",
                        },
            'license_info': {
                "name": "MIT",
                "url": "https://opensource.org/licenses/MIT",
            }}
