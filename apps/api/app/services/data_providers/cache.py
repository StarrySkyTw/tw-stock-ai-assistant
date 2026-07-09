from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from copy import deepcopy
from threading import Lock
from time import monotonic
from typing import TypeVar

T = TypeVar("T")

_LOCK = Lock()
_CACHE: dict[str, tuple[float, object]] = {}
_INFLIGHT: dict[tuple[int, str], asyncio.Task] = {}


async def cached_provider_call(key: str, ttl_seconds: int, factory: Callable[[], Awaitable[T]]) -> T:
    ttl = max(0, ttl_seconds)
    if ttl <= 0:
        return await factory()

    with _LOCK:
        cached = _CACHE.get(key)
        if cached is not None and monotonic() < cached[0]:
            return deepcopy(cached[1])

        loop = asyncio.get_running_loop()
        task_key = (id(loop), key)
        task = _INFLIGHT.get(task_key)
        if task is None or task.done():
            task = loop.create_task(factory())
            _INFLIGHT[task_key] = task

    try:
        result = await task
    finally:
        with _LOCK:
            if _INFLIGHT.get(task_key) is task:
                _INFLIGHT.pop(task_key, None)

    with _LOCK:
        _CACHE[key] = (monotonic() + ttl, deepcopy(result))
    return deepcopy(result)


def clear_provider_cache(prefix: str | None = None) -> None:
    with _LOCK:
        if prefix is None:
            _CACHE.clear()
            _INFLIGHT.clear()
            return

        for key in list(_CACHE):
            if key.startswith(prefix):
                _CACHE.pop(key, None)
        for task_key in list(_INFLIGHT):
            if task_key[1].startswith(prefix):
                _INFLIGHT.pop(task_key, None)
