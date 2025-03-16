import asyncio
from collections.abc import Callable
from typing import Any
import anyio.abc


class FixedSocketListener(
    anyio.abc.Listener
):
    def __init__(
        self,
        listener: anyio.abc.Listener
    ):
        self._listener = listener
        
    async def serve(
        self,
        handler: Callable[[anyio.abc.SocketStream], Any],
        task_group: anyio.abc.TaskGroup | None = None,
    ) -> None:
        while True:
            try:
                await self._listener.serve(handler, task_group)
            except asyncio.CancelledError:
                break

    async def aclose(self) -> None:
        await self._listener.aclose()