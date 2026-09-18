"""Base adapter - shared logic for all LLMs."""

from __future__ import annotations

from typing import Any

from memolite.models import RecallResult
from memolite.store import MemoryStore


class BaseAdapter:
    """LLM agnostic base. Store is single source of truth, adapters only translate."""

    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    def remember(
        self, content: str, importance: float = 0.7, session_id: str | None = None
    ) -> dict[str, Any]:
        m = self.store.remember(content, importance=importance, session_id=session_id)
        return {"id": m.id, "summary": m.summary, "score": m.score}

    def recall(self, query: str, session_id: str | None = None, limit: int = 5) -> RecallResult:
        return self.store.recall(query, session=session_id, limit=limit)

    def inject(self, query: str, session_id: str | None = None, limit: int = 5) -> str:
        """Prompt injection for any LLM - no tools needed. Works with Claude, ChatGPT, DeepSeek, local."""
        return self.store.recall(query, session=session_id, limit=limit).prompt

    def chat(
        self,
        session: str,
        user_msg: str,
        llm_fn: Any,
        system: str = "",
        limit: int = 5,
        actor: str | None = None,
    ) -> dict[str, Any]:
        """Fully-auto: recall -> LLM -> store -> extract. Plug-and-use, no remember() needed."""
        from memolite.auto import auto_chat

        return auto_chat(self.store, session, user_msg, llm_fn, system, limit, actor)

    def handle(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Generic tool dispatcher for any LLM tool call."""
        if name in {"memolite_remember", "remember", "store_memory"}:
            return self.remember(
                content=str(arguments.get("content", "")),
                importance=float(arguments.get("importance", 0.7)),
                session_id=arguments.get("session_id"),
            )
        if name in {"memolite_recall", "recall", "search_memory", "get_memory"}:
            r = self.recall(
                query=str(arguments.get("query", "")),
                session_id=arguments.get("session_id"),
                limit=int(arguments.get("limit", 5)),
            )
            return {
                "memories": [
                    {"id": m.id, "summary": m.summary, "score": m.score, "kind": m.kind}
                    for m in r.memories
                ],
                "prompt": r.prompt,
            }
        return {"error": f"unknown tool {name}"}
