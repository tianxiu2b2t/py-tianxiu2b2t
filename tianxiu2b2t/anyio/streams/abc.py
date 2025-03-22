from collections import deque
from typing import Callable, Mapping, TypeVar
import anyio.abc

T_Attr = TypeVar('T_Attr')

class BufferedByteStream(
    anyio.abc.ByteStream,
):
    def __init__(
        self,
        stream: anyio.abc.AnyByteStream
    ):
        self.pre_buffers = deque()
        self.pre_receives = deque()
        self.buffers = deque()
        self.stream = stream
    
    async def pre_receive(self, max_bytes: int = 65536) -> bytes:
        if len(self.pre_buffers) > 0:
            return _read_bytes(
                self.pre_buffers.popleft(), max_bytes, self.pre_buffers
            )
        buf = await self.stream.receive()
        self.pre_receives.append(buf)
        return _read_bytes(buf, max_bytes, self.pre_buffers)
        
    async def pre_readexactly(self, n: int) -> bytes:
        buf = b''
        while len(buf) < n:
            buf += await self.pre_receive(n - len(buf))
        return buf

    async def pre_readuntil(self, separator: bytes) -> bytes:
        buf = b''
        while separator not in buf:
            buf += await self.pre_receive()
        data, buf = buf.split(separator, 1)
        self.pre_buffers.appendleft(buf)
        return data + separator

    async def receive(self, max_bytes: int = 65536) -> bytes:
        if len(self.buffers) > 0:
            return _read_bytes(
                self.buffers.popleft(), max_bytes, self.buffers
            )

        if self.pre_receives:
            return _read_bytes(
                self.pre_receives.popleft(), max_bytes, self.pre_buffers
            )
        return _read_bytes(await self.stream.receive(), max_bytes, self.buffers)
        
    async def readexactly(self, n: int) -> bytes:
        buf = b''
        while len(buf) < n:
            buf += await self.receive(n - len(buf))
        return buf
    
    async def readuntil(self, separator: bytes) -> bytes:
        buf = b''
        while separator not in buf:
            buf += await self.receive()
        data, buf = buf.split(separator, 1)
        self.buffers.appendleft(buf)
        return data + separator

    async def send(self, data: bytes) -> None:
        await self.stream.send(data)

    async def aclose(self) -> None:
        await self.stream.aclose()

    async def send_eof(self) -> None:
        return await self.stream.send_eof()

    @property
    def extra_attributes(self) -> Mapping[T_Attr, Callable[[], T_Attr]]:
        """
        A mapping of the extra attributes to callables that return the corresponding
        values.

        If the provider wraps another provider, the attributes from that wrapper should
        also be included in the returned mapping (but the wrapper may override the
        callables from the wrapped instance).

        """
        return self.stream.extra_attributes


def _read_bytes(
    buffer: bytes,
    length: int,
    buffers: deque[bytes],
):
    if len(buffer) >= length:
        buf, remianing = buffer[:length], buffer[length:]
        buffers.appendleft(remianing)
        return buf
    return buffer