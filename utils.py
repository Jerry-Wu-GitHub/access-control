"""
提供了一些与同步、异步函数转换有关的工厂函数。

Pickle 友好。
"""

import asyncio
from functools import partial
import inspect
from typing import Callable, Awaitable, Any

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
