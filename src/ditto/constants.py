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
