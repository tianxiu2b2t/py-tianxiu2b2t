from collections import deque
from typing import Any, Callable, Mapping, TypeVar, final, overload
from anyio import TypedAttributeLookupError
import anyio.abc

T_Attr = TypeVar('T_Attr')
T_Value = TypeVar('T_Value')
T_Default = TypeVar("T_Default")
undefined = object()

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
        if len(self.pre_receives) > 0:
            return _read_bytes(
                self.pre_receives.popleft(), max_bytes, self.pre_receives
            )
        if len(self.buffers) > 0:
            return _read_bytes(
                self.buffers.popleft(), max_bytes, self.buffers
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
    
    @overload
    def extra(self, attribute: T_Attr) -> T_Attr: ...

    @overload
    def extra(self, attribute: T_Attr, default: T_Default) -> T_Attr | T_Default: ...

    @final
    def extra(self, attribute: Any, default: object = undefined) -> object:
        """
        extra(attribute, default=undefined)

        Return the value of the given typed extra attribute.

        :param attribute: the attribute (member of a :class:`~TypedAttributeSet`) to
            look for
        :param default: the value that should be returned if no value is found for the
            attribute
        :raises ~anyio.TypedAttributeLookupError: if the search failed and no default
            value was given

        """
        try:
            getter = self.extra_attributes[attribute]
        except KeyError:
            if default is undefined:
                raise TypedAttributeLookupError("Attribute not found") from None
            else:
                return default

        return getter()
    
    @property
    def local_addr(self) -> tuple[str, int]:
        addr = self.extra(anyio.abc.SocketAttribute.local_address)
        if isinstance(addr, tuple):
            return addr[:2]
        return addr, self.extra(anyio.abc.SocketAttribute.local_port)
    
    @property
    def remote_addr(self) -> tuple[str, int]:
        addr = self.extra(anyio.abc.SocketAttribute.remote_address)
        if isinstance(addr, tuple):
            return addr[:2]
        return addr, self.extra(anyio.abc.SocketAttribute.remote_port)

class ExtraMapping(Mapping):
    def __init__(self, data: dict):
        self._extra = data

    def __getitem__(self, key: T_Attr) -> Callable[[], T_Attr]:
        return self._extra[key]

    def __setitem__(self, key: T_Attr, value: Callable[[], T_Attr]) -> None:
        self._extra[key] = value

    def __len__(self) -> int:
        return len(self._extra)
    
    def __iter__(self):
        return iter(self._extra)
    
    def __repr__(self) -> str:
        return f"ExtraMapping({self._extra!r})"
    
class ExtraListener(
    anyio.abc.Listener
):
    def __init__(
        self,
        listener: anyio.abc.Listener,
    ):
        self._listener = listener

    @property
    def extra_attributes(self) -> Mapping[T_Attr, Callable[[], T_Attr]]:
        """
        A mapping of the extra attributes to callables that return the corresponding
        values.

        If the provider wraps another provider, the attributes from that wrapper should
        also be included in the returned mapping (but the wrapper may override the
        callables from the wrapped instance).

        """
        return self._listener.extra_attributes
    
    @overload
    def extra(self, attribute: T_Attr) -> T_Attr: ...

    @overload
    def extra(self, attribute: T_Attr, default: T_Default) -> T_Attr | T_Default: ...

    @final
    def extra(self, attribute: Any, default: object = undefined) -> object:
        """
        extra(attribute, default=undefined)

        Return the value of the given typed extra attribute.

        :param attribute: the attribute (member of a :class:`~TypedAttributeSet`) to
            look for
        :param default: the value that should be returned if no value is found for the
            attribute
        :raises ~anyio.TypedAttributeLookupError: if the search failed and no default
            value was given

        """
        try:
            getter = self.extra_attributes[attribute]
        except KeyError:
            if default is undefined:
                raise TypedAttributeLookupError("Attribute not found") from None
            else:
                return default

        return getter()
    
    @property
    def local_addr(self) -> tuple[str, int]:
        addr = self.extra(anyio.abc.SocketAttribute.local_address)
        if isinstance(addr, tuple):
            return addr[:2]
        return addr, self.extra(anyio.abc.SocketAttribute.local_port)


def _read_bytes(
    buffer: bytes,
    length: int,
    buffers: deque[bytes],
):
    if len(buffer) > length:
        buf, remianing = buffer[:length], buffer[length:]
        buffers.appendleft(remianing)
        return buf
    return buffer