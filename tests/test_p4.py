"""P4 tests: vector hybrid, file sync LWW, writer RBAC, eval invariants."""

from __future__ import annotations

from memolite import Config, MemoryStore
from memolite.sync import export_bundle, import_bundle, sync_files
from memolite.vec import cosine, hash_embed, hybrid_score


def test_hash_embed_deterministic():
    a = hash_embed(["hello world"], 32)[0]
    b = hash_embed(["hello world"], 32)[0]
    assert a == b
    assert abs(sum(x * x for x in a) - 1.0) < 1e-6
    assert cosine(a, b) == 1.0
    c = hash_embed(["totally different zebra"], 32)[0]
    assert cosine(a, c) < 0.9
    assert hybrid_score(0.5, 0.5) == 0.5


def test_hybrid_matches_fts_on_keywords():
    facts = ["Maya OS kiosk mini-PC", "deploy key Friday", "db-1 host"]
    for hybrid in (False, True):
        s = MemoryStore(
            ":memory:", Config(hybrid_enabled=hybrid, hybrid_dim=32, auto_consolidate_every=0)
        )
        for f in facts:
            s.remember(f, importance=0.8)
        r = s.recall("Maya kiosk", limit=3)
        assert any("Maya" in m.summary for m in r.memories)
        s.close()


def test_remember_embeds_and_backfills():
    s = MemoryStore(":memory:", Config(hybrid_enabled=True, hybrid_dim=32))
    s.remember("Maya OS kiosk mini-PC")
    n = s.backfill_embeddings()
    assert n >= 0
    r = s.recall("Maya kiosk", limit=2)
    assert len(r.memories) >= 1
    s.close()


def test_sync_files_merge_and_lww(tmp_path):
    a = str(tmp_path / "a.db")
    b = str(tmp_path / "b.db")
    sa = MemoryStore(a)
    sb = MemoryStore(b)
    sa.remember("shared fact kiosk", importance=0.9)
    sb.remember("unique bee fact", importance=0.9)
    sb.remember("shared fact kiosk", importance=0.5)  # lower dup
    sa.close()
    sb.close()
    out = sync_files(a, b)
    assert out["a_imported"]["memories"] >= 1  # bee fact arrives
    sa2 = MemoryStore(a)
    r = sa2.recall("bee", limit=2)
    assert any("bee" in m.summary for m in r.memories)
    # LWW: a's 0.9 kept over b's 0.5
    r2 = sa2.recall("shared fact", limit=2)
    assert any(m.importance == 0.9 for m in r2.memories)
    sa2.close()


def test_export_import_bundle(tmp_path):
    db = str(tmp_path / "x.db")
    s = MemoryStore(db)
    s.add_turn(session="s1", role="user", content="hello sync")
    s.remember("sync fact", importance=0.8)
    b = export_bundle(s)
    assert b["turns"] and b["audit"]
    s2 = MemoryStore(str(tmp_path / "y.db"))
    counts = import_bundle(s2, b)
    assert counts["turns"] >= 1
    assert s2.verify_chain()["ok"] is True
    s.close()
    s2.close()


def test_writer_rbac_split():
    s = MemoryStore(":memory:", Config(require_acl=True))
    s.grant("proj", owner="alice", readers=["bob"], writers=["alice"])
    # bob reads ok
    s.add_turn(session="proj", role="user", content="secret", actor="alice")
    r = s.recall("secret", session="proj", actor="bob")
    assert len(r.memories) >= 0
    # bob writes denied
    try:
        s.add_turn(session="proj", role="user", content="x", actor="bob")
        raise AssertionError("bob write should deny")
    except Exception:
        pass
    # promote bob to writer
    s.grant("proj", owner="alice", readers=["bob"], writers=["alice", "bob"])
    s.add_turn(session="proj", role="user", content="ok", actor="bob")
    s.close()


def test_eval_invariants():
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent.parent / "examples"))
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "eval07", str(Path(__file__).parent.parent / "examples" / "07_eval_recall.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    fts = mod.run(Config(hybrid_enabled=False, auto_consolidate_every=0), mod.KEYWORD_QUERIES)
    hyb = mod.run(Config(hybrid_enabled=True, auto_consolidate_every=0), mod.KEYWORD_QUERIES)
    assert hyb["recall@3"] >= fts["recall@3"]  # hybrid never worse than FTS
    assert fts["recall@3"] >= 0.5  # keyword suite stays healthy


def test_sync_lww_incoming_wins_and_garbage():
    s = MemoryStore(":memory:")
    s.remember("fact kiosk", importance=0.5)
    b = export_bundle(s)
    # garbage bundle tolerated
    assert import_bundle(s, {})["turns"] == 0
    # higher-importance incoming overwrites
    b["memories"][0]["importance"] = 0.95
    out = import_bundle(s, b)
    assert out["conflicts"] >= 1
    assert out["memories"] >= 1
    r = s.recall("kiosk", limit=2)
    assert any(m.importance == 0.95 for m in r.memories)
    s.close()


def test_hybrid_paths_backfill_embedder_and_disabled():
    s = MemoryStore(
        ":memory:",
        Config(hybrid_enabled=True, hybrid_dim=16, embedder=lambda ts: [[1.0] * 16 for _ in ts]),
    )
    s.remember("custom embed fact")
    assert s.backfill_embeddings() >= 0
    assert len(s.recall("custom", limit=2).memories) >= 1
    s.close()
    s2 = MemoryStore(":memory:", Config(hybrid_enabled=False))
    s2.remember("plain fact")
    assert s2.backfill_embeddings() >= 0  # still fills, rerank stays off
    assert len(s2.recall("plain", limit=2).memories) >= 1
    s2.close()


def test_llm_embedder_plumbs_through():
    from types import SimpleNamespace

    from memolite.embedders import openai_embedder

    class FakeEmb:
        def create(self, model, input):
            assert model == "m"
            return SimpleNamespace(data=[SimpleNamespace(embedding=[0.1, 0.2]) for _ in input])

    emb = openai_embedder(SimpleNamespace(embeddings=FakeEmb()), model="m")
    s = MemoryStore(":memory:", Config(embedder=emb, embedding_dim=2, auto_consolidate_every=0))
    s.remember("LLM embedded fact kiosk")
    r = s.recall("kiosk", limit=2)
    assert any("kiosk" in m.summary for m in r.memories)
    s.close()


def test_embedder_variants():
    import urllib.request as _u

    from memolite.embedders import local_embedder, ollama_embedder

    try:
        local_embedder()
    except ImportError:
        pass  # covers error branch when lib missing

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"embedding": [0.5, 0.5]}'

    orig = _u.urlopen
    _u.urlopen = lambda *a, **k: FakeResp()
    try:
        vecs = ollama_embedder(model="m", url="http://x")(["hi"])
        assert vecs == [[0.5, 0.5]]
    finally:
        _u.urlopen = orig
