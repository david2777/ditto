from loguru import logger
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse

from ditto import constants, database, secrets
from ditto.utilities.timer import Timer

notion_db = database.NotionDatabaseManager(secrets.NOTION_DATABASE_ID)

app = FastAPI(**constants.APP_META)

image_meta = {'response_class': FileResponse,
              'responses': {200: {"content": {"image/jpeg": {}},
                                  "description": "Returns an image file (jpeg format)"}}}


class GlobalState:
    _instance = None

    last_request = {}

    def __new__(cls):
        if getattr(cls, '_instance') is None:
            cls._instance = super(GlobalState, cls).__new__(cls)
        return cls._instance

    def set_last_request(self, request, quote_id):
        self.last_request = {'host': request.client.host,
                             'method': request.method,
                             'url': request.url._url,
                             'result_id': quote_id, }


async def _process_quote(request: Request, quote_item: database.NotionQuote):
    await quote_item.process_image()

    gs = GlobalState()
    gs.set_last_request(request, quote_item.page_id)

    response = FileResponse(quote_item.image_path_processed.as_posix(), media_type="image/jpeg")
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.get("/", summary="Server State", description="Return basic state information")
async def root_endpoint(request: Request):
    logger.info(f"request: {request.method} {request.url}")
    gs = GlobalState()
    response = {'application': 'ditto',
                'version': constants.VERSION,
                'clients': len(database.NotionDatabaseManager._clients),
                'quote_count': len(database.NotionDatabaseManager._page_id_cache),
                'last_request': gs.last_request}
    logger.info(f"response: {response}")
    return response


@app.get("/next", summary="Next Quote", description="Return the next quote for this client", **image_meta)
async def next_endpoint(request: Request):
    t = Timer()
    logger.info(f"request: {request.method} {request.url} from {request.client.host}")

    quote_item = await notion_db.get_next_item(request.client.host)
    response = await _process_quote(request, quote_item)
    logger.info(f'response: "{quote_item.image_path_processed.as_posix()}" generated in {t.get_elapsed_time()} seconds')
    return response


@app.get("/previous", summary="Previous Quote", description="Return the previous quote for this client",
         **image_meta)
async def previous_endpoint(request: Request):
    t = Timer()
    logger.info(f"request: {request.method} {request.url} from {request.client.host}")

    quote_item = await notion_db.get_previous_item(request.client.host)
    response = await _process_quote(request, quote_item)
    logger.info(f'response: "{quote_item.image_path_processed.as_posix()}" generated in {t.get_elapsed_time()} seconds')
    return response


@app.get("/random", summary="Random Quote", description="Return a random quote for this client", **image_meta)
async def random_endpoint(request: Request):
    t = Timer()
    logger.info(f"request: {request.method} {request.url} from {request.client.host}")

    quote_item = await notion_db.get_random_item(request.client.host)
    response = await _process_quote(request, quote_item)
    logger.info(f'response: "{quote_item.image_path_processed.as_posix()}" generated in {t.get_elapsed_time()} seconds')
    return response
