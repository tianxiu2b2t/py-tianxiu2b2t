import io
import time
from typing import Callable, Coroutine, Optional
import anyio
import anyio.abc

from .streams import HTTPStream, WebSocketReadStream, WebSocketStream
from .types import Handler, Connection, WebSocketItemBytes, WebSocketItemString

from ...anyio.streams.abc import BufferedByteStream
from ...utils import varint_bytes

import wsproto.connection
import wsproto.extensions


class WebSocketConnection(
    Connection
):
    def __init__(
        self,
        stream: BufferedByteStream,
        handler: Handler,
        tls: bool,
        request: HTTPStream,
        accept: Callable[[Optional[str]], Coroutine[None, None, None]]
    ):
        self.stream = stream
        self.handler = handler
        self.tls = tls
        self.request = WebSocketStream(
            stream_id=request.stream_id,
            headers=request.headers,
            method=request.method,
            target=request.target,
            http_version=request.http_version,
            reader=WebSocketReadStream(self.aclose),
            tls=self.tls,
            scheme=request.scheme,
            client=request.client,
            server=request.server,
            send_data=self.send,
            accept=self.accept,
            close=self.close
        )
        self._accept = accept
        self.extensions = [v.strip() for v in self.request.headers.find(b"Sec-WebSocket-Key", b'').decode().split(",")]
        self.connection = wsproto.connection.Connection(
            wsproto.connection.ConnectionType.SERVER,
            [],
        )
        self._task_group: anyio.abc.TaskGroup

    async def process(
        self
    ):
        async with anyio.create_task_group() as task_group:
            task_group.start_soon(self.receive_data, task_group)

    async def accept(
        self,
        subprotocol: Optional[str] = None
    ):
        await self._accept(subprotocol)
        self._task_group.start_soon(self.ping_pong)


    async def receive_data(
        self,
        task_group: anyio.abc.TaskGroup
    ):
        self._task_group = task_group
        task_group.start_soon(self.handler, self.request)
        while 1:
            self.connection.receive_data(await self.stream.receive())
            for event in self.connection.events():
                if isinstance(event, wsproto.events.Ping):
                    await self.raw_send(event.response())
                    continue

                if isinstance(event, (
                    wsproto.events.CloseConnection
                )):
                    if self.connection.state == wsproto.connection.ConnectionState.REMOTE_CLOSING:
                        await self.raw_send(event.response())

                    await self.stream.aclose()
                    return
                
                if isinstance(event, (
                    wsproto.events.TextMessage,
                    wsproto.events.BytesMessage
                )):
                    data = io.BytesIO(event.data) if isinstance(event, wsproto.events.BytesMessage) else io.StringIO(event.data)
                    await self.request.reader.feed(data)
                
    async def send(
        self,
        data: WebSocketItemBytes | WebSocketItemString
    ):
        if isinstance(data, WebSocketItemString):
            if isinstance(data, io.StringIO):
                data = data.getvalue()
            await self.raw_send(wsproto.events.TextMessage(data))
        elif isinstance(data, WebSocketItemBytes):
            if isinstance(data, io.BytesIO):
                data = data.getvalue()
            await self.raw_send(wsproto.events.BytesMessage(data))
        

    async def raw_send(
        self,
        event: wsproto.events.Event
    ):
        if self.connection.state == wsproto.connection.ConnectionState.CLOSED:
            return
        try:
            await self.stream.send(self.connection.send(event))
        except anyio.EndOfStream:
            pass

    async def ping_pong(
        self
    ):
        while 1:
            await anyio.sleep(10)
            await self.raw_send(wsproto.events.Ping(varint_bytes(time.perf_counter_ns())))

    async def aclose(
        self
    ):
        await self.raw_send(wsproto.events.CloseConnection(1000, "Normal closure"))


    async def close(
        self,
        code: int,
        reason: str
    ):
        await self.raw_send(wsproto.events.CloseConnection(code, reason))
