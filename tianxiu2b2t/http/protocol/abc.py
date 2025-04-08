import abc
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable, Coroutine, Optional

import anyio.abc

from ...anyio.streams.abc import BufferedByteStream
from ...anyio.future import Future

Headers = list[tuple[bytes, bytes]]
More_data = bool

class Stream(
    metaclass=abc.ABCMeta
):
    def __init__(
        self,
    ):
        self.buffer: bytes = b""

    @property
    def size(self) -> int:
        return len(self.buffer)

class ReadStream(
    Stream
):
    def __init__(
        self,
    ):
        super().__init__()
        self.waiters: deque[Future] = deque()
        self._aborted = False
        self._eof = False

    def abort(self):
        self._aborted = True
        while self.waiters:
            fut = self.waiters.popleft()
            fut.set_result(None)

    @property
    def aborted(self) -> bool:
        return self._aborted

    async def receive(self, max_bytes: int = 65536) -> bytes:
        if self._aborted:
            raise Exception("Stream aborted")
        if not self.buffer and not self._eof:
            fut = Future()
            self.waiters.append(fut)
            await fut.wait()
        data = self.buffer[:max_bytes]
        self.buffer = self.buffer[max_bytes:]
        return data
    
    def feed(self, data: bytes):
        self.buffer += data
        while self.waiters and self.buffer:
            fut = self.waiters.popleft()
            fut.set_result(None)

    def eof(self):
        self._eof = True
        while self.waiters:
            fut = self.waiters.popleft()
            fut.set_result(None)

    @property
    def is_eof(self) -> bool:
        return self._eof
@dataclass
class StreamConnection(
    metaclass=abc.ABCMeta
):
    method: bytes
    headers: Headers
    target: bytes
    http_version: bytes
    stream_id: int
    read_stream: ReadStream
    send_response: Callable[[int, Headers, int], Coroutine]
    send_data: Callable[[bytes, More_data, int], Coroutine]

class Connection(
    metaclass=abc.ABCMeta
):
    def __init__(
        self,
        stream: BufferedByteStream,
        handle: Callable[[StreamConnection], Any],
        task_group: Optional[anyio.abc.TaskGroup] = None
    ):
        self.stream = stream
        self.task_group: anyio.abc.TaskGroup = task_group # type: ignore
        self.handle = handle
    
    @abc.abstractmethod
    async def initialize(self):
        if self.task_group is None:
            self.task_group = anyio.create_task_group()
            await self.task_group.__aenter__()

        
    @abc.abstractmethod
    async def receive_data(self, data: bytes):
        ...
        
