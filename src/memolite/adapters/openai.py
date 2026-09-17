"""OpenAI and DeepSeek adapter - OpenAI compatible tool calling."""

from __future__ import annotations

from typing import Any

from memolite.adapters.base import BaseAdapter


class OpenAIAdapter(BaseAdapter):
    """Works with OpenAI, ChatGPT, DeepSeek, any OpenAI-compatible API."""

    @property
    def tools(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "memolite_remember",
                    "description": "Store a fact, preference, or project context for later recall. Use when user says remember, prefers, or shares durable info.",
                    "parameters": {
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
            },
            {
                "type": "function",
                "function": {
                    "name": "memolite_recall",
                    "description": "Recall relevant memories for a query. Use before answering when context might help.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search query"},
                            "session_id": {"type": "string"},
                            "limit": {"type": "integer", "description": "Max memories, default 5"},
                        },
                        "required": ["query"],
                    },
                },
            },
        ]

    def handle_tool_calls(self, tool_calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Handle OpenAI tool_calls array and return tool outputs."""
        out: list[dict[str, Any]] = []
        for tc in tool_calls:
            fn = tc.get("function", {})
            name = fn.get("name", "")
            args = fn.get("arguments", {})
            if isinstance(args, str):
                import json

                try:
                    args = json.loads(args)
                except Exception:
                    args = {}
            result = self.handle(name, args)
            out.append(
                {
                    "tool_call_id": tc.get("id", name),
                    "role": "tool",
                    "name": name,
                    "content": str(result),
                }
            )
        return out


DeepSeekAdapter = OpenAIAdapter
