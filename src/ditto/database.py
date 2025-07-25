import asyncio
import requests
from enum import Enum
from pathlib import Path
from random import Random
from datetime import datetime, timezone
from typing import Optional, Callable, Dict, List

from loguru import logger
from notion_client import AsyncClient, APIResponseError

from ditto import constants, secrets, image_processing
from ditto.utilities.timer import Timer

OUTPUT_DIR = constants.OUTPUT_DIR
OUTPUT_DIR = Path(OUTPUT_DIR).resolve()

notion_client = AsyncClient(auth=secrets.NOTION_KEY)


class QueryDirection(Enum):
    FORWARD = 1
    REVERSE = 2
    RANDOM = 3


class NotionClientError(RuntimeError):
    pass


rate_limit_event = asyncio.Event()
rate_limit_event.set()


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
    raise NotionClientError(f"Failed after {max_retries} retries due to rate limiting")


class Client:
    """Client class used to manage order and index in the quote list per client.

    Attributes:
        name (str): The name of the client.
        _cache_size (int): The size of the page cache.
        _index (int): The current position in the order list.
        _page_indices (List[int]): A per-client shuffled list of indices to allow each client to return pages in their
        own random order.
        _random (Random): The random number generator to use, created per client instance. Allows random sorting to be
        predictable.

    """
    name: str
    _cache_size: int
    _index: int = 0
    _page_indices: List[int]
    _random: Random

    def __init__(self, name: str, cache_size: int):
        """Initialize a new client instance based on the given name and cache size.

        Args:
            name (str): The name of the client.
            cache_size (int): The size of the page cache.
        """
        self.name = name
        self._cache_size = cache_size
        self._random = Random()
        self.update_cache_size(self._cache_size)
        logger.debug(f'{self}: New Client Instance with size {self._cache_size}')

    def __repr__(self):
        return f'Client[{self.name}]'

    def update_cache_size(self, cache_size: int):
        """Update the cache size, refreshing the indices list and updating the index.

        Args:
            cache_size (int): The size of the page cache.

        Returns:
            None
        """
        logger.debug(f'{self}: Updating cache size to {cache_size}')
        self._cache_size = cache_size
        self._page_indices = list(range(cache_size))
        self._random.shuffle(self._page_indices)
        self._index = min(self._index, self._cache_size - 1)

    def _move_index(self, direction: QueryDirection):
        """Move the index in a given direction.

        Args:
            direction (QueryDirection): The direction to move.

        Returns:
            None
        """
        before = self._index
        if direction == QueryDirection.FORWARD:
            self._index += 1
            if self._index > self._cache_size - 1:
                self._index = 0
        elif direction == QueryDirection.REVERSE:
            self._index -= 1
            if self._index < 0:
                self._index = self._cache_size - 1
        elif direction == QueryDirection.RANDOM:
            self._index = self._random.randint(0, self._cache_size - 1)
        else:
            raise ValueError(f'Invalid direction: {direction}')
        logger.debug(f"{self}: Moved index in {direction}: {before} ==> {self._index}")

    def get_item_index(self, direction: Optional[QueryDirection]) -> int:
        """Return an index in the order list for the given direction, this index is used to pull a quote from the master
        quote cache.

        Args:
            direction (Optional[QueryDirection]): The direction to get the index.

        Returns:
            int: The index in the order list for the given direction.
        """
        if direction:
            self._move_index(direction)
        result = self._page_indices[self._index]
        logger.debug(f'{self}: Got page index {result} from internal index {self._index}')
        return result


class NotionQuote:
    """Dataclass representing a single quote item from Notion.

    Attributes:
        page_id (str): The page ID for teh quote.
        quote (str): The actual quote text.
        title (str): The title of the book the quote belongs to.
        author (str): The author of the book the quote belongs to.
        image_expiry_time (Optional[datetime]): The expiry time of the image URL for internal files.
        _image_url (Optional[str]): The first image URL in the page if the page has any image urls. Note that these URLs
        expire and should be accessed via the `get_image_url` function which handles refreshing.

    """
    page_id: str
    quote: str
    title: str
    author: str
    image_expiry_time: Optional[datetime]
    _image_url: Optional[str]

    def __init__(self, page: dict, image_block: Optional[dict] = None):
        self.page_id = page['id']
        self.quote = page['properties']['Name']['title'][0]['plain_text']
        self.title = page['properties']['Title']['rich_text'][0]['plain_text']
        self.author = page['properties']['Author']['rich_text'][0]['plain_text']
        if image_block:
            if image_block['type'] == 'file':
                self._image_url = image_block['file']['url']
                self.image_expiry_time = datetime.fromisoformat(image_block['file']['expiry_time'])
            elif image_block['type'] == 'external':
                self._image_url = image_block['file']['url']
                self.image_expiry_time = None
        
    def __hash__(self):
        return hash(self.page_id)
    
    def __repr__(self):
        return f'NotionQuote[{self.page_id}]'

    async def get_image_url(self) -> Optional[str]:
        """Returns the image URL from the first image block, handling refreshing the URL if the link has expired.

        Returns:
            Optional[str]: The image URL if one exists, None otherwise.
        """
        if not self._image_url or (self.image_expiry_time and datetime.now(timezone.utc) > self.image_expiry_time):
            # Only refresh if we don't have a URL or if it's expired
            image_block = await NotionDatabaseManager.fetch_image_block(self.page_id)
            if image_block['type'] == 'file':
                self._image_url = image_block['file']['url']
                self.image_expiry_time = datetime.fromisoformat(image_block['file']['expiry_time'])
            elif image_block['type'] == 'external':
                self._image_url = image_block['file']['url']
                self.image_expiry_time = None

        return self._image_url

    @property
    def image_path_raw(self) -> Path:
        """Returns the path for the "raw" unprocessed image on disk weather or not it exits.

        Returns:
            Path: The path for the "raw" unprocessed image on disk.
        """
        return OUTPUT_DIR / 'raw' / f'{self.page_id}.jpg'

    @property
    def image_path_processed(self) -> Path:
        """Returns the path for the processed image on disk weather or not it exits.

        Returns:
            Path: The path for the processed image on disk.
        """
        return OUTPUT_DIR / 'processed' / f'{self.page_id}.jpg'

    async def download_image(self) -> bool:
        """Attempt to download the image from the image URL and store it as the raw image.

        Returns:
            bool: True if the image was downloaded, False otherwise.
        """
        image_url = await self.get_image_url()
        if not image_url:
            return False

        t = Timer()
        logger.debug(f'Downloading image at {image_url}...')
        with requests.Session() as session:
            response = session.get(image_url)
            if response.status_code == 200:
                self.image_path_raw.parent.mkdir(parents=True, exist_ok=True)
                with open(self.image_path_raw.as_posix(), "wb") as f:
                    f.write(response.content)
        logger.debug(f'Took {t.get_elapsed_time()} to download image')
        return True

    async def process_image(self):
        """Processed the image and saved out the processed image. If an image does not exist, use a fallback image.

        Returns:
            None
        """
        if self.image_path_processed.exists():
            return

        if not self.image_path_raw.is_file():
            if self._image_url:
                await self.download_image()
            else:
                raise NotImplementedError(f"Fallback Image Not Implemented")
        t = Timer()
        image = image_processing.DittoImage(self.image_path_raw.as_posix())
        image.initial_resize()
        image.blur()
        image.add_text(self.quote, self.title, self.author)
        self.image_path_processed.parent.mkdir(parents=True, exist_ok=True)
        image.write(self.image_path_processed.as_posix())
        logger.debug(f'Took {t.get_elapsed_time()} to process image: {self.image_path_processed.as_posix()}')


class NotionDatabaseManager:
    """Simple Notion Database Manager which handles querying the database and caching results.

    Attributes:
        _page_id_cache (List[str]): An ordered list of page IDs. Since Notion only returns 100 items at a time and has
        a rate limit of around 3 requests per second it's better to cache a list of all possible page IDs.
        _quote_item_cache (Dict[str, NotionQuote]): A cache of all quote items stored as {page_id: NotionQuote}. Items
        are inserted into the cache every time the data is queried.
        _clients (Dict[str, Client]): A cache of all clients stored as {client_name: Client}. Items

    """
    _page_id_cache: List[str] = []
    _quote_item_cache: Dict[str, NotionQuote] = {}
    _clients: Dict[str, Client] = {}

    def __init__(self, database_id: str):
        self.database_id = database_id

    def clear_page_id_cache(self):
        """Clear the page ID cache, forcing IDs ton be refreshed on the next query.

        Returns:
            None
        """
        self._page_id_cache.clear()

    def clear_item_cache(self):
        """Clear the item cache, forcing items to be re-generated starting on the next query.

        Returns:
            None
        """
        self._quote_item_cache.clear()

    async def update_page_id_cache(self):
        """Update the page ID cache by querying the database and caching results.

        Returns:
            None
        """
        logger.info('Updating cache')
        t = Timer()

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

        previous_count = len(self._page_id_cache)
        self.clear_page_id_cache()
        for db_item in results:
            self._page_id_cache.append(db_item['id'])

        new_count = len(self._page_id_cache)
        client_count = 0
        if new_count != previous_count:
            for client in self._clients.values():
                client_count += 1
                client.update_cache_size(new_count)

        if client_count:
            logger.info(f'Cache and {client_count} clients updated with {new_count} items '
                        f'in {t.get_elapsed_time()} seconds')
        else:
            logger.info(f'Cache updated with {new_count} items in {t.get_elapsed_time()} seconds')

    @staticmethod
    async def fetch_image_block(page_id: str) -> Optional[dict]:
        """Return the first image block from a page.

        Args:
            page_id (str): The page ID.

        Returns:
            Optional[dict]: The image block if one exists, None otherwise.
        """
        t = Timer()
        try:
            blocks = await api_request(notion_client.blocks.children.list, page_id)
        except APIResponseError as error:
            logger.exception(error)
            blocks = {'results': []}

        for block in blocks['results']:
            block_type = block['type']
            if block_type == 'image':
                image_block = block['image']
                logger.debug(f'Took {t.get_elapsed_time()} to fetch image block for {page_id}')
                return image_block

        logger.debug(f'Took {t.get_elapsed_time()} to fail to fetch image block for {page_id}')
        return None

    async def fetch_page(self, page_id: str) -> Optional[NotionQuote]:
        """Fetch an individual page from the database and return its contents as a NotionQuote.

        Args:
            page_id (str): The ID of the page to fetch.

        Returns:
            Optional[NotionQuote]: An item from the database if found, None otherwise.
        """
        t = Timer()
        try:
            return self._quote_item_cache[page_id]
        except KeyError:
            pass

        try:
            page = await api_request(notion_client.pages.retrieve, page_id=page_id)
        except APIResponseError as error:
            logger.exception(error)
            return None

        try:
            image_block = await self.fetch_image_block(page_id)
        except APIResponseError as error:
            logger.exception(error)
            return None

        logger.info(f'Next item retrieved: {page_id}')
        item = NotionQuote(page, image_block)
        self._quote_item_cache[page_id] = item
        logger.info(f'Took {t.get_elapsed_time()} to fetch page item for {page_id}')
        return item

    async def _get_item(self, client_name: str, direction: QueryDirection) -> Optional[NotionQuote]:
        """Return an item from the database in the specified direction for the specified client. None if database is
        empty.

        Args:
            client_name (str): The client host name.
            direction (QueryDirection): The direction to fetch.

        Returns:
            Optional[NotionQuote]: An item from the database if found, None otherwise.
        """
        logger.info(f'Getting {direction} item for {client_name}')

        if not self._page_id_cache:
            await self.update_page_id_cache()

        if not self._page_id_cache:
            raise NotionClientError('Unable to update cache')

        try:
            client_instance = self._clients[client_name]
        except KeyError:
            client_instance = Client(client_name, len(self._page_id_cache))
            self._clients[client_name] = client_instance

        index = client_instance.get_item_index(direction)

        page_id = self._page_id_cache[index]
        return await self.fetch_page(page_id)

    async def get_next_item(self, client_name: str) -> Optional[NotionQuote]:
        """Return the next item from the database based on the page ID cache.

        Args:
            client_name (str): The client host name.

        Returns:
            Optional[NotionQuote]: The next item from the database if the cache exists, None otherwise.
        """
        return await self._get_item(client_name, QueryDirection.FORWARD)

    async def get_previous_item(self, client_name: str) -> Optional[NotionQuote]:
        """Return the previous item from the database based on the page ID cache.

        Args:
            client_name (str): The client host name.

        Returns:
            Optional[NotionQuote]: The previous item from the database if the cache exists, None otherwise.
        """
        return await self._get_item(client_name, QueryDirection.REVERSE)

    async def get_random_item(self, client_name: str) -> Optional[NotionQuote]:
        """Return a random item from the database based on the page ID cache.

        Args:
            client_name (str): The client host name.

        Returns:
            Optional[NotionQuote]: The random item from the database if the cache exists, None otherwise.
        """
        return await self._get_item(client_name, QueryDirection.RANDOM)