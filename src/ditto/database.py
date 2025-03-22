import random
import requests
import asyncio
from pathlib import Path
from typing import Optional, Callable

from notion_client import AsyncClient, APIResponseError
from loguru import logger

from ditto import constants, secrets, image_processing

OUTPUT_DIR = constants.OUTPUT_DIR or 'test_images/resize'
OUTPUT_DIR = Path(OUTPUT_DIR).resolve()

notion_client = AsyncClient(auth=secrets.NOTION_KEY)


class NotionClientError(RuntimeError):
    pass


async def api_request(api_func: Callable, *args, max_retries:int = 5, initial_backoff:int = 1, **kwargs) -> dict:
    """Make a Notion API request with automatic retry on rate limit errors.

    Args:
        api_func (Callable): The Notion API function to call.
        *args: Positional arguments for the API function.
        max_retries (int): Maximum number of retries.
        initial_backoff (int): Initial backoff time in seconds (will be exponentially increased).
        **kwargs: Keyword arguments for the API function.

    Returns:
        dict: API response.

    Raises:
        APIResponseError: If a non-rate limit error occurs.
        NotionClientError: If the error persists after max_retries.
    """
    retries = 0
    backoff = initial_backoff

    while retries <= max_retries:
        try:
            response = await api_func(*args, **kwargs)
            return response
        except APIResponseError as error:
            # If rate limit error. sleep and try again.
            if error.status == 429:
                retry_after = int(error.headers.get("Retry-After", backoff))
                logger.error(f"Rate limit exceeded. Retrying in {retry_after} seconds...")
                await asyncio.sleep(retry_after)
                backoff *= 2
                retries += 1
            # If not a rate limit error, re-raise
            else:
                raise

    # If we've exhausted our retries, raise an error
    raise NotionClientError(f"Failed after {max_retries} retries due to rate limiting")


class NotionQuote:
    page_id: str
    quote: str
    title: str
    author: str
    image_url: Optional[str]

    def __init__(self, page_id: str, quote: str, title: str, author: str, image_url: Optional[str] = None):
        self.page_id = page_id
        self.quote = quote
        self.title = title
        self.author = author
        self.image_url = image_url
        
    def __hash__(self):
        return hash(self.page_id)
    
    def __repr__(self):
        return f'NotionQuote[{self.page_id}]'

    @property
    def image_path_raw(self) -> Path:
        return OUTPUT_DIR / 'raw' / f'{self.page_id}.jpg'

    @property
    def image_path_processed(self) -> Path:
        return OUTPUT_DIR / 'processed' / f'{self.page_id}.jpg'

    async def download_image(self) -> bool:
        if not self.image_url:
            return False

        response = requests.get(self.image_url)
        if response.status_code == 200:
            self.image_path_raw.parent.mkdir(parents=True, exist_ok=True)
            with open(self.image_path_raw.as_posix(), "wb") as f:
                f.write(response.content)
        return True

    async def process_image(self) -> bool:
        if self.image_path_processed.exists():
            return True

        if not self.image_path_raw.is_file():
            if self.image_url:
                await self.download_image()
            else:
                # TODO: Fallback Image
                pass

        image = image_processing.DittoImage(self.image_path_raw.as_posix())
        image.initial_resize()
        image.blur()
        image.add_text(self.quote, self.title, self.author)
        self.image_path_processed.parent.mkdir(parents=True, exist_ok=True)
        image.write(self.image_path_processed.as_posix())
        return True


class NotionDatabaseManager:
    _id_cache = []
    _item_cache = {}

    def __init__(self, database_id: str):
        self.database_id = database_id

    def clear_id_cache(self):
        self._id_cache.clear()

    def clear_item_cache(self):
        self._item_cache.clear()

    async def update_id_cache(self):
        logger.info('Updating cache')

        try:
            response = await api_request(notion_client.databases.query, database_id=self.database_id)
        except APIResponseError as error:
            logger.exception(error)
            return

        results = response["results"]
        while response["has_more"]:
            try:
                response = await api_request(notion_client.databases.query, database_id=self.database_id,
                                             start_cursor=response["next_cursor"])
                results.extend(response["results"])
            except APIResponseError as error:
                logger.exception(error)
                return

        if not results:
            logger.error(f'No results found for {self.database_id}')
            return

        logger.info('Clearing cache...')
        self.clear_id_cache()
        for db_item in results:
            self._id_cache.append(db_item['id'])

        random.shuffle(self._id_cache)
        logger.info(f'Cache updated with {len(self._id_cache)} items')

    async def fetch_page(self, page_id: str) -> Optional[NotionQuote]:
        try:
            return self._item_cache[page_id]
        except KeyError:
            pass

        try:
            page = await api_request(notion_client.pages.retrieve, page_id=page_id)
        except APIResponseError as error:
            logger.exception(error)
            return None

        quote = page['properties']['Name']['title'][0]['plain_text']
        title = page['properties']['Title']['rich_text'][0]['plain_text']
        author = page['properties']['Author']['rich_text'][0]['plain_text']

        try:
            blocks = await api_request(notion_client.blocks.children.list, page_id)
        except APIResponseError as error:
            logger.exception(error)
            blocks = {'results': []}

        image_url = None
        for block in blocks['results']:
            block_type = block['type']
            if block_type == 'image':
                image_block = block['image']
                image_type = image_block['type']  # Can be "external" or "file"

                if image_type == 'external':
                    image_url = image_block['external']['url']
                    logger.info(f'External Image URL: {image_url}')
                elif image_type == 'file':
                    image_url = image_block['file']['url']
                    logger.info(f'File Image URL: {image_url}')

        logger.info(f'Next item retrieved: {page_id}')
        item = NotionQuote(page_id, quote, title, author, image_url)
        self._item_cache[page_id] = item
        return item

    async def get_next_item(self):
        logger.info('Getting next item')
        if not self._id_cache:
            await self.update_id_cache()

        if not self._id_cache:
            raise NotionClientError('Unable to update cache')

        page_id = self._id_cache.pop(0)
        self._id_cache.append(page_id)
        return await self.fetch_page(page_id)

    async def get_previous_item(self):
        logger.info('Getting previous item')
        if not self._id_cache:
            await self.update_id_cache()

        if not self._id_cache:
            raise NotionClientError('Unable to update cache')

        page_id = self._id_cache[-1]
        return await self.fetch_page(page_id)
