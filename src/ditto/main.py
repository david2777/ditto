import sys
import asyncio
import time
import platform
from pathlib import Path
from collections import deque
from pydantic import BaseModel, Field
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
    """Recorded metadata for a single client connection."""

    client: str = Field(..., description="The client name or IP address.")
    timestamp: datetime = Field(..., description="When the connection was made.")
    method: str = Field(..., description="The HTTP method of the request.")
    path: str = Field(..., description="The URL path that was requested.")
    quote_id: Optional[str] = Field(None, description="The ID of the quote that was served, if any.")
    processing_time_ms: float = Field(..., description="Time spent processing the request in milliseconds.")


class ServerStatus(BaseModel):
    """Response model for the root status endpoint."""

    system: dict = Field(..., description="Host system information (platform, Python version, hostname).")
    app: dict = Field(..., description="Application metadata (name, version, uptime).")
    database: dict = Field(..., description="Database statistics (client count, quote count, database file path).")
    config: dict = Field(..., description="Active configuration values.")
    recent_connections: List[ConnectionInfo] = Field(..., description="The most recent client connections.")


async def schedule_daily_sync():
    """Background task that syncs the Notion database every day at midnight.

    Runs in an infinite loop, sleeping until the next midnight before triggering a sync. On failure the loop
    pauses for 60 seconds to prevent rapid retries.

    Raises:
        asyncio.CancelledError: Propagated when the task is cancelled during shutdown.
    """
    while True:
        # Calculate time until next midnight
        now = datetime.now()
        tomorrow = now + timedelta(days=1)
        next_run = datetime(year=tomorrow.year, month=tomorrow.month, day=tomorrow.day, hour=0, minute=0, second=0)

        sleep_duration = (next_run - now).total_seconds()
        logger.info(f"Next Notion sync scheduled in {sleep_duration:.2f} seconds (at {next_run})")

        try:
            await asyncio.sleep(sleep_duration)
            logger.info("Starting scheduled daily Notion sync...")
            await notion.sync_notion_db(quote_manager)
            logger.info("Daily Notion sync completed.")
        except asyncio.CancelledError:
            logger.info("Daily sync task cancelled.")
            raise
        except Exception as e:
            logger.error(f"Error in daily sync task: {e}")
            # Prevent rapid failure loops
            await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context manager that handles startup and shutdown tasks.

    On startup, performs an initial Notion database sync and launches the daily sync background task.
    On shutdown, cancels the background task and waits for it to finish.

    Args:
        app: The FastAPI application instance.

    Yields:
        None: Control is yielded to the application between startup and shutdown.
    """
    # Startup: Sync data from Notion
    logger.info("Starting up: Syncing Notion data...")
    try:
        await notion.sync_notion_db(quote_manager)
    except Exception as e:
        logger.error(f"Failed to sync Notion data on startup: {e}")

    # Start daily sync task
    sync_task = asyncio.create_task(schedule_daily_sync())

    # Yield control to the application
    yield

    # Handle shutdown
    logger.info("Shutting down: Cancelling background tasks...")
    sync_task.cancel()
    try:
        await sync_task
    except asyncio.CancelledError:
        logger.info("Daily sync task cancelled successfully.")
    except Exception as e:
        # Catch unexpected crashes that happened during the task's life
        logger.error(f"Daily sync task failed with an error: {e}")


app = FastAPI(**constants.APP_META, lifespan=lifespan)

image_meta = {
    "response_class": FileResponse,
    "responses": {200: {"content": {"image/jpeg": {}}, "description": "Returns an image file (jpeg format)"}},
}


async def _process_quote(
    request: Request,
    client_override: Optional[str] = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
) -> Union[FileResponse, JSONResponse]:
    """Process a quote item and return the response

    Args:
        request: Request object.
        client_override: Override the client name from the request.
        width: Width of the image. Falls back to the client's stored default.
        height: Height of the image. Falls back to the client's stored default.

    Returns:
        The resulting file response.
    """
    start_proc = time.time()
    try:
        t = Timer()
        logger.info(f"request: {request.method} {request.url} from {request.client.host}")

        direction = constants.QueryDirection.from_request(request)
        if direction is None:
            return JSONResponse(status_code=400, content={"message": "Invalid direction"})

        client_name = client_override or request.client.host

        # get_quote returns (Quote | None, Client | None)
        quote_item, client = quote_manager.get_quote(client_name, direction, width=width, height=height)

        if not quote_item:
            return JSONResponse(status_code=404, content={"message": "No quotes available"})

        # Resolve effective dimensions: query args > stored client defaults
        effective_width = width or (client.default_width if client else constants.DEFAULT_WIDTH)
        effective_height = height or (client.default_height if client else constants.DEFAULT_HEIGHT)

        # Process image using the effective dimensions
        image_path = quote_item.process_image(effective_width, effective_height)

        if image_path is None or not image_path.is_file():
            return JSONResponse(status_code=500, content={"message": "Failed to process image"})

        response = FileResponse(image_path, media_type="image/jpeg")
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"

        logger.info(f'response: "{response.path}" generated in {t.get_elapsed_time()} seconds')

        # Track connection
        elapsed_ms = (time.time() - start_proc) * 1000
        RECENT_CONNECTIONS.append(
            ConnectionInfo(
                client=client_name,
                timestamp=datetime.now(),
                method=request.method,
                path=request.url.path,
                quote_id=quote_item.id,
                processing_time_ms=elapsed_ms,
            )
        )

        return response
    except Exception:
        logger.exception("Error processing request")
        return JSONResponse(status_code=500, content={"message": "Internal server error"})


@app.get("/", summary="Server State", description="Return basic state information", response_model=ServerStatus)
async def root_endpoint(request: Request) -> ServerStatus:
    """Return basic state information.

    Args:
        request: Request object.

    Returns:
        Basic state information.
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
            "hostname": platform.node(),
        },
        app={
            "name": "ditto",
            "version": constants.VERSION,
            "uptime_seconds": uptime_seconds,
            "uptime_human": str(timedelta(seconds=int(uptime_seconds)))
            if "timedelta" in globals()
            else f"{int(uptime_seconds)}s",
        },
        database={"client_count": client_count, "quote_count": quote_count, "database_file": quote_manager.db_url},
        config={
            "cache_enabled": constants.CACHE_ENABLED,
            "static_bg": constants.USE_STATIC_BG,
            "output_dir": Path(constants.OUTPUT_DIR).resolve().as_posix(),
        },
        recent_connections=list(RECENT_CONNECTIONS),
    )

    logger.info(f"response: {status}")
    return status


@app.get(
    "/current",
    summary="Current Quote",
    description="Return the current quote for this client",
    response_model=None,
    **image_meta,
)
async def current_endpoint(
    request: Request,
    client_override: Optional[str] = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
) -> Union[FileResponse, JSONResponse]:
    """Return the current quote for this client.

    Args:
        request: The incoming HTTP request.
        client_override: Override the client name derived from the request.
        width: Width of the image. Falls back to the client's stored default.
        height: Height of the image. Falls back to the client's stored default.

    Returns:
        A FileResponse with the rendered image, or a JSONResponse on error.
    """
    return await _process_quote(request, client_override, width, height)


@app.get(
    "/next",
    summary="Next Quote",
    description="Return the next quote for this client",
    response_model=None,
    **image_meta,
)
async def next_endpoint(
    request: Request,
    client_override: Optional[str] = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
) -> Union[FileResponse, JSONResponse]:
    """Return the next quote for this client.

    Args:
        request: The incoming HTTP request.
        client_override: Override the client name derived from the request.
        width: Width of the image. Falls back to the client's stored default.
        height: Height of the image. Falls back to the client's stored default.

    Returns:
        A FileResponse with the rendered image, or a JSONResponse on error.
    """
    return await _process_quote(request, client_override, width, height)


@app.get(
    "/previous",
    summary="Previous Quote",
    description="Return the previous quote for this client",
    response_model=None,
    **image_meta,
)
async def previous_endpoint(
    request: Request,
    client_override: Optional[str] = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
) -> Union[FileResponse, JSONResponse]:
    """Return the previous quote for this client.

    Args:
        request: The incoming HTTP request.
        client_override: Override the client name derived from the request.
        width: Width of the image. Falls back to the client's stored default.
        height: Height of the image. Falls back to the client's stored default.

    Returns:
        A FileResponse with the rendered image, or a JSONResponse on error.
    """
    return await _process_quote(request, client_override, width, height)


@app.get(
    "/random",
    summary="Random Quote",
    description="Return a random quote for this client",
    response_model=None,
    **image_meta,
)
async def random_endpoint(
    request: Request,
    client_override: Optional[str] = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
) -> Union[FileResponse, JSONResponse]:
    """Return a random quote for this client.

    Args:
        request: The incoming HTTP request.
        client_override: Override the client name derived from the request.
        width: Width of the image. Falls back to the client's stored default.
        height: Height of the image. Falls back to the client's stored default.

    Returns:
        A FileResponse with the rendered image, or a JSONResponse on error.
    """
    return await _process_quote(request, client_override, width, height)


class ClientCreate(BaseModel):
    """Request body for creating / pre-registering a client."""

    client_name: str = Field(..., description="The unique name for the client.")
    width: Optional[int] = Field(None, description="Default image width in pixels for this client.")
    height: Optional[int] = Field(None, description="Default image height in pixels for this client.")


class ClientInfo(BaseModel):
    """Response model for a single client."""

    id: int = Field(..., description="The database primary key of the client.")
    client_name: str = Field(..., description="The unique name for the client.")
    default_width: int = Field(..., description="Default image width in pixels.")
    default_height: int = Field(..., description="Default image height in pixels.")
    current_position: int = Field(..., description="The client's current position in the quote rotation.")


@app.post(
    "/clients",
    summary="Register Client",
    description="Pre-register a new client with optional default width and height",
    response_model=ClientInfo,
    status_code=201,
)
async def create_client_endpoint(body: ClientCreate) -> JSONResponse:
    """Register a new client.

    If the client already exists the existing record is returned (idempotent).

    Args:
        body: The request body containing client registration details.

    Returns:
        A 201 response containing the created or existing client's details.
    """
    client = quote_manager.add_client(client_name=body.client_name, width=body.width, height=body.height)
    return JSONResponse(
        status_code=201,
        content={
            "id": client.id,
            "client_name": client.client_name,
            "default_width": client.default_width,
            "default_height": client.default_height,
            "current_position": client.current_position,
        },
    )


@app.get(
    "/clients",
    summary="List Clients",
    description="Return all registered clients and their stored defaults",
    response_model=List[ClientInfo],
)
async def list_clients_endpoint() -> JSONResponse:
    """Return all registered clients.

    Returns:
        A JSON array of all registered clients and their stored defaults.
    """
    with quote_manager.Session() as session:
        clients = session.query(database.Client).all()
        return JSONResponse(
            content=[
                {
                    "id": c.id,
                    "client_name": c.client_name,
                    "default_width": c.default_width,
                    "default_height": c.default_height,
                    "current_position": c.current_position,
                }
                for c in clients
            ]
        )


@app.get("/health")
async def health_endpoint() -> JSONResponse:
    """Handles the health check endpoint for the service.

    Returns:
        A 200 response with ``{"status": "healthy"}`` if the database is reachable, or a 503 response with
        ``{"status": "unhealthy"}`` otherwise.
    """
    try:
        # Check DB connection
        with quote_manager.Session() as session:
            session.execute(database.select(1))
        return JSONResponse(status_code=200, content={"status": "healthy"})
    except Exception:
        return JSONResponse(status_code=503, content={"status": "unhealthy"})
