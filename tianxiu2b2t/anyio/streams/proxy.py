from dataclasses import dataclass
from functools import wraps
import ipaddress
import traceback
from typing import Any, Callable, Mapping
import anyio.abc

from .abc import BufferedByteStream, ExtraMapping, T_Attr
import socket

V2_MAGIC = b'\r\n\r\n\x00\r\nQUIT\n'

@dataclass
class ProxyProtocolExtra:
    protocol: socket.SocketKind
    source_address: tuple[str, int]
    destination_address: tuple[str, int]

class ProxyProtocolStream(
    BufferedByteStream
):
    def __init__(
        self,
        stream: anyio.abc.AnyByteStream,
        extra: ProxyProtocolExtra,
    ):
        super().__init__(stream)
    
        self._extra = ExtraMapping(
            {
                **self.stream.extra_attributes,
                anyio.abc.SocketAttribute.remote_address: lambda: extra.source_address,
                anyio.abc.SocketAttribute.remote_port: lambda: extra.source_address[1],
                anyio.abc.SocketAttribute.local_address: lambda: extra.destination_address,
                anyio.abc.SocketAttribute.local_port: lambda: extra.destination_address[1],
            }
        )
        
    @property
    def extra_attributes(self) -> Mapping[T_Attr, Callable[[], T_Attr]]:
        return self._extra


class ProxyProtocolV2Listener(
    anyio.abc.Listener
):
    def __init__(
        self,
        listener: anyio.abc.Listener,
    ):
        self.listener = listener

    async def serve(
        self,
        handler: Callable[[ProxyProtocolStream | BufferedByteStream], Any],
        task_group: anyio.abc.TaskGroup | None = None,
    ) -> None:
        @wraps(handler)
        async def wrapper(
            stream: anyio.abc.AnyByteStream
        ):
            try:
                stream = BufferedByteStream(stream)
                buffer = await stream.pre_readexactly(len(V2_MAGIC))
            except:
                return
            
            if buffer != V2_MAGIC:
                return await handler(stream)


            try:
                await stream.readexactly(len(V2_MAGIC))
                buffer = await stream.readexactly(2)
                extra_info = await stream.readexactly(int.from_bytes(await stream.readexactly(2), 'big'))
                
                # 4 bits, 4 bits
                b_af, b_kind = buffer[1] >> 4, buffer[1] & 0b1111

                af = socket.AF_UNSPEC
                kind = socket.SOCK_RAW
                if b_af == 1:
                    af = socket.AF_INET
                elif b_af == 2:
                    af = socket.AF_INET6

                if b_kind == 1:
                    kind = socket.SOCK_STREAM
                elif b_kind == 2:
                    kind = socket.SOCK_DGRAM


                if af == socket.AF_INET:
                    source_addr, source_port = ipaddress.IPv4Address(extra_info[:4]), int.from_bytes(extra_info[8:10], 'big')
                    dest_addr, dest_port = ipaddress.IPv4Address(extra_info[4:8]), int.from_bytes(extra_info[10:12], 'big')
                elif af == socket.AF_INET6:
                    source_addr, source_port = ipaddress.IPv6Address(extra_info[:16]), int.from_bytes(extra_info[32:34], 'big')
                    dest_addr, dest_port = ipaddress.IPv6Address(extra_info[16:32]), int.from_bytes(extra_info[34:36], 'big')
                else:
                    raise ValueError("Unsupported address family")
                

                extra = ProxyProtocolExtra(
                    socket.SOCK_STREAM,
                    (str(source_addr), source_port),
                    (str(dest_addr), dest_port),
                )
                return await handler(ProxyProtocolStream(stream, extra))

            except:
                print(traceback.format_exc())
            
            


        return await self.listener.serve(
            wrapper,
            task_group
        )

    async def aclose(self) -> None:
        return await self.listener.aclose()