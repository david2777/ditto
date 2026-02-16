import sys
import time
import platform
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Union

from loguru import logger
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

from ditto import constants, database
from ditto.lifecycle import quote_manager, lifespan, START_TIME, RECENT_CONNECTIONS
from ditto.schemas import ConnectionInfo, ServerStatus, ClientCreate, ClientUpdate, ClientInfo
from ditto.utilities.timer import Timer

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
        elapsed_ms = t.get_elapsed_time_ms()
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


# --- Status & health endpoints ------------------------------------------------


@app.get("/", summary="Server State", description="Return basic state information", response_model=ServerStatus)
async def root_endpoint(request: Request) -> ServerStatus:
    """Return basic state information.

    Args:
        request: Request object.

    Returns:
        Basic state information.
    """
    logger.info(f"request: {request.method} {request.url}")

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
            "uptime_human": str(timedelta(seconds=int(uptime_seconds))),
        },
        database=quote_manager.get_stats(),
        config={
            "cache_enabled": constants.CACHE_ENABLED,
            "static_bg": constants.USE_STATIC_BG,
            "output_dir": Path(constants.OUTPUT_DIR).resolve().as_posix(),
        },
        recent_connections=list(RECENT_CONNECTIONS),
    )

    logger.info(f"response: {status}")
    return status


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


# --- Quote endpoints (image responses) ----------------------------------------

_QUOTE_ROUTES = [
    {"path": "/current", "summary": "Current Quote", "description": "Return the current quote for this client"},
    {"path": "/next", "summary": "Next Quote", "description": "Return the next quote for this client"},
    {"path": "/previous", "summary": "Previous Quote", "description": "Return the previous quote for this client"},
    {"path": "/random", "summary": "Random Quote", "description": "Return a random quote for this client"},
]


def _register_quote_routes():
    """Register the four quote endpoints using a shared handler."""
    for route in _QUOTE_ROUTES:

        async def _endpoint(
            request: Request,
            client_override: Optional[str] = None,
            width: Optional[int] = None,
            height: Optional[int] = None,
        ) -> Union[FileResponse, JSONResponse]:
            return await _process_quote(request, client_override, width, height)

        _endpoint.__doc__ = f"""{route["description"]}.

    Args:
        request: The incoming HTTP request.
        client_override: Override the client name derived from the request.
        width: Width of the image. Falls back to the client's stored default.
        height: Height of the image. Falls back to the client's stored default.

    Returns:
        A FileResponse with the rendered image, or a JSONResponse on error.
    """
        app.get(
            route["path"],
            summary=route["summary"],
            description=route["description"],
            response_model=None,
            **image_meta,
        )(_endpoint)


_register_quote_routes()


# --- Client management endpoints ----------------------------------------------


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


@app.patch(
    "/clients/{client_id}",
    summary="Update Client",
    description="Update an existing client's default width, height, and/or position",
    response_model=ClientInfo,
)
async def update_client_endpoint(client_id: int, body: ClientUpdate) -> JSONResponse:
    """Update a client's stored settings.

    Only fields present in the request body are modified.

    Args:
        client_id: The database primary key of the client to update.
        body: The request body containing the fields to update.

    Returns:
        A 200 response with the updated client details, or 404 if the client was not found.
    """
    client = quote_manager.update_client(
        client_id=client_id,
        width=body.width,
        height=body.height,
        position=body.position,
    )
    if not client:
        return JSONResponse(status_code=404, content={"message": f"Client {client_id} not found"})
    return JSONResponse(
        content={
            "id": client.id,
            "client_name": client.client_name,
            "default_width": client.default_width,
            "default_height": client.default_height,
            "current_position": client.current_position,
        },
    )
