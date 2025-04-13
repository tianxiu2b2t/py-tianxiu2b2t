import asyncio
from collections.abc import Callable
from typing import Any
import anyio.abc

from .abc import ExtraListener


class FixedSocketListener(
    ExtraListener
):
    def __init__(
        self,
        listener: anyio.abc.Listener
    ):
        super().__init__(listener)
        self.listener = listener
        
    async def serve(
        self,
        handler: Callable[[anyio.abc.SocketStream], Any],
        task_group: anyio.abc.TaskGroup | None = None,
    ) -> None:
        while True:
            try:
                await self.listener.serve(handler, task_group)
            except asyncio.CancelledError:
                break

    async def aclose(self) -> None:
        await self.listener.aclose()