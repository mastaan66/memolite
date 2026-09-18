"""System-wide auto-patch. Imported at interpreter startup via memolite.pth.

Reads config from env + ~/.config/memolite/auto.json. Fail-open: never breaks user code.
Kill-switch: MEMOLITE_OFF=1 or MEMOLITE_AUTOPATCH=0 disables everything.
"""

from __future__ import annotations

import builtins
import json
import os
import sys
from pathlib import Path
from typing import Any

_PATCHED = "_memolite_autopatch_done"
_ORIG_IMPORT = None
_STORE = None


def _off() -> bool:
    return os.environ.get("MEMOLITE_OFF") == "1" or os.environ.get("MEMOLITE_AUTOPATCH") == "0"


def _config() -> dict[str, Any]:
    cfg: dict[str, Any] = {}
    try:
        p = Path.home() / ".config" / "memolite" / "auto.json"
        if p.exists():
            cfg = json.loads(p.read_text())
    except Exception:
        cfg = {}
    return {
        "db": os.environ.get("MEMOLITE_DB") or cfg.get("db") or "agent.db",
        "session": os.environ.get("MEMOLITE_SESSION") or cfg.get("session") or "default",
        "actor": os.environ.get("MEMOLITE_ACTOR") or cfg.get("actor"),
        "limit": int(os.environ.get("MEMOLITE_LIMIT") or cfg.get("limit") or 5),
    }


def _store() -> Any | None:
    global _STORE
    if _STORE is not None:
        return _STORE
    try:
        from memolite import MemoryStore

        c = _config()
        _STORE = MemoryStore(c["db"])
        return _STORE
    except Exception:
        return None


def _patch_instance(client: Any, sync: bool) -> None:
    try:
        from memolite.patch import patch_anthropic, patch_openai

        c = _config()
        store = _store()
        if store is None:
            return
        # detect provider by shape
        if (
            sync
            and hasattr(client, "chat")
            and hasattr(getattr(client, "chat", None), "completions")
        ):
            patch_openai(client, store, session=c["session"], actor=c["actor"], limit=c["limit"])
        elif sync and hasattr(client, "messages"):
            patch_anthropic(client, store, session=c["session"], actor=c["actor"], limit=c["limit"])
    except Exception:
        pass


def _wrap_init(cls: Any, sync: bool) -> None:
    if getattr(cls, _PATCHED, False):
        return
    try:
        orig_init = cls.__init__

        def __init__(wrapper_self: Any, *a: Any, **k: Any) -> None:
            orig_init(wrapper_self, *a, **k)
            try:
                _patch_instance(wrapper_self, sync)
            except Exception:
                pass

        cls.__init__ = __init__
        setattr(cls, _PATCHED, True)
    except Exception:
        pass


def _patch_module(name: str) -> None:
    try:
        mod = sys.modules.get(name)
        if mod is None:
            return
        if name == "openai":
            for cls_name in ("OpenAI", "AzureOpenAI"):
                cls = getattr(mod, cls_name, None)
                if cls is not None:
                    _wrap_init(cls, True)
        elif name == "anthropic":
            for cls_name in ("Anthropic",):
                cls = getattr(mod, cls_name, None)
                if cls is not None:
                    _wrap_init(cls, True)
    except Exception:
        pass


def install_hook() -> None:
    """Wrap __import__ so late imports of openai/anthropic get class-patched."""
    global _ORIG_IMPORT
    if _ORIG_IMPORT is not None:
        return
    try:
        _ORIG_IMPORT = builtins.__import__

        def hook(
            mod_name: str,
            globals: Any = None,
            locals: Any = None,
            fromlist: Any = (),
            level: int = 0,
        ) -> Any:
            assert _ORIG_IMPORT is not None
            m = _ORIG_IMPORT(mod_name, globals, locals, fromlist, level)
            try:
                top = mod_name.split(".")[0]
                if top in ("openai", "anthropic"):
                    _patch_module(top)
            except Exception:
                pass
            return m

        builtins.__import__ = hook  # type: ignore[assignment]
    except Exception:
        pass
    # patch anything already loaded
    for n in ("openai", "anthropic"):
        if n in sys.modules:
            _patch_module(n)


try:
    if not _off():
        install_hook()
except Exception:
    pass
