"""MCP server for Claude Desktop, Cursor, and any MCP client. Zero config: pip install memolite[mcp]."""

from __future__ import annotations

import argparse

from memolite import Config, MemoryStore


def _get_store(path: str) -> MemoryStore:
    return MemoryStore(path, Config(auto_consolidate_every=8))


def run(path: str = "agent.db") -> None:
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as e:
        raise ImportError(
            "MCP requires mcp package: pip install memolite[mcp]  or  pip install mcp"
        ) from e

    mcp = FastMCP("memolite")
    store = _get_store(path)

    @mcp.tool()  # type: ignore
    def remember(content: str, importance: float = 0.7, session_id: str | None = None) -> str:
        """Store a fact, preference, or project note for later recall."""
        m = store.remember(content, importance=importance, session_id=session_id)
        return f"remembered id={m.id} score={m.score:.2f} summary={m.summary}"

    @mcp.tool()  # type: ignore
    def recall(query: str, session_id: str | None = None, limit: int = 5) -> str:
        """Recall relevant memories. Returns prompt-ready block."""
        r = store.recall(query, session=session_id, limit=limit)
        if not r.memories and not r.stm:
            return "no memories found"
        return r.prompt

    @mcp.tool()  # type: ignore
    def health() -> str:
        """Health check: integrity, sizes, FTS."""
        import json

        return json.dumps(store.health_check(), indent=2)

    mcp.run()


def main() -> None:
    p = argparse.ArgumentParser(description="memolite MCP server")
    p.add_argument("--db", default="agent.db", help="SQLite path, default agent.db")
    args = p.parse_args()
    run(args.db)


if __name__ == "__main__":
    main()
