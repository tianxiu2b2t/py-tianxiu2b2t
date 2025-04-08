from typing import Any, Callable

from .abc import StreamConnection
from ...anyio.streams import BufferedByteStream

from .h11_impl import H11Connection
from .h2_impl import H2Connection


class ServerConnection:
    def __init__(
        self,
        stream: BufferedByteStream,
        handle: Callable[[StreamConnection], Any],
    ):
        self.stream = stream
        self.conn = None
        self.handle = handle

    async def handler(self):
        data = await self.stream.receive()

        if self.conn is None:
            if data.startswith(b"PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n"):
                self.conn = H2Connection(self.stream, self.handle)
            else:
                self.conn = H11Connection(self.stream, self.handle)
            
            await self.conn.initialize()

        await self.conn.receive_data(data)
        while 1:
            data = await self.stream.receive()
            await self.conn.receive_data(data)