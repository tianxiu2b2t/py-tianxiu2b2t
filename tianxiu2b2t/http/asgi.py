from collections import defaultdict
import traceback
from typing import Awaitable, Callable, MutableMapping, Any, Optional
from urllib.parse import unquote

import anyio.abc
import anyio.streams
import anyio.streams.tls
import logging

from . import protocol

from ..anyio.streams import BufferedByteStream, TLSStream

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
default_logging = logging.getLogger("tianxiu2b2t.http.asgi")

class ASGIConfig:
    def __init__(
        self,
        root_path: str = "",
    ):
        self.root_path = root_path
        self.asgi_version = "3.0"

class ASGIApplicationBridge:
    def __init__(
        self,
        app: Callable[[Scope, Receive, Send], Awaitable[None]],
        config: ASGIConfig = ASGIConfig()
    ):
        self.app = app
        self.config = config
        self.task_group = anyio.create_task_group()
        self._entered = False

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self.app(scope, receive, send)

    async def serve(self, listener: anyio.abc.Listener):
        await listener.serve(self.handler)
    

    async def handler(
        self,
        stream: anyio.abc.AnyByteStream,
    ):
        stream = BufferedByteStream(stream)
        if not self._entered:
            await self.__aenter__()
        
        conn = Connection(
            stream,
            self.app,
            self.config,
        )
        async def wrapper_handler():
            try:
                await conn.handle()
            except Exception as e:
                print(traceback.format_exc())

        self.task_group.start_soon(wrapper_handler)

    async def __aenter__(self):
        await self.task_group.__aenter__()
        self._entered = True
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.task_group.__aexit__(exc_type, exc_val, exc_tb)
        self._entered = False
        

class Connection:
    def __init__(
        self,
        stream: BufferedByteStream,
        app: Callable[[Scope, Receive, Send], Awaitable[None]],
        config: ASGIConfig = ASGIConfig(),
    ):
        self.app = app
        self.config = config
        self.conn = protocol.ServerConnection(stream, self.handle_req)
        self.scheme = "https" if isinstance(stream, (anyio.streams.tls.TLSStream, TLSStream)) else "http"

    async def handle(self):
        await self.conn.handler()

    async def handle_req(self, stream: protocol.StreamConnection):
        print(stream)


def get_local_addr(
    stream: anyio.abc.AnyByteStream,
):
    addr = stream.extra(anyio.abc.SocketAttribute.local_address)
    if isinstance(addr, tuple):
        return addr[:2]
    return addr, stream.extra(anyio.abc.SocketAttribute.local_port)

def get_remote_addr(
    stream: anyio.abc.AnyByteStream,
):
    addr = stream.extra(anyio.abc.SocketAttribute.remote_address)
    if isinstance(addr, tuple):
        return addr[:2]
    return addr, stream.extra(anyio.abc.SocketAttribute.remote_port)