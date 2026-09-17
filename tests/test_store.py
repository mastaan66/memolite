from memolite import Config, MemoryStore


def test_add_turn_and_recall() -> None:
    store = MemoryStore(":memory:", Config(auto_consolidate_every=0))
    store.add_turn(session="s1", role="user", content="I prefer python")
    store.remember("user prefers python, no classes", importance=0.9)
    res = store.recall("python", session="s1", limit=2)
    assert len(res.memories) >= 1
    assert any("python" in m.summary.lower() for m in res.memories)
    assert len(res.stm) == 1
    store.close()


def test_consolidate_heuristic() -> None:
    store = MemoryStore(":memory:", Config(auto_consolidate_every=2))
    store.add_turn(session="s1", role="user", content="Remember I work on SHUCHI kiosk")
    store.add_turn(session="s1", role="user", content="another turn")
    # should have auto-consolidated
    res = store.recall("SHUCHI", session="s1", limit=5)
    assert any("SHUCHI" in m.content for m in res.memories)
    store.close()


def test_tool_call_creates_procedural() -> None:
    store = MemoryStore(":memory:", Config(auto_consolidate_every=0))
    t = store.add_turn(session="s1", role="assistant", content="scanning")
    store.add_tool_call(t.id, name="clamav", args={"p": "/usb"}, result={"ok": True}, success=True)
    res = store.recall("clamav", limit=5)
    assert any(m.kind == "procedural" for m in res.memories)
    store.close()


def test_feedback_and_prune() -> None:
    store = MemoryStore(":memory:", Config(auto_consolidate_every=0, max_memories=2))
    m1 = store.remember("a", importance=0.1)
    _m2 = store.remember("b", importance=0.9)
    store.remember("c", importance=0.5)
    store.feedback(m1.id, reward=0.0)
    deleted = store.prune(keep=2)
    assert deleted == 1
    store.close()


def test_prompt_helper() -> None:
    store = MemoryStore(":memory:", Config(auto_consolidate_every=0))
    store.add_turn(session="s1", role="user", content="hello")
    store.remember("fact", importance=0.8)
    res = store.recall("fact", session="s1", limit=1)
    assert "Long-term" in res.prompt
    assert "Recent" in res.prompt
    store.close()
