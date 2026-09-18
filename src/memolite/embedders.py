"""LLM embedders as drop-in Config(embedder=...). Lazy imports, fail-clear.

- openai_embedder(client, model): OpenAI / DeepSeek / any OpenAI-compatible.
  Costs network. Best quality.
- local_embedder(model): sentence-transformers, offline after download.
  Needs pip install memolite[local].
- ollama_embedder(model, url): local Ollama server, offline after pull.
  Needs requests (stdlib fallback via urllib).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def openai_embedder(
    client: Any, model: str = "text-embedding-3-small"
) -> Callable[[list[str]], list[list[float]]]:
    """Embed via OpenAI-compatible client.embeddings.create. Batched, normalized."""

    def embed(texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), 100):
            batch = texts[i : i + 100]
            resp = client.embeddings.create(model=model, input=batch)
            items = getattr(resp, "data", None) or resp.get("data", [])
            for item in items:
                emb = item.embedding if hasattr(item, "embedding") else item["embedding"]
                out.append([float(x) for x in emb])
        return out

    return embed


def local_embedder(model: str = "all-MiniLM-L6-v2") -> Callable[[list[str]], list[list[float]]]:
    """Embed via sentence-transformers (offline after first download)."""
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as e:
        raise ImportError('pip install "memolite[local]" for offline LLM embeddings') from e
    st = SentenceTransformer(model)

    def embed(texts: list[str]) -> list[list[float]]:
        vecs = st.encode(texts, normalize_embeddings=True)
        return [[float(x) for x in v] for v in vecs]

    return embed


def ollama_embedder(
    model: str = "nomic-embed-text", url: str = "http://localhost:11434"
) -> Callable[[list[str]], list[list[float]]]:
    """Embed via local Ollama server (offline after pull). Uses urllib, no new deps."""
    import json as _j
    import urllib.request as _u

    def embed(texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for t in texts:
            req = _u.Request(
                f"{url}/api/embeddings",
                data=_j.dumps({"model": model, "prompt": t}).encode(),
                headers={"Content-Type": "application/json"},
            )
            with _u.urlopen(req, timeout=60) as r:
                body = _j.loads(r.read().decode())
            out.append([float(x) for x in body["embedding"]])
        return out

    return embed
