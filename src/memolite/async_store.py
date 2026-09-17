"""Async wrapper via aiosqlite - optional."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from memolite.config import Config
from memolite.models import Memory, RecallResult
from memolite.store import MemoryStore


class AsyncMemoryStore:
    """Thin async facade delegating to sync store on threadpool.

    Keeps SQL logic in one place. True aiosqlite path would duplicate SQL.
    For :memory: use sync store directly.
    """

    def __init__(self, path: str | Path, config: Config | None = None) -> None:
        if str(path) == ":memory:":
            raise ValueError("AsyncMemoryStore cannot use :memory: - use file path")
        self._store = MemoryStore(path, config)

    async def _run(self, fn: Any, *a: Any, **kw: Any) -> Any:
        return await asyncio.to_thread(fn, *a, **kw)

    async def create_session(self, *a: Any, **kw: Any) -> Any:
        return await self._run(self._store.create_session, *a, **kw)

    async def add_turn(self, *a: Any, **kw: Any) -> Any:
        return await self._run(self._store.add_turn, *a, **kw)

    async def add_tool_call(self, *a: Any, **kw: Any) -> Any:
        return await self._run(self._store.add_tool_call, *a, **kw)

    async def remember(self, *a: Any, **kw: Any) -> Memory:
        return await self._run(self._store.remember, *a, **kw)  # type: ignore[no-any-return]

    async def recall(self, *a: Any, **kw: Any) -> RecallResult:
        return await self._run(self._store.recall, *a, **kw)  # type: ignore[no-any-return]

    async def consolidate(self, *a: Any, **kw: Any) -> Any:
        return await self._run(self._store.consolidate, *a, **kw)

    async def feedback(self, *a: Any, **kw: Any) -> Any:
        return await self._run(self._store.feedback, *a, **kw)

    async def prune(self, *a: Any, **kw: Any) -> Any:
        return await self._run(self._store.prune, *a, **kw)

    async def stats(self) -> dict[str, int]:
        return await self._run(self._store.stats)  # type: ignore[no-any-return]

    async def close(self) -> None:
        await self._run(self._store.close)

    async def __aenter__(self) -> AsyncMemoryStore:
        return self

    async def __aexit__(self, *a: Any) -> None:
        await self.close()
