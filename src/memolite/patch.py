"""Zero-effort wiring: patch once, every LLM call uses memory. No chat() needed.

from memolite import MemoryStore, patch_openai
store = MemoryStore("agent.db")
patch_openai(client, store, session="s1")  # done. all future calls auto-recall + auto-store.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any

_ORIG_OPENAI = "_memolite_orig_create"
_ORIG_ANTHROPIC = "_memolite_orig_create"


def _resolve(val: str | Callable[..., str] | None, *args: Any) -> str | None:
    if val is None:
        return None
    if callable(val):
        try:
            return str(val(*args))
        except Exception:
            return None
    return str(val)


def _last_user_text(messages: list[dict[str, Any]]) -> str:
    for m in reversed(messages):
        if m.get("role") == "user":
            c = m.get("content", "")
            if isinstance(c, str):
                return c
            if isinstance(c, list):
                parts = []
                for b in c:
                    if isinstance(b, dict) and b.get("type") == "text":
                        parts.append(str(b.get("text", "")))
                    elif isinstance(b, dict) and "text" in b:
                        parts.append(str(b["text"]))
                if parts:
                    return "\n".join(parts)
    return ""


def _assistant_text_openai(resp: Any) -> str:
    try:
        choices = getattr(resp, "choices", None) or resp.get("choices", [])
        first = choices[0]
        msg = first.message if hasattr(first, "message") else first["message"]
        content = msg.content if hasattr(msg, "content") else msg.get("content", "")
        return str(content or "")
    except Exception:
        return ""


def _assistant_text_anthropic(resp: Any) -> str:
    try:
        blocks = getattr(resp, "content", None) or resp.get("content", [])
        out: list[str] = []
        for b in blocks:
            if isinstance(b, dict) and b.get("type") == "text":
                out.append(str(b.get("text", "")))
            elif hasattr(b, "text"):
                out.append(str(getattr(b, "text", "")))
        return "\n".join(out)
    except Exception:
        return ""


def patch_openai(
    client: Any,
    store: Any,
    session: str | Callable[..., str] = "default",
    actor: str | Callable[..., str] | None = None,
    limit: int = 5,
) -> Any:
    """Patch client.chat.completions.create. Idempotent. Returns client."""
    from memolite.auto import save_facts

    target = client.chat.completions
    if getattr(target, _ORIG_OPENAI, None) is not None:
        return client
    orig = target.create
    setattr(target, _ORIG_OPENAI, orig)

    @functools.wraps(orig)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        msgs = kwargs.get("messages") or (list(args[0]) if args else [])
        msgs = [dict(m) for m in msgs]
        sess = _resolve(session, msgs, kwargs) or "default"
        act = _resolve(actor, msgs, kwargs)
        query = _last_user_text(msgs)
        if kwargs.get("stream"):
            # inject recall but skip store (stream capture out of scope)
            try:
                if query:
                    block = store.recall(query, session=sess, limit=limit).prompt
                    if block:
                        msgs = [{"role": "system", "content": block}, *msgs]
                        kwargs["messages"] = msgs
            except Exception:
                pass
            return orig(*args, **kwargs)
        try:
            if query:
                block = store.recall(query, session=sess, limit=limit).prompt
                if block:
                    msgs = [{"role": "system", "content": block}, *msgs]
                    kwargs["messages"] = msgs
        except Exception:
            pass
        resp = orig(*args, **kwargs)
        try:
            text = _assistant_text_openai(resp)
            if query:
                store.add_turn(sess, "user", query, actor=act)
            if text:
                store.add_turn(sess, "assistant", text, actor=act)
            if query and text:
                save_facts(store, sess, query, text, act)
        except Exception:
            pass
        return resp

    target.create = wrapper
    return client


def unpatch_openai(client: Any) -> Any:
    target = client.chat.completions
    orig = getattr(target, _ORIG_OPENAI, None)
    if orig is not None:
        target.create = orig
        delattr(target, _ORIG_OPENAI)
    return client


def patch_anthropic(
    client: Any,
    store: Any,
    session: str | Callable[..., str] = "default",
    actor: str | Callable[..., str] | None = None,
    limit: int = 5,
) -> Any:
    """Patch client.messages.create. Idempotent. Returns client."""
    from memolite.auto import save_facts

    target = client.messages
    if getattr(target, _ORIG_ANTHROPIC, None) is not None:
        return client
    orig = target.create
    setattr(target, _ORIG_ANTHROPIC, orig)

    @functools.wraps(orig)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        msgs = kwargs.get("messages") or (list(args[0]) if args else [])
        msgs = [dict(m) for m in msgs]
        sess = _resolve(session, msgs, kwargs) or "default"
        act = _resolve(actor, msgs, kwargs)
        query = _last_user_text(msgs)
        if kwargs.get("stream"):
            try:
                if query:
                    block = store.recall(query, session=sess, limit=limit).prompt
                    if block:
                        prev = kwargs.get("system", "")
                        kwargs["system"] = (prev + "\n\n" + block) if prev else block
            except Exception:
                pass
            return orig(*args, **kwargs)
        try:
            if query:
                block = store.recall(query, session=sess, limit=limit).prompt
                if block:
                    prev = kwargs.get("system", "")
                    kwargs["system"] = (prev + "\n\n" + block) if prev else block
        except Exception:
            pass
        resp = orig(*args, **kwargs)
        try:
            text = _assistant_text_anthropic(resp)
            if query:
                store.add_turn(sess, "user", query, actor=act)
            if text:
                store.add_turn(sess, "assistant", text, actor=act)
            if query and text:
                save_facts(store, sess, query, text, act)
        except Exception:
            pass
        return resp

    target.create = wrapper
    return client


def unpatch_anthropic(client: Any) -> Any:
    target = client.messages
    orig = getattr(target, _ORIG_ANTHROPIC, None)
    if orig is not None:
        target.create = orig
        delattr(target, _ORIG_ANTHROPIC)
    return client
