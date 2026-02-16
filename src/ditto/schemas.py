"""Pydantic request and response models for the Ditto API."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


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
