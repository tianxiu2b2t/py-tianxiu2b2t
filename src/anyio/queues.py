from collections import deque
from typing import (
    Generic, 
    TypeVar
)

import anyio


T = TypeVar("T")
    
class Queue(Generic[T]):
    def __init__(self, maxsize: int = 0) -> None:
        """
        Initialize the Queue with a maximum size.
        
        Args:
            maxsize (int): The maximum number of items the queue can hold.
                If set to 0, the queue has no size limit.
        """
        self._queue = deque()
        self._maxsize = maxsize
        self._putter_waiters: deque[anyio.Event] = deque()
        self._getter_waiters: deque[anyio.Event] = deque()

    async def put(self, item: T) -> None:
        """
        Put an item into the queue.

        If the queue is full (i.e., its size reaches maxsize), this method will wait
        until space becomes available.
        """
        while self._maxsize != 0 and len(self._queue) >= self._maxsize:
            event = anyio.Event()
            self._putter_waiters.append(event)
            await event.wait()
        self._queue.append(item)
        # Notify any waiting getters that an item is available
        if self._getter_waiters:
            self._getter_waiters.popleft().set()

    async def get(self) -> T:
        """
        Get an item from the queue.

        If the queue is empty, this method will wait until an item is available.
        """
        while not self._queue:
            event = anyio.Event()
            self._getter_waiters.append(event)
            await event.wait()
        item = self._queue.popleft()
        # Notify any waiting putters that space is available
        if self._putter_waiters:
            self._putter_waiters.popleft().set()
        return item
