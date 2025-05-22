from tianxiu2b2t.http.protocol.h1 import H1Connection
from tianxiu2b2t.http.protocol.h2 import H2Connection
from tianxiu2b2t.anyio.streams.abc import BufferedByteStream
from tianxiu2b2t.http.protocol.types import Handler


async def auto(
    stream: BufferedByteStream,
    handler: Handler,
    tls: bool = False
):
    # http2
    try:
        buffer = await stream.pre_readexactly(24)
        if buffer == b'PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n':
            return H2Connection(stream, handler, tls)
        else:
            return H1Connection(stream, handler, tls)
    except Exception:
        ...