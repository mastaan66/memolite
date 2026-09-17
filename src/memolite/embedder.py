"""Pluggable embedder protocols - offline friendly."""

from __future__ import annotations

from typing import Protocol


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...
