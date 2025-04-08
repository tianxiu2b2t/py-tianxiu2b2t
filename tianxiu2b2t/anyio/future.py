from typing import Any
import anyio


class Future:
    def __init__(
        self,
    ):
        self._result = None
        self._setted = False
        self._event = anyio.Event()
    
    def set_result(
        self,
        result: Any
    ):
        if self._setted:
            raise RuntimeError("Future already set")
        self._result = result
        self._setted = True
        self._event.set()

    def result(self):
        if not self._setted:
            raise RuntimeError("Future not set")
        return self._result
    
    async def wait(self):
        await self._event.wait()

    async def __await__(self):
        await self.wait()
        return self.result()
