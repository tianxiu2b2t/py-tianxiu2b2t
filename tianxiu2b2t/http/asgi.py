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
ASGICallable = Callable[[Scope, Receive, Send], Awaitable[None]]
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
        app: ASGICallable,
        listener: anyio.abc.Listener,
        config: ASGIConfig = ASGIConfig(),
    ):
        self.app = app
        self.config = config
        self.listener = listener
        self.task_group = anyio.create_task_group()

    async def serve(
        self,
    ):
        await self.task_group.__aenter__()
        try:
            await self.listener.serve(
                self.handler
            )
        finally:
            await self.task_group.__aexit__(None, None, None)

    async def handler(
        self,
        stream: BufferedByteStream,
    ):
        connection = Connection(
            stream,
            self.app,
            self.config,
            self.task_group
        )
        try:
            await connection.handler()
        except Exception as e:
            default_logging.error(
                traceback.format_exc()
            )
        


class Connection:
    def __init__(
        self,
        stream: BufferedByteStream,
        app: ASGICallable,
        config: ASGIConfig,
        task_group: anyio.abc.TaskGroup
    ):
        self.stream = stream
        self.app = app
        self.config = config
        self.conn = protocol.ServerConnection(stream, self.handle)
        self.scheme = "https" if isinstance(stream, (
            TLSStream,
            anyio.streams.tls.TLSStream
        )) else "http"

        self.task_group = task_group

    async def handler(self):
        await self.conn.handler()

    async def handle(
        self,
        request: protocol.StreamConnection,
    ):
        cycle = RequestResponseCycle(
            request,
            self.stream,
            self.app,
            self.config,
            self.scheme,
        )
        self.task_group.start_soon(cycle.run)


class RequestResponseCycle:
    def __init__(
        self,
        request: protocol.StreamConnection,
        stream: BufferedByteStream,
        app: ASGICallable,
        config: ASGIConfig,
        scheme: str,
    ):
        self.request = request
        self.stream = stream
        self.app = app
        self.config = config
        self.root_path = self.config.root_path
        self.scheme = scheme

        self.response_started = False
        self.response_completed = False
        self.response_wait = anyio.Event()


        self.headers = [(key.lower(), value) for key, value in request.headers]
        raw_path, _, query_string = request.target.partition(b"?")
        path = unquote(raw_path.decode("ascii"))
        full_path = self.root_path + path
        full_raw_path = self.root_path.encode("ascii") + raw_path
        self.scope = {
            "type": "http",
            "asgi": {"version": self.config.asgi_version, "spec_version": "2.3"},
            "http_version": request.http_version.decode("ascii"),
            "server": self.stream.local_addr,
            "client": self.stream.remote_addr,
            "scheme": self.scheme,  # type: ignore[typeddict-item]
            "method": request.method.decode("ascii"),
            "root_path": self.root_path,
            "path": full_path,
            "raw_path": full_raw_path,
            "query_string": query_string,
            "headers": self.headers,
            "state": {},
        }

    async def run(self):
        try:
            await self.app(
                self.scope,
                self.receive,
                self.send
            )
        except Exception as e:
            default_logging.error(
                traceback.format_exc()
            )

    
    async def send(self, message: Message):
        stream_id = self.request.stream_id
        if message["type"] == "http.response.start":
            if self.response_started:
                raise RuntimeError("Response already started")
            self.response_started = True
            self.response_wait.set()
            self.status_code = message["status"]
            self.headers = message["headers"]
            await self.request.send_response(
                self.status_code,
                self.headers,
                stream_id
            )
        elif message["type"] == "http.response.body":
            if not self.response_started:
                raise RuntimeError("Response not started")
            if self.response_completed:
                raise RuntimeError("Response already completed")
            more_data = message.get("more_body", False)
            if not more_data:
                self.response_completed = True
                self.response_wait.set()
            await self.request.send_data(message["body"], more_data, stream_id)

    async def receive(self) -> Message:
        read_stream = self.request.read_stream
        
        if read_stream.aborted:
            return {
                "type": "http.disconnect",
            }
        
        if read_stream.size == 0 and read_stream.is_eof and not self.response_completed:
            await self.response_wait.wait()

        data = await read_stream.receive()

        return {
            "type": "http.request",
            "body": data,
            "more_body": True
        }
