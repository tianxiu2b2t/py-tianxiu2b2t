import abc
from collections import deque
from dataclasses import dataclass
import io
from typing import Any, Callable, Coroutine, TypeVar, Union

import anyio.streams.memory

from ...anyio.streams.abc import BufferedByteStream


Handler = Callable[['Stream'], Any]
WebSocketItem = io.BytesIO | io.StringIO
SendDataWithStreamId = Callable[[bytes, int], Coroutine[None, None, None]]
SendDataWithoutStreamId = Callable[[bytes], Coroutine[None, None, None]]
SendResponseWithStreamId = Callable[[int, 'Header', int], Coroutine[None, None, None]]
SendResponseWithoutStreamId = Callable[[int, 'Header'], Coroutine[None, None, None]]
SendData = Union[
    SendDataWithStreamId | SendDataWithoutStreamId
]
SendResponse = Union[
    SendResponseWithoutStreamId | SendResponseWithStreamId
]

WebSocketItemString = io.StringIO | str
WebSocketItemBytes = io.BytesIO | bytes

T = TypeVar('T')

class Header(
    list[tuple[bytes, bytes]]
):
    def find_all(self, key: bytes) -> list[bytes]:
        results = []
        for k, v in self:
            if k.lower() == key.lower():
                results.append(v)
        return results
    
    def find(self, key: bytes, default: T = None) -> T | bytes:
        for k, v in self:
            if k.lower() == key.lower():
                return v
        return default
    
    def append(self, key: bytes, value: bytes):
        super().append((key, value))

    def set(self, key: bytes, value: bytes):
        self.remove(key)
        self.append(key, value)

    def remove(self, key: bytes):
        new = []
        for k, v in self:
            if k.lower() != key.lower():
                new.append((k, v))
        self.clear()
        self.extend(new)
   
@dataclass
class Stream(
    metaclass=abc.ABCMeta
):
    stream_id: int
    headers: Header
    method: bytes
    target: bytes
    http_version: bytes
    tls: bool
    scheme: bytes
    client: tuple[str, int]
    server: tuple[str, int]
    reader: 'ReadStream'

class ReadStream[T]:
    def __init__(
        self,
    ):
        self._eof = False
        self._buffers: deque[T] = deque()
        self._read_waiters: deque[anyio.Event] = deque()
        self._feed_waiters: deque[anyio.Event] = deque()
        self._paused = False

    async def receive(self) -> T | None:
        if not self._buffers and not self._eof:
            fut = anyio.Event()
            self._read_waiters.append(fut)
            await fut.wait()

        if self._eof and not self._buffers:
            return None
        return self._buffers.popleft()
    
    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False
        while self._feed_waiters:
            self._feed_waiters.popleft().set()

    async def feed(self, data: T):
        if self._paused:
            fut = anyio.Event()
            self._feed_waiters.append(fut)
            await fut.wait()
        self._buffers.append(data)
        while self._read_waiters and self._buffers:
            self._read_waiters.popleft().set()

    def feed_eof(self):
        self._eof = True
        while self._read_waiters:
            self._read_waiters.popleft().set()

    def is_eof(self) -> bool:
        return self._eof

    def size(self) -> int:
        return len(self._buffers)

class Connection(
    metaclass=abc.ABCMeta
):
    def __init__(
        self,
        stream: BufferedByteStream,
        handler: Handler,
        tls: bool = False
    ):
        self.stream = stream
        self.handler = handler
        self.tls = tls

    @abc.abstractmethod
    async def process(self):
        ...