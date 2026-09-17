"""Typed models for memolite."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Session:
    id: str
    meta: dict[str, object] | None
    created_at: int


@dataclass(frozen=True, slots=True)
class Turn:
    id: int
    session_id: str
    role: str
    content: str
    tokens: int
    ts: int


@dataclass(frozen=True, slots=True)
class ToolCall:
    id: int
    turn_id: int
    name: str
    args: dict[str, object] | None
    result: dict[str, object] | str | None
    success: bool | None


@dataclass(frozen=True, slots=True)
class Memory:
    id: int
    kind: str  # semantic | procedural | episodic
    session_id: str | None
    content: str
    summary: str
    importance: float
    access_count: int
    score: float
    created_at: int
    last_accessed: int

    @property
    def text(self) -> str:
        return self.summary or self.content


@dataclass(frozen=True, slots=True)
class RecallResult:
    query: str
    stm: list[Turn]
    memories: list[Memory]
    tool_calls: list[ToolCall]

    @property
    def prompt(self) -> str:
        """Ready-to-inject context block for agent."""
        lines: list[str] = []
        if self.memories:
            lines.append("# Long-term memories")
            for m in self.memories:
                lines.append(f"- [{m.kind}:{m.id} score={m.score:.2f}] {m.text}")
        if self.stm:
            lines.append("\n# Recent conversation")
            for t in self.stm:
                lines.append(f"{t.role}: {t.content}")
        return "\n".join(lines)
