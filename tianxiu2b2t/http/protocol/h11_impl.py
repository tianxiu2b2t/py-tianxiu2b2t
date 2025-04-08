from typing import Any, Callable
import h11

from ...anyio.streams.abc import BufferedByteStream
from .abc import Connection, StreamConnection, Headers, More_data, ReadStream

class H11Connection(
    Connection
):
    def __init__(
        self,
        stream: BufferedByteStream,
        handle: Callable[[StreamConnection], Any],
    ):
        super().__init__(stream, handle)
        self.conn = h11.Connection(h11.SERVER)
        self.stream_connection: StreamConnection = None # type: ignore

    async def initialize(self):
        await super().initialize()

    async def receive_data(self, data: bytes):
        self.conn.receive_data(data)
        await self.handle_events()


    async def handle_events(self):
        while True:
            event = self.conn.next_event()
            if isinstance(event, (
                h11.NEED_DATA,
                h11.ConnectionClosed,
                h11.PAUSED
            )):
                break
            
            if isinstance(event, h11.Request):
                headers = [(
                    k.lower(), v
                ) for k, v in event.headers]
                self.stream_connection = StreamConnection(
                    event.method,
                    headers,
                    event.target,
                    event.http_version,
                    0,
                    ReadStream(),
                    self.send_response,
                    self.send_data
                )
                self.task_group.start_soon(self.handle, self.stream_connection)
            if self.stream_connection is None:
                continue

    async def send_response(self, status_code: int, headers: Headers, stream_id: int = 0):
        buffer = self.conn.send(
            h11.Response(
                status_code=status_code,
                headers=headers
            )
        )
        if buffer is None:
            return
        await self.stream.send(buffer)

    async def send_data(self, data: bytes, more_data: More_data, stream_id: int = 0):
        try:
            buffer = self.conn.send(
                h11.Data(
                    data=data,
                )
            )
        except h11.LocalProtocolError as e:
            return
        if buffer is None:
            return
        await self.stream.send(buffer)

        if not more_data:
            buffer = self.conn.send(
                h11.EndOfMessage()
            )
            if buffer is None:
                return
            await self.stream.send(buffer)

            self.task_group.start_soon(self.next_cycle)

    
    async def next_cycle(self):
        if self.conn.our_state == h11.MUST_CLOSE:
            await self.stream.aclose()
            return False
        
        if self.conn.our_state == h11.DONE and self.conn.their_state == h11.DONE:
            self.conn.start_next_cycle()
        return True

    
