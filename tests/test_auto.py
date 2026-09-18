"""Fully-auto chat loop tests: no explicit remember()."""

from __future__ import annotations

from memolite import Config, MemoryStore


def fake_llm(messages):
    # echo user msg as assistant reply with a fact
    user = messages[-1]["content"]
    return f"noted: {user}"


def test_chat_stores_and_recalls_implicitly():
    store = MemoryStore(":memory:")
    out1 = store.chat("s1", "I prefer concise Python with type hints", fake_llm)
    assert "noted" in out1["response"]
    assert len(out1["memories"]) >= 1
    # second turn finds first without explicit remember
    out2 = store.chat("s1", "how should I write code?", fake_llm)
    assert out2["recall_count"] >= 1
    r = store.recall("python type hints", session="s1")
    assert any("Python" in m.content or "python" in m.content.lower() for m in r.memories)
    store.close()


def test_chat_no_dupes():
    store = MemoryStore(":memory:")
    store.chat("s1", "My name is Ada", fake_llm)
    store.chat("s1", "My name is Ada", fake_llm)
    r = store.recall("Ada", session="s1", limit=10)
    names = [m for m in r.memories if "Ada" in m.content]
    assert len(names) <= 2
    store.close()


def test_chat_opt_out():
    store = MemoryStore(":memory:", Config(auto_capture=False))
    out = store.chat("s1", "I prefer Rust", fake_llm)
    assert out["memories"] == []
    # turns still stored
    assert store.stats()["turns"] == 2
    store.close()


def test_adapter_chat():
    from memolite import plug

    store = MemoryStore(":memory:")
    a = plug(store, llm="generic")
    out = a.chat("s1", "I work on SHUCHI sanitiser", fake_llm)
    assert "response" in out
    store.close()
