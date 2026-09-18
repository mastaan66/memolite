"""Autoload tests: import hook + class wrap, fake provider modules."""

from __future__ import annotations

import sys
import types


def _fake_openai_module():
    mod = types.ModuleType("openai")

    class FakeCompletions:
        def create(self, messages, **kw):
            return {"ok": True, "messages": messages}

    class FakeChat:
        def __init__(self):
            self.completions = FakeCompletions()

    class OpenAI:
        def __init__(self, *a, **k):
            self.chat = FakeChat()

    mod.OpenAI = OpenAI
    return mod


def test_autoload_patches_new_clients(tmp_path, monkeypatch):
    import memolite.autoload as al

    monkeypatch.setenv("MEMOLITE_DB", str(tmp_path / "auto.db"))
    monkeypatch.delenv("MEMOLITE_OFF", raising=False)
    monkeypatch.delenv("MEMOLITE_AUTOPATCH", raising=False)
    al._STORE = None
    sys.modules["openai"] = _fake_openai_module()
    al._patch_module("openai")
    from openai import OpenAI

    c = OpenAI()
    out = c.chat.completions.create(messages=[{"role": "user", "content": "I prefer Vim"}])
    assert out["ok"] is True
    # system prompt injected from second call onward; turns stored
    c.chat.completions.create(messages=[{"role": "user", "content": "hello again"}])
    assert al._store() is not None
    assert al._store().stats()["turns"] >= 2
    del sys.modules["openai"]
    al._STORE.close()
    al._STORE = None


def test_off_switch():
    import memolite.autoload as al

    assert al._off() in (True, False)


def test_config_and_hook(tmp_path, monkeypatch):
    import memolite.autoload as al

    monkeypatch.setenv("MEMOLITE_DB", str(tmp_path / "c.db"))
    monkeypatch.setenv("MEMOLITE_SESSION", "s9")
    c = al._config()
    assert c["session"] == "s9"
    al.install_hook()
    al.install_hook()  # idempotent
    al._patch_module("nonexistent-xyz")

    # already-patched class skipped
    class C:
        def __init__(self):
            pass

    al._wrap_init(C, True)
    al._wrap_init(C, True)
    assert C._memolite_autopatch_done is True


def test_patch_instance_shapes(tmp_path, monkeypatch):
    from types import SimpleNamespace

    import memolite.autoload as al

    monkeypatch.setenv("MEMOLITE_DB", str(tmp_path / "s.db"))
    monkeypatch.delenv("MEMOLITE_OFF", raising=False)
    monkeypatch.delenv("MEMOLITE_AUTOPATCH", raising=False)
    al._STORE = None
    fake_oa = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **k: None))
    )
    al._patch_instance(fake_oa, True)
    fake_an = SimpleNamespace(messages=SimpleNamespace(create=lambda **k: None))
    al._patch_instance(fake_an, True)
    al._patch_instance(object(), True)
    if al._STORE is not None:
        al._STORE.close()
    al._STORE = None


def test_off_disables(monkeypatch):
    import memolite.autoload as al

    monkeypatch.setenv("MEMOLITE_OFF", "1")
    assert al._off() is True
    monkeypatch.delenv("MEMOLITE_OFF")
    monkeypatch.setenv("MEMOLITE_AUTOPATCH", "0")
    assert al._off() is True
