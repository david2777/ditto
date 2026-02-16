import sys
import os
import time
import platform
from typing import *
from pathlib import Path
from collections import deque
from pydantic import BaseModel
from datetime import datetime, timedelta
from typing import Optional, List, Union
from contextlib import asynccontextmanager

from loguru import logger
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

from ditto import constants, database, notion
from ditto.utilities.timer import Timer

# Initialize QuoteManager
quote_manager = database.QuoteManager()

# Global State
START_TIME = time.time()
RECENT_CONNECTIONS = deque(maxlen=10)

class ConnectionInfo(BaseModel):
    client: str
    timestamp: datetime
    method: str
    path: str
    quote_id: Optional[str] = None
    processing_time_ms: float

class ServerStatus(BaseModel):
    system: dict
    app: dict
    database: dict
    config: dict
    recent_connections: List[ConnectionInfo]

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
    start_proc = time.time()
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
        
        # Track connection
        elapsed_ms = (time.time() - start_proc) * 1000
        RECENT_CONNECTIONS.append(ConnectionInfo(
            client=client_name,
            timestamp=datetime.now(),
            method=request.method,
            path=request.url.path,
            quote_id=quote_item.id,
            processing_time_ms=elapsed_ms
        ))

        return response
    except Exception:
        logger.exception("Error processing request")
        return JSONResponse(status_code=500, content={"message": "Internal server error"})


@app.get("/", summary="Server State", description="Return basic state information", response_model=ServerStatus)
async def root_endpoint(request: Request) -> ServerStatus:
    """Return basic state information.

    Args:
        request (Request): Request object.

    Returns:
        ServerStatus: Basic state information.
    """
    logger.info(f"request: {request.method} {request.url}")
    
    # Database Stats
    try:
        with quote_manager.Session() as session:
            client_count = session.query(database.Client).count()
            quote_count = session.query(database.Quote).count()
    except Exception:
        client_count = -1
        quote_count = -1

    uptime_seconds = time.time() - START_TIME

    status = ServerStatus(
        system={
            "platform": platform.system(),
            "platform_release": platform.release(),
            "python_version": sys.version.split()[0],
            "hostname": platform.node()
        },
        app={
            "name": "ditto",
            "version": constants.VERSION,
            "uptime_seconds": uptime_seconds,
            "uptime_human": str(timedelta(seconds=int(uptime_seconds))) if 'timedelta' in globals() else f"{int(uptime_seconds)}s"
        },
        database={
            "client_count": client_count,
            "quote_count": quote_count,
            "database_file": quote_manager.db_url
        },
        config={
            "cache_enabled": constants.CACHE_ENABLED,
            "static_bg": constants.USE_STATIC_BG,
            "output_dir": Path(constants.OUTPUT_DIR).resolve().as_posix()
        },
        recent_connections=list(RECENT_CONNECTIONS)
    )

    logger.info(f"response: {status}")
    return status


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
