"""Async store."""

import asyncio
import tempfile
from pathlib import Path

from memolite import AsyncMemoryStore


async def main() -> None:
    with tempfile.TemporaryDirectory() as d:
        db = Path(d) / "a.db"
        async with AsyncMemoryStore(db) as store:
            await store.add_turn(session="s1", role="user", content="async hello")
            res = await store.recall("hello", session="s1")
            print(res.prompt)


asyncio.run(main())
