import abc
from collections import deque
from dataclasses import dataclass
import io
import logging
import ssl
import traceback
from typing import Any, Awaitable, Callable, MutableMapping, Optional, TypedDict
from urllib.parse import unquote

import anyio
import anyio.abc

from ..anyio.streams.abc import BufferedByteStream
from ..anyio.exceptions import ALLStreamError
from .protocol import auto, exceptions
from .protocol.streams import HTTPStream, WebSocketStream

from .protocol.types import Stream


logger = logging.getLogger("tianxiu2b2t.http.asgi")

Message = MutableMapping[str, Any]
Send = Callable[[Message], Awaitable[None]]
Receive = Callable[[], Awaitable[Message]]
Scope = MutableMapping[str, Any]
ASGIVersion = {
    "version": "3.0",
    "spec_version": "2.3",
}
ASGICallable = Callable[[Scope, Receive, Send], Awaitable[None]]

class HTTPScope(TypedDict):
    type: str
    http_version: str
    method: str
    scheme: str
    path: str
    raw_path: bytes
    query_string: bytes
    root_path: str
    headers: list[tuple[str, str]]
    client: tuple[str, int]
    server: tuple[str, int]

class WebSocketScope(TypedDict):
    type: str
    subprotocols: list[str]
    extensions: dict[str, Any]
    client: tuple[str, int]
    server: tuple[str, int]

@dataclass
class ASGIConfig:
    app: ASGICallable
    root_path: str = ""

class RequestResponseCycle(
    metaclass=abc.ABCMeta
):
    def __init__(
        self,
        connection: Stream,
        config: ASGIConfig
    ):
        self.connection = connection
        self.config = config

    @abc.abstractmethod
    async def process(self):
        pass

class HTTPRequestResponseCycle(RequestResponseCycle):
    def __init__(
        self,
        connection: HTTPStream,
        config: ASGIConfig
    ):
        super().__init__(connection, config)
        # type
        self.connection: HTTPStream

        raw_path, _, query_string = self.connection.target.partition(b"?")
        path = unquote(raw_path.decode("ascii"))
        full_path = self.config.root_path + path
        full_raw_path = self.config.root_path.encode("ascii") + raw_path
        self.scope = {
            "type": "http",
            "asgi": ASGIVersion,
            "http_version": self.connection.http_version.decode("ascii"),
            "server": self.connection.server,
            "client": self.connection.client,
            "scheme": self.connection.scheme.decode("ascii"),  # type: ignore[typeddict-item]
            "method": self.connection.method.decode("ascii"),
            "root_path": self.config.root_path,
            "path": full_path,
            "raw_path": full_raw_path,
            "query_string": query_string,
            "headers": self.connection.headers,
            "state": {},
        }
        self.disconnect = False
        self.completed = False
        self.receive_message = anyio.Event()

    async def process(self):
        app = self.config.app
        try:
            await app(self.scope, self.receive, self.send)
        except ALLStreamError:
            self.disconnect = True
            self.receive_message.set()
            return
        except:
            logger.exception("Error in ASGI application")
            logger.exception(traceback.format_exc())

    async def send(self, message: Message):
        type = message["type"]
        if type == "http.response.start":
            await self.connection.send_response(message["status"], message["headers"])
        elif type == "http.response.body":
            await self.connection.send_data(message["body"])
            if not message.get("more_body", False):
                await self.connection.send_data(b'')
                self.completed = True
                self.disconnect = True
                self.receive_message.set()


    async def receive(self) -> Message:
        if self.connection.reader.is_eof() and self.connection.reader.size() == 0:
            await self.receive_message.wait()
            
        if self.disconnect or self.completed:
            return {
                "type": "http.disconnect"
            }
        
        data = await self.connection.reader.receive()
        more_body = not self.connection.reader.is_eof() and self.connection.reader.size() > 0
        
        return {
            "type": "http.request",
            "body": await self.connection.reader.receive(),
            "more_body": more_body
        }

class WebSocketRequestResponseCycle(RequestResponseCycle):
    def __init__(
        self,
        connection: WebSocketStream,
        config: ASGIConfig
    ):
        super().__init__(connection, config)
        self.connection: WebSocketStream

        raw_path, _, query_string = self.connection.target.partition(b"?")
        path = unquote(raw_path.decode("ascii"))
        full_path = self.config.root_path + path
        full_raw_path = self.config.root_path.encode("ascii") + raw_path
        self.scope = {
            "type": "websocket",
            "asgi": ASGIVersion,
            "http_version": self.connection.http_version.decode("ascii"),
            "server": self.connection.server,
            "client": self.connection.client,
            "scheme": "wss" if self.connection.tls else "ws",  # type: ignore[typeddict-item]
            "root_path": self.config.root_path,
            "path": full_path,
            "raw_path": full_raw_path,
            "query_string": query_string,
            "headers": self.connection.headers,
            "state": {},
        }
        self.message_queues: deque[Message] = deque()
        self.message_queues.appendleft({
            "type": "websocket.connect"
        })

    async def process(self):
        app = self.config.app
        try:
            await app(self.scope, self.receive, self.send)
        except ALLStreamError:
            return
        except:
            logger.exception("Error in ASGI application")
            logger.exception(traceback.format_exc())

    async def send(self, message: Message):
        type = message["type"]
        if type == "websocket.accept":
            await self.connection.accept(message["subprotocol"])
        elif type == "websocket.send":
            await self.connection.send_data(message["text"] if message["text"] is not None else message["bytes"])
        elif type == "websocket.close":
            await self.connection.close(message["code"], message["reason"])
            await self.connection.reader.aclose()
            self.completed = True
            self.disconnect = True
            

    async def receive(self) -> Message:
        if self.message_queues:
            return self.message_queues.popleft()
        
        data = await self.receive_data()
        if data is None:
            return {
                "type": "websocket.disconnect"
            }
        return data

    async def receive_data(self) -> Optional[Message]:
        data = await self.connection.reader.receive()
        if data is None:
            return None
        return {
            "type": "websocket.receive",
            "text": data.read() if isinstance(data, io.StringIO) else None,
            "bytes": data.read() if isinstance(data, io.BytesIO) else None
        }

class ASGIApplicationBridge:
    def __init__(
        self,
        config: ASGIConfig
    ):
        self.app = config.app
        self.config = config
        self.task_group = anyio.create_task_group()

    async def handler(
        self,
        connection: Stream
    ):
        conn = None
        if isinstance(connection, HTTPStream):
            conn = HTTPRequestResponseCycle(connection, self.config)
        elif isinstance(connection, WebSocketStream):
            conn = WebSocketRequestResponseCycle(connection, self.config)
        if conn is None:
            return
        try:
            await conn.process()
        except ALLStreamError:
            pass


    async def __aenter__(self):
        await self.task_group.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.task_group.__aexit__(exc_type, exc_val, exc_tb)

    async def serve(
        self,
        listener: anyio.abc.Listener
    ):
        async def wrapper_handler(
            stream: anyio.abc.AnyByteStream
        ):
            conn = await auto.auto(BufferedByteStream(stream), self.handler)
            if conn is None:
                return
            await conn.process()
        
        await listener.serve(wrapper_handler, self.task_group)

    
class ASGIListener:
    def __init__(
        self,
        config: ASGIConfig,
        listener: anyio.abc.Listener
    ):
        self.config = config
        self.bridge = ASGIApplicationBridge(config)
        self.listener = listener
    
    async def serve(
        self,
    ):
        async with self.bridge:
            await self.bridge.serve(self.listener)