from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable, Optional
import anyio.abc

from .abc import BufferedByteStream

V2_MAGIC = b'\r\n\r\n\x00\r\nQUIT\n'

@dataclass
class ProxyProtocolExtra:
    protocol: int

class ProxyProtocolV2Listener(
    anyio.abc.Listener
):
    def __init__(
        self,
        listener: anyio.abc.Listener,
        handler: Callable[[
            anyio.abc.AnyByteStream,
            Optional[ProxyProtocolExtra]
        ], Any],
    ):
        self.listener = listener
        self.handler = handler

    async def serve(
        self,
        handler: Callable[[anyio.abc.SocketStream], Any],
        task_group: anyio.abc.TaskGroup | None = None,
    ) -> None:
        @wraps
        async def wrapper(
            stream: anyio.abc.AnyByteStream
        ):
            stream = BufferedByteStream(stream)
            buffer = await stream.pre_readexactly(len(V2_MAGIC))

            if buffer != V2_MAGIC:
                return await self.handler(stream, None)
            
            
            


        return await self.listener.serve(
            wrapper,
            task_group
        )

    async def aclose(self) -> None:
        return await self.listener.aclose()