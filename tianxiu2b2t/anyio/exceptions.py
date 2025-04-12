import anyio
import ssl

StreamError = (
    anyio.EndOfStream,
    anyio.ClosedResourceError,
    anyio.BrokenResourceError,
    anyio.BusyResourceError
)

TLSStreamError = (
    ssl.SSLError,
    ssl.SSLZeroReturnError,
    ssl.SSLWantReadError,
    ssl.SSLWantWriteError
)

ALLStreamError = StreamError + TLSStreamError