import tomllib

# Image Formatting
WIDTH = 480
HEIGHT = 800
PADDING = 10
QUOTE_HEIGHT = 650
TITLE_HEIGHT = 50
AUTHOR_HEIGHT = 35

def _get_version():
    with open("pyproject.toml", "rb") as f:
        data = tomllib.load(f)

    version = data["project"]["version"]
    return version

VERSION = _get_version()
