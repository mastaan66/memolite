"""Fully-auto chat loop: recall -> LLM -> store -> extract. Plug-and-use.

User never calls remember(). Just chat(). Memory happens implicitly.
Offline by default (heuristic extractor). Bring your own LLM extractor
via Config(consolidator=fn) for higher quality.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from memolite.consolidator import heuristic_consolidate

Messages = list[dict[str, str]]
LlmFn = Callable[[Messages], str]


def auto_chat(
    store: Any,
    session: str,
    user_msg: str,
    llm_fn: LlmFn,
    system: str = "",
    limit: int = 5,
    actor: str | None = None,
) -> dict[str, Any]:
    """One call does everything. Returns {response, memories, recall_count}."""
    if not session or not session.strip():
        from memolite.exceptions import ValidationError

        raise ValidationError("session required")
    if not user_msg or not user_msg.strip():
        from memolite.exceptions import ValidationError

        raise ValidationError("user_msg empty")

    # 1. implicit recall
    res = store.recall(user_msg, session=session, limit=limit)
    mem_block = res.prompt
    sys = (system + "\n\n" + mem_block) if system and mem_block else (mem_block or system)

    # 2. call user LLM (memolite stays provider-agnostic, offline)
    response = llm_fn(
        [{"role": "system", "content": sys}, {"role": "user", "content": user_msg}]
        if sys
        else [{"role": "user", "content": user_msg}]
    )
    response = str(response)

    # 3. implicit store both turns
    store.add_turn(session, "user", user_msg, actor=actor)
    store.add_turn(session, "assistant", response, actor=actor)

    # 4. implicit extract (skip if auto_capture off)
    created: list[Any] = []
    cfg = getattr(store, "config", None)
    if cfg is not None and getattr(cfg, "auto_capture", True) is False:
        return {"response": response, "memories": created, "recall_count": len(res.memories)}

    extractor = getattr(cfg, "consolidator", None) if cfg is not None else None
    try:
        cands = (
            extractor([user_msg, response])
            if extractor
            else heuristic_consolidate([user_msg, response])
        )
    except Exception:
        cands = heuristic_consolidate([user_msg, response])

    seen: set[str] = set()
    for c in cands[:3]:
        content = str(c.get("content", "")).strip()
        if not content or content.lower() in seen:
            continue
        seen.add(content.lower())
        # dedup against existing: skip if near-identical summary exists
        try:
            dup = store.recall(content[:80], session=session, limit=2)
            if any(m.summary.lower() == content.lower() for m in dup.memories):
                continue
        except Exception:
            pass
        try:
            kind = str(c.get("kind", "semantic"))
            if kind not in {"semantic", "procedural", "episodic"}:
                kind = "semantic"
            imp_raw = c.get("importance", 0.6)
            try:
                imp = float(imp_raw)  # type: ignore[arg-type]
            except Exception:
                imp = 0.6
            imp = max(0.2, min(1.0, imp))
            m = store.remember(
                content,
                summary=str(c.get("summary") or content),
                kind=kind,
                session_id=session,
                importance=imp,
                actor=actor,
            )
            created.append(m)
        except Exception:
            continue

    return {"response": response, "memories": created, "recall_count": len(res.memories)}
