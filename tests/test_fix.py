import tempfile
from pathlib import Path

import pytest

from memolite import Config, MemoryStore
from memolite.exceptions import ValidationError
from memolite.scoring import frequency_factor


def test_extra_pragmas_validation() -> None:
    with pytest.raises(ValidationError):
        MemoryStore(":memory:", Config(extra_pragmas={"bad;key": "1"}))
    with pytest.raises(ValidationError):
        MemoryStore(":memory:", Config(extra_pragmas={"cache_size": "bad value!"}))
    # valid
    s = MemoryStore(":memory:", Config(extra_pragmas={"cache_size": "-64000"}))
    s.close()


def test_session_isolation() -> None:
    s = MemoryStore(":memory:", Config(auto_consolidate_every=0))
    s.remember("secret s1", importance=0.9, session_id="s1")
    s.remember("global fact", importance=0.8)
    # s2 should not see s1 secret, but should see global
    res = s.recall("secret", session="s2", limit=5)
    assert not any("secret s1" in m.content for m in res.memories)
    res2 = s.recall("global", session="s2", limit=5)
    assert any("global" in m.content for m in res2.memories)
    # global recall without session sees all
    res3 = s.recall("secret", limit=5)
    assert any("secret s1" in m.content for m in res3.memories)
    s.close()


def test_json_validation() -> None:
    s = MemoryStore(":memory:", Config(auto_consolidate_every=0))
    t = s.add_turn(session="s1", role="user", content="hi")
    with pytest.raises(ValidationError):
        s.add_tool_call(t.id, name="x", args={"a": {1, 2}})  # type: ignore[dict-item]
    with pytest.raises(ValidationError):
        s.create_session("bad", meta={"x": {1, 2}})  # type: ignore[dict-value]
    s.close()


def test_fts_special_chars_not_crash() -> None:
    s = MemoryStore(":memory:", Config(auto_consolidate_every=0))
    s.remember("hello world", importance=0.9)
    for q in ["hello OR world", "hello*", '"hello"', ""]:
        r = s.recall(q, limit=5)
        assert isinstance(r.memories, list)
    s.close()


def test_frequency_negative() -> None:
    assert frequency_factor(-1) == 0
    assert frequency_factor(-100) == 0


def test_persistence_counter() -> None:
    with tempfile.TemporaryDirectory() as d:
        db = Path(d) / "p.db"
        s = MemoryStore(db, Config(auto_consolidate_every=2))
        s.add_turn(session="s1", role="user", content="Remember cats")
        s.add_turn(session="s1", role="user", content="x")
        c1 = s.stats()["memories"]
        s.close()
        s2 = MemoryStore(db, Config(auto_consolidate_every=2))
        s2.add_turn(session="s1", role="user", content="Remember dogs")
        s2.add_turn(session="s1", role="user", content="y")
        c2 = s2.stats()["memories"]
        assert c2 > c1
        s2.close()


def test_prune_validation() -> None:
    s = MemoryStore(":memory:", Config(auto_consolidate_every=0))
    with pytest.raises(ValidationError):
        s.prune(keep=-1)
    s.close()


def test_recall_session_filter_empty_query() -> None:
    s = MemoryStore(":memory:", Config(auto_consolidate_every=0))
    s.remember("a", importance=0.9, session_id="s1")
    s.remember("b", importance=0.9, session_id="s2")
    res = s.recall("", session="s1", limit=10)
    # should not see s2
    assert not any(m.session_id == "s2" for m in res.memories)
    s.close()
