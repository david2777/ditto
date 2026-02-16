import asyncio
from typing import *
from pathlib import Path
from datetime import datetime

from loguru import logger
from notion_client import AsyncClient, APIResponseError

from ditto import constants, credentials

OUTPUT_DIR = Path(constants.OUTPUT_DIR).resolve()

notion_api = AsyncClient(auth=credentials.settings.notion_key)


class NotionError(RuntimeError):
    pass


rate_limit_event = asyncio.Event()
rate_limit_event.set()


async def api_request(api_func: Callable, *args, max_retries: int = 5, initial_backoff: int = 1, **kwargs) -> Any:
    """Make a Notion API request with automatic retry on rate limit errors."""
    retries = 0
    backoff = initial_backoff

    while retries <= max_retries:
        await rate_limit_event.wait()
        try:
            response = await api_func(*args, **kwargs)
            return response
        except APIResponseError as error:
            # If rate limit error. sleep and try again.
            if error.status == 429:
                retry_after = int(error.headers.get("Retry-After", backoff))
                logger.error(f"Rate limit exceeded. Retrying in {retry_after} seconds...")
                rate_limit_event.clear()
                await asyncio.sleep(retry_after)
                rate_limit_event.set()
                backoff *= 2
                retries += 1
            # If not a rate limit error, re-raise
            else:
                raise

    # If we've exhausted our retries, raise an error
    raise NotionError(f"Failed after {max_retries} retries due to rate limiting")


async def fetch_image_block(page_id: str) -> Optional[dict]:
    """Return the first image block from a page. Note that this is just the image block, not the actual image."""
    try:
        blocks = await api_request(notion_api.blocks.children.list, page_id)
    except APIResponseError as error:
        logger.exception(error)
        blocks = {'results': []}

    for block in blocks['results']:
        if block['type'] == 'image':
            return block['image']
    return None


class NotionPage:
    """Represents a processed page from Notion."""
    page_id: str
    quote: str
    title: str
    author: str
    image_url: Optional[str]
    image_expiry_time: Optional[datetime]

    def __init__(self, page: dict, image_block: Optional[dict] = None):
        self.page_id = page['id']
        quote = ''
        # Safely extract title
        if 'Name' in page['properties'] and 'title' in page['properties']['Name']:
            for part in page['properties']['Name']['title']:
                quote += part['plain_text']
        self.quote = quote

        self.title = "Unknown"
        if 'TITLE' in page['properties'] and page['properties']['TITLE']['rich_text']:
            self.title = page['properties']['TITLE']['rich_text'][0]['plain_text']

        self.author = "Unknown"
        if 'AUTHOR' in page['properties'] and page['properties']['AUTHOR']['rich_text']:
            self.author = page['properties']['AUTHOR']['rich_text'][0]['plain_text']

        self.image_url = None
        self.image_expiry_time = None

        if image_block:
            if image_block['type'] == 'file':
                self.image_url = image_block['file']['url']
                self.image_expiry_time = datetime.fromisoformat(image_block['file']['expiry_time'])
            elif image_block['type'] == 'external':
                self.image_url = image_block['external']['url']
                self.image_expiry_time = None

    def __repr__(self):
        return f'NotionPage[{self.page_id}]'


async def fetch_all_pages(database_id: str) -> List[dict]:
    """Fetch all pages from the Notion database."""
    logger.info(f'Fetching all pages from database {database_id}...')
    try:
        response = await api_request(notion_api.databases.query, database_id=database_id)
    except APIResponseError as error:
        logger.exception(error)
        return []

    results = response["results"]
    while response["has_more"]:
        try:
            response = await api_request(notion_api.databases.query, database_id=database_id,
                                         start_cursor=response["next_cursor"])
            results.extend(response["results"])
        except APIResponseError as error:
            logger.exception(error)
            break
            
    logger.info(f'Fetched {len(results)} raw pages.')
    return results


async def sync_notion_db(quote_manager):
    """
    Syncs Notion data to the SQLite database via QuoteManager.
    
    Args:
        quote_manager: Instance of QuoteManager (from ditto.database)
    """
    logger.info("Starting Notion sync...")
    
    raw_pages = await fetch_all_pages(credentials.settings.notion_database_id)
    
    synced_count = 0
    skipped_count = 0
    active_ids = set()

    for page in raw_pages:
        # Check simple filters (not archived, not in trash)
        # And check "DISPLAY" or equivalent properties if they exist
        is_active = True
        if page.get("archived") or page.get("in_trash"):
            is_active = False
        
        # Check DISPLAY checkbox if it exists
        if 'DISPLAY' in page['properties'] and 'checkbox' in page['properties']['DISPLAY']:
            if not page['properties']['DISPLAY']['checkbox']:
                is_active = False
                
        if not is_active:
            skipped_count += 1
            continue
            
        # Fetch image block which contains the image URL and expiry time
        image_block = await fetch_image_block(page['id'])
        
        notion_page = NotionPage(page, image_block)
        
        # Upsert into QuoteManager
        quote_data = {
            "id": notion_page.page_id,
            "db_id": notion_page.page_id,
            "content": notion_page.quote,
            "title": notion_page.title,
            "author": notion_page.author,
            "image_url": notion_page.image_url,
            "image_expiry": notion_page.image_expiry_time
        }
        
        quote_manager.upsert_quote(quote_data)
        active_ids.add(notion_page.page_id)
        synced_count += 1

    # Cleanup: Remove quotes from DB that are not in active_ids
    existing_ids = set(quote_manager.get_all_quote_ids())
    to_delete = existing_ids - active_ids
    
    deleted_count = 0
    for quote_id in to_delete:
        quote_manager.delete_quote(quote_id)
        deleted_count += 1

    logger.info(f"Sync complete. Synced: {synced_count}, Skipped: {skipped_count}, Deleted: {deleted_count}")
