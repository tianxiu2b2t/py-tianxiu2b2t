from collections import deque
from dataclasses import dataclass
import enum
from functools import wraps
import re
import ssl
from typing import Any, Callable, Mapping, Optional, TypeVar
import anyio.abc
import anyio.streams.tls

from .abc import BufferedByteStream, ExtraListener, T_Attr, ExtraMapping

@dataclass(eq=False)
class TLSExtraData:
    hostname: str | None = None
    ssl_context: ssl.SSLContext | None = None
    version: ssl.TLSVersion | None = None

class TLSExtraAttributes(enum.Enum):
    HOSTNAME = "hostname"
    SSL_CONTEXT = "ssl_context"
    VERSION = "version"

class TLSStream(
    BufferedByteStream
):
    def __init__(
        self,
        stream: anyio.abc.AnyByteStream,
        extra: TLSExtraData,
    ):
        super().__init__(stream)
        self._extra = ExtraMapping(
            {
                **self.stream.extra_attributes,
                TLSExtraAttributes.HOSTNAME: lambda: extra.hostname,
                TLSExtraAttributes.SSL_CONTEXT: lambda: extra.ssl_context,
                TLSExtraAttributes.VERSION: lambda: extra.version,
            }
        )
        
    @property
    def extra_attributes(self) -> Mapping[T_Attr, Callable[[], T_Attr]]:
        return self._extra
    
class SSLContextMapper:
    def __init__(
        self,
        default_context: Optional[ssl.SSLContext] = None,
    ):
        self.contexts: dict[re.Pattern, ssl.SSLContext] = {}
        self.default_context = default_context
    
    def _wildcard_to_regex(self, hostname: str) -> re.Pattern:
        return re.compile(
            "^" + re.escape(hostname).replace(re.escape("*"), r"[^.]*") + "$"
        )
    
    def add_context(
        self,
        hostname: str,
        context: ssl.SSLContext
    ) -> None:
        self.contexts[self._wildcard_to_regex(hostname)] = context

    def get_context(
        self,
        hostname: str
    ) -> ssl.SSLContext:
        for pattern, context in self.contexts.items():
            if pattern.match(hostname):
                return context
        return self.default_context or list(self.contexts.values())[0]
    
class AutoTLSListener(
    ExtraListener
):
    def __init__(
        self,
        listener: anyio.abc.Listener,
        default_context: Optional[ssl.SSLContext] = None,
        standard_compatible: bool = True,
        handshake_timeout: float = 30
    ):
        super().__init__(listener)
        self.listener = listener
        self.standard_compatible = standard_compatible
        self.handshake_timeout = handshake_timeout
        self._contexts = SSLContextMapper(default_context)
        
    def add_context(self, hostname: str, context: ssl.SSLContext) -> None:
        self._contexts.add_context(hostname, context)

    async def auto_tls_wrap(
        self,
        stream: BufferedByteStream,
        extra: TLSExtraData
    ) -> BufferedByteStream:
        buf = await stream.pre_readexactly(3)
        if buf[0] != 0x16:
            return stream
        extra.version = ssl.TLSVersion(int.from_bytes(buf[1:]))
        await stream.pre_readexactly(40)
        await stream.pre_readexactly(int.from_bytes(await stream.pre_readexactly(1), "big"))
        await stream.pre_readexactly(int.from_bytes(await stream.pre_readexactly(2), "big"))
        await stream.pre_readexactly(int.from_bytes(await stream.pre_readexactly(1), "big"))
        extensions_length = int.from_bytes(await stream.pre_readexactly(2), "big")
        current_extension_cur = 0
        while current_extension_cur < extensions_length:
            extension_type = int.from_bytes(await stream.pre_readexactly(2), "big")
            extension_length = int.from_bytes(await stream.pre_readexactly(2), "big")
            extension_data = await stream.pre_readexactly(extension_length)
            current_extension_cur += 4 + extension_length
            if extension_type == 0x00:
                extra.hostname = extension_data[5:].decode("utf-8")
                break

        context = self._contexts.get_context(extra.hostname or "*")
        try:
            with anyio.fail_after(self.handshake_timeout):
                stream = BufferedByteStream(
                    await anyio.streams.tls.TLSStream.wrap(
                        stream,
                        ssl_context=context,
                        standard_compatible=self.standard_compatible,
                    )
                )
        except BaseException as exc:
            await anyio.aclose_forcefully(stream)
            raise anyio.ClosedResourceError from exc
        else:
            return stream
        
    async def serve(self, handler: Callable[[TLSStream], Any], task_group: anyio.abc.TaskGroup | None = None) -> None:
        
        @wraps(handler)
        async def wrapper(
            stream: anyio.abc.ByteStream,
        ) -> None:
            stream = BufferedByteStream(stream)
            extra = TLSExtraData()
            try:
                wrapper_stream = await self.auto_tls_wrap(stream, extra)
            except Exception as exc:
                await anyio.aclose_forcefully(stream)
            else:
                await handler(TLSStream(
                    wrapper_stream,
                    extra=extra
                ))

        
        await self.listener.serve(
            wrapper,
            task_group
        )

    async def aclose(self) -> None:
        return await self.listener.aclose()

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