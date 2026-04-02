"""
提供了一些与同步、异步函数转换有关的工厂函数。

Pickle 友好。
"""

import asyncio
from functools import partial
import inspect
from typing import Any, Awaitable, AsyncContextManager, Callable, ContextManager, Optional

# 同步函数类型
SyncFunction = Callable[..., Any]

# 异步函数类型
AsyncFunction = Callable[..., Awaitable[Any]]


def sync_to_async(sync_func: SyncFunction) -> AsyncFunction:
    """
    将同步函数包装为异步函数。
    """
    return partial(asyncio.to_thread, sync_func)


class _AsyncToSyncWrapper:
    __slots__ = ('_async_func',)

    def __init__(self, async_func):
        self._async_func = async_func

    def __call__(self, *args, **kwargs):
        return asyncio.run(self._async_func(*args, **kwargs))

    def __get__(self, instance, owner):
        if instance is None:
            return self
        # 返回一个绑定了实例的包装器
        return partial(self, instance)

    def __reduce__(self):
        return (_AsyncToSyncWrapper, (self._async_func,))


def async_to_sync(async_func: AsyncFunction) -> SyncFunction:
    """
    将异步函数包装为同步函数。
    """
    return _AsyncToSyncWrapper(async_func)


def is_async_func(func: Callable) -> bool:
    """
    判断一个函数是否为异步函数（包括协程函数和异步生成器函数）
    """
    return inspect.iscoroutinefunction(func) or inspect.isasyncgenfunction(func)


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
