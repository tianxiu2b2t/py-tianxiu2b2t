from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

from .types import Header, ReadStream, Stream, WebSocketItem, SendDataWithStreamId, SendResponseWithStreamId, SendDataWithoutStreamId, SendResponseWithoutStreamId

ZERO_STREAM_ID = -1

async def _empty(*args):
    ...

@dataclass
class HTTPStream(Stream):
    raw_send_data: SendDataWithStreamId
    raw_send_response: SendResponseWithStreamId

    send_data: SendDataWithoutStreamId = field(default=_empty)
    send_response: SendResponseWithoutStreamId = field(default=_empty)

    sent_headers: bool = False
    response_completed: bool = False
    disconnected: bool = False
    abort: bool = False

    def init(self) -> None:
        async def wrapper_send_data(data: bytes):
            await self.raw_send_data(data, self.stream_id)

        async def wrapper_send_response(status_code: int, headers: Header):
            await self.raw_send_response(status_code, headers, self.stream_id)

        self.send_data = wrapper_send_data
        self.send_response = wrapper_send_response

@dataclass
class WebSocketStream(Stream):
    reader: 'WebSocketReadStream'
    accept: Callable[[str | None], Coroutine[Any, Any, None]]
    send_data: Callable[[WebSocketItem], Coroutine[Any, Any, None]]
    close: Callable[[int, str], Coroutine[Any, Any, None]]

class WebSocketReadStream(
    ReadStream[WebSocketItem]
):
    def __init__(
        self,
        aclose: Callable[[], Coroutine[Any, Any, None]]
    ):
        super().__init__()
        self._aclose = aclose

    async def aclose(self):
        await self._aclose()

class ByteReadStream(
    ReadStream[bytes]
):
    ...

    def size(self) -> int:
        return sum((
            len(buffer) for buffer in self._buffers
        ))
    
    async def receive(self, max_size: int = 65536) -> bytes | None:
        data = await super().receive()
        if data is None:
            return None
        
        data, remaining = data[:max_size], data[max_size:]
        if remaining:
            self._buffers.appendleft(remaining)

        return data