import asyncio
from collections.abc import Callable
from typing import Any
import anyio.abc


class FixedSocketListener(
    anyio.abc.SocketListener
):
    def __init__(
        self,
        listener: anyio.abc.SocketListener
    ):
        self._listener = listener

    async def accept(self) -> anyio.abc.SocketStream:
        try:
            return await self._listener.accept()
        except Exception as e:
            raise e
        
    async def serve(
        self,
        handler: Callable[[anyio.abc.SocketStream], Any]
    ) -> None:
        async with anyio.create_task_group() as task_group:
            while True:
                try:
                    await self._listener.serve(handler, task_group)
                except asyncio.CancelledError:
                    break

    async def aclose(self) -> None:
        await self._listener.aclose()