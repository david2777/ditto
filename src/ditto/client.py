from random import Random
from typing import Optional, List

from loguru import logger

from ditto.constants import QueryDirection


class DittoClientError(RuntimeError):
    pass


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
        if direction == QueryDirection.CURRENT:
            pass
        elif direction == QueryDirection.FORWARD:
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