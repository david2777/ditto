from typing import Union, Optional

from loguru import logger
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

from ditto import constants, database, secrets
from ditto.utilities.timer import Timer

notion_db = database.NotionDatabaseManager(secrets.NOTION_DATABASE_ID)

# TODO: Remove duplicate code
# TODO: Rework global state to be a rolling list of the last x responses

app = FastAPI(**constants.APP_META)

image_meta = {'response_class': FileResponse,
              'responses': {200: {"content": {"image/jpeg": {}},
                                  "description": "Returns an image file (jpeg format)"}}}


class GlobalState:
    """Global state singleton, which stores the last request for debugging.

    """
    _instance = None

    last_request = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(GlobalState, cls).__new__(cls)
        return cls._instance

    def set_last_request(self, request: Request, quote_id: str):
        """Set the last request variable for future retrieval.

        Args:
            request (Request): Request object.
            quote_id (str): The resulting quote id.

        Returns:
            None
        """
        self.last_request = {'host': request.client.host,
                             'method': request.method,
                             'url': request.url._url,
                             'result_id': quote_id, }


async def _process_quote(request: Request, quote_item: database.NotionQuote, width: Optional[int] = None,
                         height: Optional[int] = None) -> Union[FileResponse, JSONResponse]:
    """Process a quote item and return the response

    Args:
        request (Request): Request object.
        quote_item (database.NotionQuote): Quote item from the database.
        width (Optional[int]): Width of the image.
        height (Optional[int]): Height of the image.

    Returns:
        Union[FileResponse, JSONResponse]: The resulting file response.
    """
    image_path = await quote_item.process_image(width, height)

    if image_path is None or not image_path.is_file():
        return JSONResponse(status_code=500, content={"message": "Failed to process image"})

    gs = GlobalState()
    gs.set_last_request(request, quote_item.page_id)

    response = FileResponse(image_path, media_type="image/jpeg")
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.get("/", summary="Server State", description="Return basic state information")
async def root_endpoint(request: Request) -> JSONResponse:
    """Return basic state information.

    Args:
        request (Request): Request object.

    Returns:
        JSONResponse: Basic state information.
    """
    logger.info(f"request: {request.method} {request.url}")
    gs = GlobalState()
    response = {'application': 'ditto',
                'version': constants.VERSION,
                'clients': len(database.NotionDatabaseManager._clients),
                'quote_count': len(database.NotionDatabaseManager._page_id_cache),
                'last_request': gs.last_request}
    logger.info(f"response: {response}")
    return JSONResponse(content=response, status_code=200)


@app.get("/next", summary="Next Quote", description="Return the next quote for this client", **image_meta)
async def next_endpoint(request: Request, width: Optional[int] = None, height: Optional[int] = None):
    """Return the next quote for this client.

    Args:
        request (Request): Request object.
        width (Optional[int]): Width of the image.
        height (Optional[int]): Height of the image.

    Returns:
        Union[FileResponse, JSONResponse]: The next quote for this client.
    """
    t = Timer()
    logger.info(f"request: {request.method} {request.url} from {request.client.host}")

    try:
        quote_item = await notion_db.get_next_item(request.client.host)
        if not quote_item:
            return JSONResponse(status_code=404, content={"message": "No quotes available"})
        response = await _process_quote(request, quote_item, width, height)
        if isinstance(response, FileResponse):
            logger.info(f'response: "{response.path}" generated in {t.get_elapsed_time()} seconds')
        else:
            logger.info(f'response: {response.status_code} generated in {t.get_elapsed_time()} seconds')
        return response
    except Exception:
        logger.exception("Error processing request")
        return JSONResponse(status_code=500, content={"message": "Internal server error"})


@app.get("/previous", summary="Previous Quote", description="Return the previous quote for this client",
         **image_meta)
async def previous_endpoint(request: Request, width: Optional[int] = None, height: Optional[int] = None):
    """Return the previous quote for this client.

    Args:
        request (Request): Request object.
        width (Optional[int]): Width of the image.
        height (Optional[int]): Height of the image.

    Returns:
        Union[FileResponse, JSONResponse]: The previous quote for this client.
    """
    t = Timer()
    logger.info(f"request: {request.method} {request.url} from {request.client.host}")

    try:
        quote_item = await notion_db.get_previous_item(request.client.host)
        if not quote_item:
            return JSONResponse(status_code=404, content={"message": "No quotes available"})
        response = await _process_quote(request, quote_item, width, height)
        if isinstance(response, FileResponse):
            logger.info(f'response: "{response.path}" generated in {t.get_elapsed_time()} seconds')
        else:
            logger.info(f'response: {response.status_code} generated in {t.get_elapsed_time()} seconds')
        return response
    except Exception:
        logger.exception("Error processing request")
        return JSONResponse(status_code=500, content={"message": "Internal server error"})


@app.get("/random", summary="Random Quote", description="Return a random quote for this client", **image_meta)
async def random_endpoint(request: Request, width: Optional[int] = None, height: Optional[int] = None):
    """Return a random quote for this client.

    Args:
        request (Request): Request object.
        width (Optional[int]): Width of the image.
        height (Optional[int]): Height of the image.

    Returns:
        Union[FileResponse, JSONResponse]: The random quote for this client.
    """
    t = Timer()
    logger.info(f"request: {request.method} {request.url} from {request.client.host}")

    try:
        quote_item = await notion_db.get_random_item(request.client.host)
        if not quote_item:
            return JSONResponse(status_code=404, content={"message": "No quotes available"})
        response = await _process_quote(request, quote_item, width, height)
        if isinstance(response, FileResponse):
            logger.info(f'response: "{response.path}" generated in {t.get_elapsed_time()} seconds')
        else:
            logger.info(f'response: {response.status_code} generated in {t.get_elapsed_time()} seconds')
        return response
    except Exception:
        logger.exception("Error processing request")
        return JSONResponse(status_code=500, content={"message": "Internal server error"})


@app.get("/health")
async def health_endpoint() -> JSONResponse:
    """Handles the health check endpoint for the service.

    Returns:
        JSONResponse: A JSON response with a status code representing the
        health of the service and a content body indicating "healthy" or
        "unhealthy".
    """
    try:
        # Add any necessary health checks
        return JSONResponse(status_code=200, content={"status": "healthy"})
    except Exception:
        return JSONResponse(status_code=503, content={"status": "unhealthy"})
