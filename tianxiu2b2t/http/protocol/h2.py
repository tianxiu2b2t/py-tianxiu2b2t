from dataclasses import dataclass, field
from typing import Callable, Coroutine
import anyio
import anyio.abc
import h2.connection
import h2.config
import h2.events
import h2.settings

from .streams import ByteReadStream, HTTPStream
from .types import Header, Connection, Handler
from .exceptions import HTTPHeaderSentException
from ...anyio.streams import BufferedByteStream

DEFAULT_SETTINGS = {
    h2.settings.SettingCodes.MAX_CONCURRENT_STREAMS: 1,
    h2.settings.SettingCodes.INITIAL_WINDOW_SIZE.value: 65535,
    h2.settings.SettingCodes.MAX_FRAME_SIZE.value: 65536,
}

class H2Connection(
    Connection
):
    def __init__(
        self,
        stream: BufferedByteStream,
        handler: Handler,
        tls: bool
    ):
        super().__init__(stream, handler, tls)
        self.conn = h2.connection.H2Connection(
            config=h2.config.H2Configuration(
                client_side=False,
            )
        )
        self.streams: dict[int, HTTP2Stream] = {}
        self.writer_lock = anyio.Lock()
        self.stream_lock = anyio.Lock()

    async def process(
        self
    ):
        async with anyio.create_task_group() as task_group:
            task_group.start_soon(self.receive_data, task_group)

    async def receive_data(
        self,
        task_group: anyio.abc.TaskGroup
    ):
        self.conn.initiate_connection()
        self.conn.update_settings(DEFAULT_SETTINGS)

        await self.increment_window()
        await self.flush()

        while True:
            if self.conn.state_machine is h2.connection.ConnectionState.CLOSED:
                break
            try:
                data = await self.stream.receive()
            except:
                break

            for event in self.conn.receive_data(data):
                if isinstance(event, (
                    h2.events.RemoteSettingsChanged,
                    h2.events.SettingsAcknowledged,
                    h2.events.PingAckReceived,
                )):
                    continue

                # ping pong
                if isinstance(event, (
                    h2.events.PingReceived,
                )) and event.ping_data is not None:
                    self.conn.ping(event.ping_data)

                if isinstance(event, (
                    h2.events.ConnectionTerminated,
                )):
                    break

                # flow
                if isinstance(event, (
                    h2.events.WindowUpdated,
                )):
                    
                    await self.increment_window()
                    if event.stream_id is not None and event.delta is not None and event.stream_id != 0:
                        self.conn.acknowledge_received_data(event.delta, event.stream_id)
                        await self.flush_data()


                if isinstance(event, (
                    h2.events.StreamReset,
                )):
                    stream_id = event.stream_id
                    if stream_id is None:
                        continue
                    stream = self.streams.get(stream_id)
                    if stream is None:
                        continue

                    stream.reader.feed_eof()
                    stream.reset = True
                    del self.streams[stream_id]

                # request
                if isinstance(event, (
                    h2.events.RequestReceived,
                )):
                    stream_id = event.stream_id
                    if stream_id is None:
                        continue
                    headers = Header([
                        (k, v) for k, v in event.headers or []
                    ])
                    method = headers.find(b':method', b'')
                    scheme = headers.find(b':scheme', b'')
                    authority = headers.find(b':authority', b'')
                    path = headers.find(b':path', b'/')

                    headers.remove(b':method')
                    headers.remove(b':scheme')
                    headers.remove(b':authority')
                    headers.remove(b':path')

                    headers.append(b'host', authority)
                    stream = HTTP2Stream(
                        stream_id=stream_id,
                        headers=headers,
                        reader=ByteReadStream(),
                        method=method,
                        target=path,
                        scheme=scheme,
                        tls=self.tls,
                        http_version=b'2.0',
                        client=self.stream.remote_addr,
                        server=self.stream.local_addr,
                        raw_send_data=self.send_data,
                        raw_send_response=self.send_response
                    )
                    self.streams[stream_id] = stream
                    stream.init()
                    task_group.start_soon(self.handler, stream)

                if isinstance(event, (
                    h2.events.DataReceived,
                )):
                    stream_id = event.stream_id
                    if stream_id is None:
                        continue
                    stream = self.streams.get(stream_id)
                    if stream is None:
                        continue
                    await stream.reader.feed(event.data)
                    await self.flush_data()

                if isinstance(event, (
                    h2.events.StreamEnded,
                )):
                    stream_id = event.stream_id
                    if stream_id is None:
                        continue
                    stream = self.streams.get(stream_id)
                    if stream is None:
                        continue
                    stream.reader.feed_eof()


    async def increment_window(self):
        inc = h2.connection.H2Connection.MAX_WINDOW_INCREMENT - self.conn.inbound_flow_control_window
        if inc > 0 and inc < h2.connection.H2Connection.MAX_WINDOW_INCREMENT:
            self.conn.increment_flow_control_window(inc)
            await self.flush()

    async def flush_data(self):
        for stream in list(self.streams.values()):
            writer = stream.writer
            if writer.size() < (
                min(self.conn.max_outbound_frame_size, self.conn.outbound_flow_control_window)
            ) and not writer.is_eof():
                continue

            size = min(
                writer.size(),
                self.conn.max_outbound_frame_size,
                self.conn.outbound_flow_control_window
            )
            data = await writer.receive(size)
            if data is None:
                continue
            self.conn.send_data(stream.stream_id, data, end_stream=writer.is_eof() and writer.size() == 0)
            await self.flush()


    async def send_data(
        self,
        data: bytes,
        stream_id: int
    ):
        stream = self.streams.get(stream_id)
        if stream is None:
            return
        if not data:
            stream.writer.feed_eof()
        else:
            await stream.writer.feed(data)
        await self.flush_data()

    async def send_response(
        self,
        status_code: int,
        headers: Header,
        stream_id: int
    ):
        if stream_id not in self.streams or self.streams[stream_id].writer.is_eof() or self.streams[stream_id].reset:
            return
        stream = self.streams[stream_id]
        if stream.sent_headers:
            raise HTTPHeaderSentException()
        headers = Header([
            (b':status', str(status_code).encode('ascii')),
        ] + headers)
        
        stream.sent_headers = True
        self.conn.send_headers(stream_id, headers)
        await self.flush()


    
    async def flush(
        self,
    ):
        async with self.writer_lock:
            data = self.conn.data_to_send()
            if not data:
                return

            await self.stream.send(data)


@dataclass
class HTTP2Stream(HTTPStream):
    writer: ByteReadStream = field(default_factory=ByteReadStream)
    reset: bool = False