"""Generic adapter - works with any LLM via prompt injection, no tools required."""

from __future__ import annotations

from memolite.adapters.base import BaseAdapter


class GenericAdapter(BaseAdapter):
    """For any LLM that does not support tools. Just inject prompt."""

    def build_messages(
        self, system: str, user_query: str, session_id: str | None = None
    ) -> list[dict[str, str]]:
        """Return messages with memory injected. Plug into any chat API."""
        mem_prompt = self.inject(user_query, session_id=session_id, limit=5)
        if mem_prompt.strip():
            system = system + "\n\n" + mem_prompt if system else mem_prompt
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user_query},
        ]
