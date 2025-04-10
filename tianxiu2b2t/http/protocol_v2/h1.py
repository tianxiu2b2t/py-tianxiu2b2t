import base64
import hashlib
from typing import Callable, cast
 
import anyio
import anyio.abc
import h11

from .streams import ZERO_STREAM_ID, HTTPStream, WebSocketStream
from .types import Header, Connection, Handler
from ...anyio.streams import BufferedByteStream
from ...logging import logging


class H1Connection(
    Connection
):
    def __init__(
        self,
        stream: BufferedByteStream,
        handler: Handler,
        tls: bool
    ):
        super().__init__(stream, handler, tls)
        self.conn = h11.Connection(
            our_role=h11.SERVER,
        )

    async def process(
        self
    ):
        async with anyio.create_task_group() as task_group:
            task_group.start_soon(self.receive_data, task_group)

    async def receive_data(
        self,
        task_group: anyio.abc.TaskGroup
    ):
        while True:
            try:
                data = await self.stream.receive()
                self.conn.receive_data(data)
            except:
                break

            while True:
                event = self.conn.next_event()
                if isinstance(event, (
                    h11.ConnectionClosed,
                    h11.RemoteProtocolError,
                    h11.LocalProtocolError,
                    h11.NEED_DATA,
                    h11.PAUSED
                )):
                    break
                
            
                if isinstance(event, h11.Request):
                    headers = Header(event.headers)
                    writer, reader = anyio.create_memory_object_stream()
                    self.request = HTTPStream(
                        stream_id=ZERO_STREAM_ID,
                        method=event.method,
                        target=event.target,
                        headers=headers,
                        http_version=event.http_version,
                        reader=reader,
                        writer=writer
                    )
                    await self.should_ws_upgrade()

                    task_group.start_soon(self.handler, self.request)

                if isinstance(event, h11.Data):
                    await self.request.writer.send(event.data)

    async def should_ws_upgrade(self):
        upgrade = self.request.headers.find(b'Upgrade', b'')
        connection = self.request.headers.find(b'Connection', b'')
        websocket_key = self.request.headers.find(b'Sec-WebSocket-Key', b'')
        if (
            upgrade != b'websocket' or connection != b'Upgrade' or websocket_key == b''
        ):
            return False
        
        await self.raw_send(
            h11.InformationalResponse(
                status_code=101,
                headers=[
                    (b'Upgrade', b'websocket'),
                    (b'Connection', b'Upgrade'),
                    (b'Sec-WebSocket-Accept', base64.b64encode(hashlib.sha1(websocket_key + b'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').digest())),
                    (b'Sec-WebSocket-Version', b'13'),
                ]
            )
        )
        self.request = cast(WebSocketStream, self.request)
        

    async def raw_send(
        self,
        event: h11.Event
    ):
        data = self.conn.send(event)
        
        if data is None:
            return
        await self.stream.send(data)
                

    