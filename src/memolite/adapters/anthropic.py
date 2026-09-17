"""Anthropic Claude adapter - tool_use compatible."""

from __future__ import annotations

from typing import Any

from memolite.adapters.base import BaseAdapter


class AnthropicAdapter(BaseAdapter):
    """Works with Claude via tool_use. Same store, different schema."""

    @property
    def tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "memolite_remember",
                "description": "Store a fact, preference, or project context for later recall.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "content": {"type": "string", "description": "Fact to remember"},
                        "importance": {"type": "number", "description": "0 to 1, default 0.7"},
                        "session_id": {
                            "type": "string",
                            "description": "Session for isolation, optional",
                        },
                    },
                    "required": ["content"],
                },
            },
            {
                "name": "memolite_recall",
                "description": "Recall relevant memories for a query.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "session_id": {"type": "string"},
                        "limit": {"type": "integer", "description": "Max memories, default 5"},
                    },
                    "required": ["query"],
                },
            },
        ]

    def handle_tool_use(self, blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Handle Anthropic tool_use content blocks."""
        out: list[dict[str, Any]] = []
        for b in blocks:
            if b.get("type") != "tool_use":
                continue
            name = b.get("name", "")
            args = b.get("input", {})
            result = self.handle(name, args)
            out.append(
                {"type": "tool_result", "tool_use_id": b.get("id", ""), "content": str(result)}
            )
        return out
