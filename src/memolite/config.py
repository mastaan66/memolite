"""Configuration for memolite."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Config:
    """Store configuration. All fields have safe offline defaults."""

    # path behaviour
    busy_timeout_ms: int = 5000
    wal_mode: bool = True
    foreign_keys: bool = True

    # STM
    stm_window: int = 12  # last N turns returned in recall
    auto_consolidate_every: int = 8  # trigger consolidation after N turns, 0=disable
    max_tokens_stm: int = 8000  # char budget approx, for prompt building

    # scoring weights: must sum ~1.0
    weight_importance: float = 0.4
    weight_frequency: float = 0.3
    weight_recency: float = 0.2
    weight_reward: float = 0.1
    recency_half_life_days: float = 30.0

    # FTS recall
    fts_boost_factor: float = 1.0
    min_score_to_recall: float = 0.0

    # caps
    max_memories: int = 10000
    prune_batch: int = 500

    # pluggable hooks - receive (texts: list[str]) -> summaries or embeddings
    # If None, heuristic / no-vec fallback is used.
    consolidator: Callable[[list[str]], list[dict[str, object]]] | None = None
    embedder: Callable[[list[str]], list[list[float]]] | None = None
    embedding_dim: int | None = None

    # extra pragmas
    extra_pragmas: dict[str, str] = field(default_factory=dict)

    # hardening - all off except WORM/file-perms which are passive
    redact_pii: bool = False
    require_encryption: bool = False
    encryption_key_env: str = "MEMOLITE_KEY"
    require_acl: bool = False
    worm_enabled: bool = True

    # fully-auto plug-and-use: chat() stores + extracts without remember()
    auto_capture: bool = True
