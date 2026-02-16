import sys
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add src to path
sys.path.append(str(Path.cwd() / "src"))

from ditto.database import QuoteManager, Quote, Client, QueryDirection
from ditto import constants

def test_database():
    print("Initializing QuoteManager...")
    # Use in-memory DB for testing
    mgr = QuoteManager("sqlite:///:memory:")
    
    # 1. Upsert Quotes
    print("Upserting quotes...")
    quotes = [
        {"id": "q1", "db_id": "db1", "content": "Quote 1", "title": "Title 1", "author": "Author 1"},
        {"id": "q2", "db_id": "db2", "content": "Quote 2", "title": "Title 2", "author": "Author 2"},
        {"id": "q3", "db_id": "db3", "content": "Quote 3", "title": "Title 3", "author": "Author 3"},
    ]
    for q in quotes:
        mgr.upsert_quote(q)
        
    with mgr.Session() as session:
        count = session.query(Quote).count()
        print(f"Quotes in DB: {count}")
        assert count == 3
        
    # 2. Register Client
    print("Registering client...")
    client_name = "test_client"
    mgr.register_client(client_name)
    
    # 3. Test Navigation
    print("Testing Navigation...")
    
    # Trigger sync logic manually as they are separate now in my implementation
    # navigate/get_quote calls sync_new_quotes internally
    
    # Get Current (should be first item, idx 0)
    q = mgr.get_quote(client_name, QueryDirection.CURRENT)
    print(f"Current: {q.id if q else None}")
    assert q is not None
    
    # Get Next (should be idx 1)
    q = mgr.get_quote(client_name, QueryDirection.FORWARD)
    print(f"Next: {q.id if q else None}")
    assert q is not None
    assert q.id != quotes[0]['id'] # Should likely be different if shuffled, but could be same if shuffle happens to match. 
    # Actually, default implementation shuffles.
    
    # Get Previous (should be back to idx 0)
    q = mgr.get_quote(client_name, QueryDirection.REVERSE)
    print(f"Previous: {q.id if q else None}")
    assert q is not None
    
    # 4. Image Processing Mock
    print("Testing Image Processing (Mocked)...")
    q = mgr.get_quote(client_name, QueryDirection.CURRENT)
    q.image_url = "http://example.com/image.jpg"
    
    with patch('requests.Session.get') as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'fake_image_data'
        mock_get.return_value = mock_response
        
        with patch('ditto.image_processing.process_image') as mock_process:
            mock_process.return_value = True
            
            # Create a localized output dir for test to avoid messing up real data
            # But Quote uses global OUTPUT_DIR. 
            # We can just verify it calls what we expect.
            
            # Actually, let's just test `download_image`
            res = q.download_image()
            print(f"Download result: {res}")
            assert res is True
            
    print("Verification passed!")

if __name__ == "__main__":
    test_database()
