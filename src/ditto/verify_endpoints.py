import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Add src to path
sys.path.append(str(Path.cwd() / "src"))

from fastapi.testclient import TestClient
from ditto.main import app
from ditto import database, notion

client = TestClient(app)

def test_endpoints():
    print("Testing Endpoints...")
    
    # Mock Notion Sync to avoid startup error or actual network call
    app.dependency_overrides = {}
    
    # Needs to mock notion.sync_notion_db because it runs on startup
    # However, TestClient triggers startup events.
    # We can patch it.
    
    with patch("ditto.notion.sync_notion_db", new_callable=AsyncMock) as mock_sync:
        with TestClient(app) as client:
            # 1. Test Root
            print("Testing / ...")
            response = client.get("/")
            assert response.status_code == 200
            data = response.json()
            assert data["application"] == "ditto"
            print(f"Root response: {data}")
            
            # 2. Test Current (with empty DB)
            print("Testing /current (empty)...")
            # Ensure DB is empty or clean
            # We can rely on in-memory or file DB. 
            # Ideally we'd insert some data first manually into the QuoteManager used by main
            
            # Inject data
            from ditto.main import quote_manager
            quote_manager.upsert_quote({
                "id": "test_q", "db_id": "test_db", "content": "Test Quote", 
                "title": "T", "author": "A", "image_url": "http://example.com/img.jpg"
            })
            
            # Mock process_image to return a fake path without doing work
            with patch("ditto.database.Quote.process_image") as mock_process:
                # Create a dummy file
                dummy_path = Path("test_image.jpg")
                dummy_path.touch()
                mock_process.return_value = dummy_path
                
                print("Testing /current...")
                response = client.get("/current")
                if response.status_code != 200:
                    print(response.json())
                assert response.status_code == 200
                assert response.headers["content-type"] == "image/jpeg"
                
                # Cleanup
                if dummy_path.exists():
                    dummy_path.unlink()
                    
            print("Endpoint verification passed!")

if __name__ == "__main__":
    test_endpoints()
