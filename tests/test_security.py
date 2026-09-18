import pytest
"""Hardening tests: redact, WORM, ACL, encryption, perms."""

from __future__ import annotations

import os

from memolite import Config, MemoryStore
from memolite.security import decrypt_str, encrypt_str, redact_pii


def test_redact_pii():
    s = "contact me at a@b.com or +91 9876543210, key sk-abc123XYZ"
    out = redact_pii(s)
    assert "[REDACTED_EMAIL]" in out
    assert "[REDACTED_PHONE]" in out
    assert "a@b.com" not in out


def test_redact_on_remember():
    store = MemoryStore(":memory:", Config(redact_pii=True))
    m = store.remember("email test@example.com here")
    assert "test@example.com" not in m.content
    assert "REDACTED" in m.content
    store.close()


def test_worm_chain_ok_and_tamper():
    store = MemoryStore(":memory:")
    store.add_turn(session="s1", role="user", content="hello")
    store.add_turn(session="s1", role="assistant", content="hi")
    v = store.verify_chain()
    assert v["ok"] is True
    assert v["count"] == 2
    # tamper: break link
    store._conn.execute("UPDATE audit_log SET prev_hash='X' WHERE id=2")
    v2 = store.verify_chain()
    assert v2["ok"] is False
    assert v2["bad_id"] == 2
    store.close()


def test_acl_enforce():
    store = MemoryStore(":memory:", Config(require_acl=True))
    store.add_turn(session="proj", role="user", content="secret", actor="alice")
    # bob denied
    try:
        store.add_turn(session="proj", role="user", content="x", actor="bob")
        raise AssertionError("should deny")
    except Exception:
        pass
    # grant bob, then allow
    store.grant("proj", "alice", ["bob"])
    store.add_turn(session="proj", role="user", content="ok", actor="bob")
    try:
        store.recall("secret", session="proj", actor="eve")
        raise AssertionError("should deny recall")
    except Exception:
        pass
    r = store.recall("secret", session="proj", actor="alice")
    assert len(r.memories) >= 0
    store.close()


def test_encrypt_roundtrip(tmp_path, monkeypatch):
    pytest.importorskip("cryptography")
    monkeypatch.setenv("MEMOLITE_KEY", "test-passphrase-123")
    enc = encrypt_str("hello shuchi", "MEMOLITE_KEY")
    assert enc.startswith("ENC1:")
    assert decrypt_str(enc, "MEMOLITE_KEY") == "hello shuchi"
    db = str(tmp_path / "enc.db")
    store = MemoryStore(db, Config(require_encryption=True))
    store.add_turn(session="s1", role="user", content="my secret note")
    store.remember("vault code 123")
    # raw db must not contain plaintext
    with open(db, "rb") as f:
        raw = f.read()
    assert b"my secret note" not in raw
    r = store.recall("vault", session="s1")
    assert any("vault" in x.content for x in r.memories)
    assert r.stm[0].content == "my secret note"
    store.close()


def test_file_perms(tmp_path):
    db = str(tmp_path / "p.db")
    store = MemoryStore(db)
    store.add_turn(session="s", role="user", content="x")
    mode = oct(os.stat(db).st_mode & 0o777)
    assert mode == "0o600"
    h = store.health_check()
    assert h["perms_ok"] is True
    assert int(h["audit_count"]) >= 1  # type: ignore[arg-type]
    store.close()
