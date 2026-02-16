"""Tests for ditto.schemas — Pydantic request/response models."""

import pytest
from datetime import datetime
from pydantic import ValidationError
from ditto.schemas import ClientCreate, ClientUpdate, ClientInfo, ConnectionInfo, ServerStatus


class TestClientCreate:
    def test_valid_minimal(self):
        """Only client_name is required."""
        obj = ClientCreate(client_name="test-client")
        assert obj.client_name == "test-client"
        assert obj.width is None
        assert obj.height is None

    def test_valid_with_dimensions(self):
        """Width and height are accepted when provided."""
        obj = ClientCreate(client_name="test", width=640, height=480)
        assert obj.width == 640
        assert obj.height == 480

    def test_missing_client_name(self):
        """Omitting client_name raises ValidationError."""
        with pytest.raises(ValidationError):
            ClientCreate()


class TestClientUpdate:
    def test_all_none_by_default(self):
        """All fields are optional and default to None."""
        obj = ClientUpdate()
        assert obj.width is None
        assert obj.height is None
        assert obj.position is None

    def test_partial_update(self):
        """Only specified fields are set."""
        obj = ClientUpdate(width=1024)
        assert obj.width == 1024
        assert obj.height is None


class TestClientInfo:
    def test_valid(self):
        """All required fields accepted."""
        obj = ClientInfo(id=1, client_name="test", default_width=800, default_height=480, current_position=0)
        assert obj.id == 1
        assert obj.client_name == "test"

    def test_missing_field(self):
        """Omitting a required field raises ValidationError."""
        with pytest.raises(ValidationError):
            ClientInfo(id=1, client_name="test")


class TestConnectionInfo:
    def test_valid(self):
        """Round-trip with all required fields."""
        now = datetime.now()
        obj = ConnectionInfo(
            client="192.168.1.1",
            timestamp=now,
            method="GET",
            path="/next",
            processing_time_ms=12.5,
        )
        assert obj.client == "192.168.1.1"
        assert obj.quote_id is None

    def test_with_quote_id(self):
        """Optional quote_id is stored."""
        obj = ConnectionInfo(
            client="c",
            timestamp=datetime.now(),
            method="GET",
            path="/next",
            quote_id="abc-123",
            processing_time_ms=1.0,
        )
        assert obj.quote_id == "abc-123"


class TestServerStatus:
    def test_valid(self):
        """Round-trip with all required fields."""
        obj = ServerStatus(
            system={"platform": "linux"},
            app={"name": "ditto"},
            database={"quote_count": 10},
            config={"cache": False},
            recent_connections=[],
        )
        assert obj.system["platform"] == "linux"
        assert obj.recent_connections == []
