from typing import Union, Optional

from loguru import logger
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

from ditto import constants, database, secrets
from ditto.utilities.timer import Timer

notion_db = database.NotionDatabaseManager(secrets.NOTION_DATABASE_ID)
app = FastAPI(**constants.APP_META)

image_meta = {'response_class': FileResponse,
              'responses': {200: {"content": {"image/jpeg": {}},
                                  "description": "Returns an image file (jpeg format)"}}}


async def _process_quote(request: Request, client_override: Optional[str] = None, width: Optional[int] = None,
                         height: Optional[int] = None) -> Union[FileResponse, JSONResponse]:
    """Process a quote item and return the response

    Args:
        request (Request): Request object.
        client_override (Optional[str]): Override the client name from the request.
        width (Optional[int]): Width of the image.
        height (Optional[int]): Height of the image.

    Returns:
        Union[FileResponse, JSONResponse]: The resulting file response.
    """
    try:
        t = Timer()
        logger.info(f"request: {request.method} {request.url} from {request.client.host}")

        quote_item = await notion_db.get_item_from_request(request=request, client_override=client_override)
        if not quote_item:
            return JSONResponse(status_code=404, content={"message": "No quotes available"})

        image_path = await quote_item.process_image(width, height)

        if image_path is None or not image_path.is_file():
            return JSONResponse(status_code=500, content={"message": "Failed to process image"})

        response = FileResponse(image_path, media_type="image/jpeg")
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"

        logger.info(f'response: "{response.path}" generated in {t.get_elapsed_time()} seconds')

        return response
    except Exception:
        logger.exception("Error processing request")
        return JSONResponse(status_code=500, content={"message": "Internal server error"})


@app.get("/", summary="Server State", description="Return basic state information")
async def root_endpoint(request: Request) -> JSONResponse:
    """Return basic state information.

    Args:
        request (Request): Request object.

    Returns:
        JSONResponse: Basic state information.
    """
    logger.info(f"request: {request.method} {request.url}")
    headers = {
        'Cache-Control': 'no-store, no-cache, must-revalidate',
        'Pragma': 'no-cache',
        'Expires': '0'
    }
    response = {'application': 'ditto',
                'version': constants.VERSION,
                'clients': [k for k in database.NotionDatabaseManager._clients],
                'quote_count': len(database.NotionDatabaseManager._page_id_cache)
    }
    logger.info(f"response: {response}")
    return JSONResponse(content=response, headers=headers, status_code=200)


@app.get("/current", summary="Current Quote", description="Return the current quote for this client", **image_meta)
async def current_endpoint(request: Request, client_override: Optional[str] = None,
                           width: Optional[int] = None, height: Optional[int] = None):
    """Return the next quote for this client.

    Args:
        request (Request): Request object.
        client_override (Optional[str]): Override the client name from the request.
        width (Optional[int]): Width of the image.
        height (Optional[int]): Height of the image.

    Returns:
        Union[FileResponse, JSONResponse]: The next quote for this client.
    """
    return await _process_quote(request, client_override, width, height)


@app.get("/next", summary="Next Quote", description="Return the next quote for this client", **image_meta)
async def next_endpoint(request: Request, client_override: Optional[str] = None,
                        width: Optional[int] = None, height: Optional[int] = None):
    """Return the next quote for this client.

    Args:
        request (Request): Request object.
        client_override (Optional[str]): Override the client name from the request.
        width (Optional[int]): Width of the image.
        height (Optional[int]): Height of the image.

    Returns:
        Union[FileResponse, JSONResponse]: The next quote for this client.
    """
    return await _process_quote(request, client_override, width, height)


@app.get("/previous", summary="Previous Quote", description="Return the previous quote for this client",
         **image_meta)
async def previous_endpoint(request: Request, client_override: Optional[str] = None,
                            width: Optional[int] = None, height: Optional[int] = None):
    """Return the previous quote for this client.

    Args:
        request (Request): Request object.
        client_override (Optional[str]): Override the client name from the request.
        width (Optional[int]): Width of the image.
        height (Optional[int]): Height of the image.

    Returns:
        Union[FileResponse, JSONResponse]: The previous quote for this client.
    """
    return await _process_quote(request, client_override, width, height)


@app.get("/random", summary="Random Quote", description="Return a random quote for this client", **image_meta)
async def random_endpoint(request: Request, client_override: Optional[str] = None,
                          width: Optional[int] = None, height: Optional[int] = None):
    """Return a random quote for this client.

    Args:
        request (Request): Request object.
        client_override (Optional[str]): Override the client name from the request.
        width (Optional[int]): Width of the image.
        height (Optional[int]): Height of the image.

    Returns:
        Union[FileResponse, JSONResponse]: The random quote for this client.
    """
    return await _process_quote(request, client_override, width, height)


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
