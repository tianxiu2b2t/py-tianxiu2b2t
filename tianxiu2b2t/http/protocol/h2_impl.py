from typing import Any, Callable
import h2.connection
import h2.events
import h2.config
import h2.settings

from ...anyio.streams import BufferedByteStream
from .abc import Connection, ReadStream, StreamConnection, Headers

LOCAL_CONFIG = {
    h2.settings.SettingCodes.INITIAL_WINDOW_SIZE.value: 1677216,
    h2.settings.SettingCodes.MAX_FRAME_SIZE.value: 1677216
}

class H2Connection(
    Connection
):
    def __init__(
        self,
        stream: BufferedByteStream,
        handle: Callable[[StreamConnection], Any],
    ):
        super().__init__(stream, handle)
        self.conn = h2.connection.H2Connection(
            config=h2.config.H2Configuration(
                client_side=False,
            )
        )
        self.streams: dict[int, StreamConnection] = {}
        self.send_data_streams: dict[int, ReadStream] = {}

    async def initialize(self):
        await super().initialize()

        self.conn.initiate_connection()
        self.conn.update_settings(LOCAL_CONFIG)
        self.conn.increment_flow_control_window(self.conn.MAX_WINDOW_INCREMENT - self.conn.outbound_flow_control_window)
        await self.flush()
    
    async def receive_data(self, data: bytes):
        events = self.conn.receive_data(data)
        await self.handle_events(events)

    async def handle_events(self, events: list[h2.events.Event]):
        for event in events:
            if isinstance(event,
                h2.events.ConnectionTerminated
            ):
                await self.stream.aclose()
                break
            if isinstance(event, (
                h2.events.RemoteSettingsChanged,
                h2.events.PingReceived
            )):
                if isinstance(event, h2.events.PingReceived):
                    self.conn.ping(event.ping_data or b'')
                await self.flush()
                continue

            if isinstance(event, h2.events.WindowUpdated):
                if event.stream_id is not None and event.stream_id != 0:
                    self.conn.increment_flow_control_window(self.conn.MAX_WINDOW_INCREMENT - self.conn.outbound_flow_control_window, stream_id=event.stream_id)
                await self.flush_send_data()
                continue

            if isinstance(event, h2.events.RequestReceived):
                stream_id = event.stream_id
                if stream_id is None:
                    continue
                headers = [(k.lower(), v) for (k, v) in event.headers or []]
                method, host, scheme, path = (
                    _find_and_remove_header(headers, b":method") or b'',
                    _find_and_remove_header(headers, b":authority") or b'',
                    _find_and_remove_header(headers, b":scheme") or b'',
                    _find_and_remove_header(headers, b":path") or b'',
                )
                headers = [
                    (b"host", host)
                ] + headers
                connection = StreamConnection(
                    method,
                    headers,
                    path,
                    b"HTTP/2.0",
                    stream_id, # type: ignore
                    ReadStream(),
                    self.send_response,
                    self.send_data
                )
                self.streams[stream_id] = connection
                self.send_data_streams[stream_id] = ReadStream()
                #await self.handle(connection)
                self.task_group.start_soon(
                    self.handle, connection
                )
            
            if isinstance(event, (
                h2.events.DataReceived,
                h2.events.StreamReset
            )):
                stream_id = event.stream_id
                if stream_id is None or stream_id not in self.streams:
                    continue
                if isinstance(event, h2.events.DataReceived):
                    self.streams[stream_id].read_stream.feed(event.data or b'')
                
                if isinstance(event, h2.events.StreamReset):
                    self.streams.pop(stream_id).read_stream.abort()
                    self.send_data_streams.pop(stream_id).abort()
                

    async def flush(self):
        data = self.conn.data_to_send()
        if not data:
            return
        await self.stream.send(data)

    async def send_response(self, status_code: int, headers: Headers, stream_id: int):
        headers = [
            (b":status", str(status_code).encode('ascii')),
        ] + headers
        self.conn.send_headers(stream_id, headers)
        await self.flush()

    async def send_data(self, data: bytes, more_data: bool, stream_id: int):
        if stream_id not in self.send_data_streams:
            return
        
        self.send_data_streams[stream_id].feed(data)
        if not more_data:
            self.send_data_streams[stream_id].eof()

        chunk_size = min(
            self.conn.local_flow_control_window(stream_id),
            self.conn.max_outbound_frame_size,
        )
        if not self.send_data_streams[stream_id].is_eof or chunk_size == 0:
            return
        
        await self.flush_send_data()

    async def flush_send_data(self):
        for stream_id, stream in list(self.send_data_streams.items()):
            if stream.aborted or (stream.size == 0 and stream.is_eof):
                continue
            chunk_size = min(
                self.conn.local_flow_control_window(stream_id),
                self.conn.max_outbound_frame_size,
                stream.size,
            )
            chunk = await stream.receive(chunk_size)
            if not chunk:
                continue
            self.conn.send_data(stream_id, chunk, end_stream=stream.is_eof)
        await self.flush()


def _find_and_remove_header(headers: Headers, key: bytes):
    val = None
    for i, (k, v) in enumerate(headers):
        if k == key:
            del headers[i]
            val = val or v
    return val