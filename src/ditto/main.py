from typing import *
from contextlib import asynccontextmanager

from loguru import logger
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

from ditto import constants, database, notion
from ditto.utilities.timer import Timer

# Initialize QuoteManager
quote_manager = database.QuoteManager()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Sync data from Notion
    logger.info("Starting up: Syncing Notion data...")
    try:
        await notion.sync_notion_db(quote_manager)
    except Exception as e:
        logger.error(f"Failed to sync Notion data on startup: {e}")
    yield
    # Shutdown logic if needed

app = FastAPI(**constants.APP_META, lifespan=lifespan)

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

        direction = constants.QueryDirection.from_request(request)
        if direction is None:
             return JSONResponse(status_code=400, content={"message": "Invalid direction"})

        client_name = client_override or request.client.host
        
        # database.QuoteManager.get_quote returns a Quote object or None
        quote_item = quote_manager.get_quote(client_name, direction)

        if not quote_item:
            return JSONResponse(status_code=404, content={"message": "No quotes available"})

        # Process image using the new method on Quote model
        image_path = quote_item.process_image(width, height)

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
    
    # We might need to query the DB to get stats, or just omit for now.
    # To keep it simple, I'll count quotes in the DB.
    try:
        with quote_manager.Session() as session:
            client_count = session.query(database.Client).count()
            quote_count = session.query(database.Quote).count()
    except Exception:
        client_count = 0
        quote_count = 0

    response = {'application': 'ditto',
                'version': constants.VERSION,
                'clients': client_count,
                'quote_count': quote_count
    }
    logger.info(f"response: {response}")
    return JSONResponse(content=response, headers=headers, status_code=200)


@app.get("/current", summary="Current Quote", description="Return the current quote for this client", **image_meta)
async def current_endpoint(request: Request, client_override: Optional[str] = None,
                           width: Optional[int] = None, height: Optional[int] = None):
    """Return the next quote for this client."""
    return await _process_quote(request, client_override, width, height)


@app.get("/next", summary="Next Quote", description="Return the next quote for this client", **image_meta)
async def next_endpoint(request: Request, client_override: Optional[str] = None,
                        width: Optional[int] = None, height: Optional[int] = None):
    """Return the next quote for this client."""
    return await _process_quote(request, client_override, width, height)


@app.get("/previous", summary="Previous Quote", description="Return the previous quote for this client",
         **image_meta)
async def previous_endpoint(request: Request, client_override: Optional[str] = None,
                            width: Optional[int] = None, height: Optional[int] = None):
    """Return the previous quote for this client."""
    return await _process_quote(request, client_override, width, height)


@app.get("/random", summary="Random Quote", description="Return a random quote for this client", **image_meta)
async def random_endpoint(request: Request, client_override: Optional[str] = None,
                          width: Optional[int] = None, height: Optional[int] = None):
    """Return a random quote for this client."""
    return await _process_quote(request, client_override, width, height)


@app.get("/health")
async def health_endpoint() -> JSONResponse:
    """Handles the health check endpoint for the service."""
    try:
        # Check DB connection
        with quote_manager.Session() as session:
            session.execute(database.select(1))
        return JSONResponse(status_code=200, content={"status": "healthy"})
    except Exception:
        return JSONResponse(status_code=503, content={"status": "unhealthy"})
