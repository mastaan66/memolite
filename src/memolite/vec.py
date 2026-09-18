"""Vector hybrid v1: stdlib hash-embed baseline + cosine rerank over FTS candidates.

Honest scope: NOT full ANN. FTS retrieves candidates (limit*3), vectors rerank them.
Bring SOTA via Config(embedder=fn, embedding_dim=N) — e.g. sentence-transformers.
Without sqlite_vec/numpy, pure-python cosine over a handful of candidates is ~us.
"""

from __future__ import annotations

import hashlib
import math
import struct


def hash_embed(texts: list[str], dim: int = 128) -> list[list[float]]:
    """Deterministic hashing-trick embeddings. Offline, zero deps. Baseline only."""
    out: list[list[float]] = []
    for t in texts:
        vec = [0.0] * dim
        for tok in t.lower().split():
            h = int(hashlib.sha256(tok.encode()).hexdigest(), 16)
            vec[h % dim] += 1.0
        n = math.sqrt(sum(v * v for v in vec)) or 1.0
        out.append([v / n for v in vec])
    return out


def cosine(a: list[float], b: list[float]) -> float:
    n = min(len(a), len(b))
    s = sum(a[i] * b[i] for i in range(n))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return s / (na * nb)


def pack(vec: list[float]) -> bytes:
    return struct.pack(f"<{len(vec)}f", *vec)


def unpack(blob: bytes) -> list[float]:
    n = len(blob) // 4
    return list(struct.unpack(f"<{n}f", blob))


def hybrid_score(fts_fused: float, sim: float, w_fts: float = 0.6, w_vec: float = 0.4) -> float:
    return w_fts * fts_fused + w_vec * sim
