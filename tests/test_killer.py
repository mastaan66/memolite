import tempfile
from pathlib import Path

from memolite import Config, MemoryStore


def test_health_check() -> None:
    s = MemoryStore(":memory:", Config(auto_consolidate_every=0))
    h = s.health_check()
    assert h["integrity_ok"] is True
    assert h["fts_ok"] is True
    assert "db_size_bytes" in h
    assert h["stats"]["memories"] == 0
    s.close()


def test_backup_and_restore() -> None:
    with tempfile.TemporaryDirectory() as d:
        db = Path(d) / "a.db"
        backup = Path(d) / "b.db"
        s = MemoryStore(db, Config(auto_consolidate_every=0))
        s.remember("hello", importance=0.9)
        s.backup(backup)
        assert backup.exists()
        assert backup.stat().st_size > 0
        # backup is readable
        s2 = MemoryStore(backup, Config(auto_consolidate_every=0))
        assert s2.stats()["memories"] == 1
        s2.close()
        s.close()


def test_export_import() -> None:
    with tempfile.TemporaryDirectory() as d:
        db = Path(d) / "a.db"
        exp = Path(d) / "out.json"
        s = MemoryStore(db, Config(auto_consolidate_every=0))
        s.create_session("sess1", meta={"x": 1})
        s.add_turn(session="sess1", role="user", content="hi")
        s.remember("fact", importance=0.8, session_id="sess1")
        counts = s.export_json(exp)
        assert counts["memories"] == 1
        assert exp.exists()
        # import into new db
        db2 = Path(d) / "b.db"
        s2 = MemoryStore(db2, Config(auto_consolidate_every=0))
        imp = s2.import_json(exp)
        assert imp["memories"] == 1
        assert s2.stats()["memories"] == 1
        s.close()
        s2.close()


def test_vacuum_and_explain() -> None:
    s = MemoryStore(":memory:", Config(auto_consolidate_every=0))
    s.remember("test vacuum fact", importance=0.7)
    s.vacuum()  # should not raise
    exp = s.explain_recall("vacuum", limit=2)
    assert exp["returned"] >= 1
    assert "took_ms" in exp
    assert exp["prompt_chars"] >= 0
    s.close()


def test_nan_inf_rejected() -> None:
    import pytest

    from memolite.exceptions import ValidationError

    s = MemoryStore(":memory:", Config(auto_consolidate_every=0))
    with pytest.raises(ValidationError):
        s.remember("x", importance=float("nan"))
    with pytest.raises(ValidationError):
        s.remember("x", importance=float("inf"))
    s.close()


def test_consolidator_cap() -> None:
    def evil(texts: list[str]) -> list[dict[str, object]]:
        return [
            {"content": f"evil {i}", "summary": f"evil {i}", "importance": 0.9, "kind": "semantic"}
            for i in range(1000)
        ]

    s = MemoryStore(":memory:", Config(auto_consolidate_every=2, consolidator=evil))
    s.add_turn(session="s", role="user", content="hello")
    s.add_turn(session="s", role="user", content="world")
    # capped to 10, not 1000
    assert s.stats()["memories"] <= 10
    s.close()


def test_like_huge_query() -> None:
    s = MemoryStore(":memory:", Config(auto_consolidate_every=0))
    s.remember("normal", importance=0.9)
    big = "A" * 100000
    res = s.recall(big, limit=2)
    assert len(res.memories) >= 1  # fallback to top
    s.close()


def test_prune_batch() -> None:
    s = MemoryStore(":memory:", Config(auto_consolidate_every=0, max_memories=1000))
    for i in range(3000):
        s.remember(f"m {i}", importance=0.5)
    deleted = s.prune(keep=1000)
    assert deleted == 2000
    assert s.stats()["memories"] == 1000
    s.close()
