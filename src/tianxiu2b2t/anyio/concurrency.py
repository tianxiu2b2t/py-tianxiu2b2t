from typing import (
    Any, 
    Coroutine,
    Optional, 
    TypeVar,
    overload,
)

import anyio

T = TypeVar("T")

@overload
async def gather(
    *tasks: Coroutine[Any, Any, T]
) -> list[T]:
    ...

@overload
async def gather(
    *tasks: Coroutine[Any, Any, T],
    concurrency: Optional[int] = None
) -> list[T]:
    ...

async def gather(
    *tasks: Coroutine[Any, Any, T],
    concurrency: Optional[int] = None
) -> list[T]:
    """
    Gather multiple tasks and return their results as a list.
    """
    sem = anyio.Semaphore(concurrency or len(tasks), fast_acquire=True)
    results: dict[Coroutine[Any, Any, T], T] = {}
    async def wrapper(coro: Coroutine[Any, Any, T]):
        async with sem:
            results[coro] = await coro
    async with anyio.create_task_group() as task_group:
        for task in tasks:
            task_group.start_soon(wrapper, task)

    return [
        results[task] for task in tasks
    ]