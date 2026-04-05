"""
提供了一些与同步、异步函数转换有关的工厂函数。

Pickle 友好。
"""

import asyncio
from functools import partial
from inspect import isawaitable
from typing import Any, Awaitable, AsyncContextManager, Callable, ContextManager, Optional

# 同步函数类型
SyncFunction = Callable[..., Any]

# 异步函数类型
AsyncFunction = Callable[..., Awaitable[Any]]


async def _run_func_async(func: Callable, *args, **kwargs):
    """
    异步运行一个同步或异步函数。
    """
    result = func(*args, **kwargs)
    if isawaitable(result):
        return await result
    return result

def to_async(func: Callable) -> AsyncFunction:
    """
    把同步或异步函数转换为异步函数。
    """
    return partial(_run_func_async, func)


def _run_func_sync(func: Callable, *args, **kwargs):
    """
    同步运行一个同步或异步函数。
    """
    result = func(*args, **kwargs)
    if isawaitable(result):
        return asyncio.run(result)
    return result

def to_sync(func: Callable) -> SyncFunction:
    """
    把同步或异步函数转换为同步函数。
    """
    return partial(_run_func_sync, func)


def run_within_context(context: ContextManager, func: SyncFunction, *args, **kwargs):
    """
    将函数 func 放在上下文里执行。
    """
    with context:
        return func(*args, **kwargs)


async def run_within_context_async(context: AsyncContextManager, func: AsyncFunction, *args, **kwargs):
    """
    Asynchronous version of `run_within_context`.
    """
    async with context:
        return await func(*args, **kwargs)


class AsyncRLock:
    """简单的异步可重入锁，兼容 Python 3.10"""
    def __init__(self):
        self._lock = asyncio.Lock()
        self._owner: Optional[int] = None   # 持有锁的 task id
        self._count = 0

    async def acquire(self):
        current_task = id(asyncio.current_task())
        if self._owner == current_task:
            self._count += 1
            return True
        await self._lock.acquire()
        self._owner = current_task
        self._count = 1
        return True

    def release(self):
        if self._owner != id(asyncio.current_task()):
            raise RuntimeError("Cannot release a lock that is not held by the current task")
        self._count -= 1
        if self._count == 0:
            self._owner = None
            self._lock.release()

    async def __aenter__(self):
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.release()
