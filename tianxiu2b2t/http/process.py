import anyio
import anyio.abc

from tianxiu2b2t.anyio.streams import BufferedByteStream

async def handler(
    stream: anyio.abc.AnyByteStream
):
    stream = BufferedByteStream(stream)
    
    # 