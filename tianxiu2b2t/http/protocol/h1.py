import base64
from dataclasses import dataclass
import hashlib
import traceback
from typing import Optional
 
import anyio
import anyio.abc
import h11

from tianxiu2b2t.anyio.lock import WaitLock

from .websockets import WebSocketConnection
from .streams import ZERO_STREAM_ID, ByteReadStream, HTTPStream
from .types import Header, Connection, Handler
from ...anyio.streams import BufferedByteStream


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
        self.pause = WaitLock()

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
                await self.pause.wait()
                data = await self.stream.receive()
                self.conn.receive_data(data)
            except:
                break

            while True:
                try:
                    event = self.conn.next_event()
                except h11.RemoteProtocolError:
                    break
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
                    self.request = HTTPStream(
                        stream_id=ZERO_STREAM_ID,
                        method=event.method,
                        target=event.target,
                        headers=headers,
                        scheme=b"https" if self.tls else b"http",
                        tls=self.tls,
                        http_version=event.http_version,
                        client=self.stream.local_addr,
                        server=self.stream.remote_addr,
                        reader=ByteReadStream(),
                        raw_send_response=self.send_response,
                        raw_send_data=self.send_data
                    )
                    self.request.init()
                    if self.is_websocket():
                        conn = WebSocketConnection(
                            stream=self.stream,
                            handler=self.handler,
                            tls=self.tls,
                            request=self.request,
                            accept=self.accept_ws
                        )
                        await conn.receive_data(task_group)
                        return

                    task_group.start_soon(self.handler, self.request)
                
                if not hasattr(self, 'request'):
                    continue

                if isinstance(event, h11.EndOfMessage):
                    self.request.reader.feed_eof()
                    self.pause.acquire()

                if isinstance(event, h11.Data):
                    await self.request.reader.feed(event.data)

    def is_websocket(self):
        assert self.request is not None, 'No request'
        upgrade = self.request.headers.find(b'Upgrade', b'')
        connection = self.request.headers.find(b'Connection', b'')
        websocket_key = self.request.headers.find(b'Sec-WebSocket-Key', b'')
        return upgrade.lower() == b'websocket' and connection.lower() == b'upgrade' and websocket_key != b''

    async def accept_ws(self, subprotocol: Optional[str]):
        websocket_key = self.request.headers.find(b'Sec-WebSocket-Key', b'')
        headers = [
            (b'Upgrade', b'websocket'),
            (b'Connection', b'Upgrade'),
            (b'Sec-WebSocket-Accept', base64.b64encode(hashlib.sha1(websocket_key + b'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').digest())),
            (b'Sec-WebSocket-Version', b'13'),
        ]
        if subprotocol is not None:
            headers.append((b'Sec-WebSocket-Protocol', subprotocol.encode('utf-8')))
        await self.raw_send(
            h11.InformationalResponse(
                status_code=101,
                headers=headers
            )
        )
        

    async def raw_send(
        self,
        event: h11.Event
    ):
        data = self.conn.send(event)
        
        if data is None:
            return
        await self.stream.send(data)
                

    async def send_response(
        self,
        status_code: int,
        headers: Header,
        stream_id: int = ZERO_STREAM_ID
    ):
        await self.raw_send(
            h11.Response(
                status_code=status_code,
                headers=headers
            )
        )

    async def send_data(
        self,
        data: bytes,
        stream_id: int = ZERO_STREAM_ID
    ):
        if not data:
            await self.raw_send(
                h11.EndOfMessage()
            )
            await self.maybe_next_cycle()
            return
        await self.raw_send(
            h11.Data(data=data)
        )


    async def maybe_next_cycle(self):
        if self.conn.our_state == h11.MUST_CLOSE or self.conn.their_state == h11.MUST_CLOSE:
            await self.raw_send(
                h11.ConnectionClosed()
            )
            await self.stream.aclose()
            return

        if (
            self.conn.our_state == h11.DONE
            and self.conn.their_state == h11.DONE
        ):
            await self.stream.aclose()
            self.pause.release()

    
