from collections import deque

from .future import Future


class Lock:
    def __init__(
        self,
    ):
        self._locked = False
        self._fut: deque[Future] = deque()

    async def acquire(
        self,
    ):
        if not self._locked:
            self._locked = True
            return
        fut = Future()
        self._fut.append(fut)
        try:
            await fut.wait()
        finally:
            if fut not in self._fut:
                return
            self._fut.remove(fut)

    def release(
        self,
    ):
        if not self._locked or not self._fut:
            return
        fut = self._fut.popleft()
        fut.set_result(None)
        if not self._fut:
            self._locked = False

    async def __aenter__(self):
        await self.acquire()

    async def __aexit__(self, exc_type, exc, tb):
        self.release()


class WaitLock:
    def __init__(
        self,
        locked: bool = False
    ):
        self._locked = locked
        self._fut: deque[Future] = deque()

    def acquire(
        self,
    ):
        self._locked = True

    def release(
        self,
    ):
        self._locked = False

        for fut in self._fut:
            fut.set_result(None)

    async def wait(
        self
    ):
        if not self._locked:
            return
        fut = Future()
        self._fut.append(fut)
        try:
            await fut.wait()
        finally:
            self._fut.remove(fut)
