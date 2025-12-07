from typing import Any, Generic, TypeVar
import anyio

T = TypeVar('T')

class Future(Generic[T]):
    def __init__(
        self,
    ):
        self._result: T = None # type: ignore
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
