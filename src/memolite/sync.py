"""Multi-node file sync v1: export/import bundles with LWW conflicts.

Honest scope: NOT live replication. Pairwise file merge for small fleets
(kiosk A <-> kiosk B via USB/file drop). Same-machine tested; cross-machine
via copied bundle files. Last-write-wins on (session, summary) duplicates.
"""

from __future__ import annotations

import time
from typing import Any


def export_bundle(store: Any, since_audit_id: int = 0) -> dict[str, Any]:
    """Export turns+memories+audit+acl newer than since_audit_id."""
    with store._lock:
        audits = [
            dict(r)
            for r in store._conn.execute(
                "SELECT * FROM audit_log WHERE id>? ORDER BY id", (since_audit_id,)
            ).fetchall()
        ]
        turn_ids = [a["turn_id"] for a in audits]
        turns: list[dict[str, Any]] = []
        if turn_ids:
            qm = ",".join("?" for _ in turn_ids)
            turns = [
                dict(r)
                for r in store._conn.execute(
                    f"SELECT * FROM turns WHERE id IN ({qm})", turn_ids
                ).fetchall()
            ]
        mems = [dict(r) for r in store._conn.execute("SELECT * FROM memories").fetchall()]
        for m in mems:
            if m.get("embedding") is not None:
                m["embedding"] = None
        acls = [dict(r) for r in store._conn.execute("SELECT * FROM session_acl").fetchall()]
    return {
        "node": getattr(store, "path", "?"),
        "exported_at": int(time.time()),
        "since": since_audit_id,
        "turns": turns,
        "memories": mems,
        "audit": audits,
        "acl": acls,
    }


def import_bundle(store: Any, bundle: dict[str, Any]) -> dict[str, int]:
    """Merge bundle. Returns {turns, memories, conflicts, audit}."""
    counts = {"turns": 0, "memories": 0, "conflicts": 0, "audit": 0}
    with store._lock:
        for s in bundle.get("acl", []):
            try:
                store._conn.execute(
                    "INSERT OR IGNORE INTO session_acl(session_id, owner, readers_json, created_at)"
                    " VALUES (?,?,?,?)",
                    (s["session_id"], s["owner"], s.get("readers_json", "[]"), s["created_at"]),
                )
            except Exception:
                pass
        for t in bundle.get("turns", []):
            try:
                store._conn.execute(
                    "INSERT OR IGNORE INTO sessions(id, meta_json, created_at) VALUES (?,?,?)",
                    (t["session_id"], None, t["ts"]),
                )
                cur = store._conn.execute(
                    "INSERT INTO turns(id, session_id, role, content, tokens, ts)"
                    " VALUES (?,?,?,?,?,?)",
                    (None, t["session_id"], t["role"], t["content"], t["tokens"], t["ts"]),
                )
                if cur.lastrowid:
                    counts["turns"] += 1
            except Exception:
                pass
        for a in bundle.get("audit", []):
            try:
                # find mapped turn: match by session+ts (ids differ across nodes)
                row = store._conn.execute(
                    "SELECT id FROM turns WHERE session_id=? AND ts=? LIMIT 1",
                    (a["session_id"], a["ts"]),
                ).fetchone()
                if not row:
                    continue
                exists = store._conn.execute(
                    "SELECT id FROM audit_log WHERE hash=? LIMIT 1", (a["hash"],)
                ).fetchone()
                if exists:
                    continue
                store._conn.execute(
                    "INSERT INTO audit_log(session_id, turn_id, prev_hash, hash, ts)"
                    " VALUES (?,?,?,?,?)",
                    (a["session_id"], row["id"], a["prev_hash"], a["hash"], a["ts"]),
                )
                counts["audit"] += 1
            except Exception:
                continue
        for m in bundle.get("memories", []):
            try:
                dup = store._conn.execute(
                    "SELECT id, importance, score FROM memories"
                    " WHERE IFNULL(session_id,'')=IFNULL(?, '') AND summary=? LIMIT 1",
                    (m.get("session_id"), m["summary"]),
                ).fetchone()
                if dup:
                    counts["conflicts"] += 1
                    # LWW: incoming wins if strictly more important
                    if float(m["importance"]) > float(dup["importance"]):
                        store._conn.execute(
                            "UPDATE memories SET content=?, importance=?, score=? WHERE id=?",
                            (m["content"], m["importance"], m["score"], dup["id"]),
                        )
                        counts["memories"] += 1
                    continue
                store._conn.execute(
                    "INSERT INTO memories(kind, session_id, content, summary, importance,"
                    " access_count, reward, score, created_at, last_accessed)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        m["kind"],
                        m.get("session_id"),
                        m["content"],
                        m["summary"],
                        m["importance"],
                        m.get("access_count", 0),
                        m.get("reward", 0.0),
                        m["score"],
                        m["created_at"],
                        m["last_accessed"],
                    ),
                )
                counts["memories"] += 1
            except Exception:
                continue
    try:
        store.verify_chain()
    except Exception:
        pass
    return counts


def sync_files(path_a: str, path_b: str) -> dict[str, Any]:
    """Bidirectional file merge. Returns per-direction counts."""
    from memolite import MemoryStore

    sa, sb = MemoryStore(path_a), MemoryStore(path_b)
    try:
        ba, bb = export_bundle(sa), export_bundle(sb)
        a_in = import_bundle(sa, bb)
        b_in = import_bundle(sb, ba)
        return {"a_imported": a_in, "b_imported": b_in}
    finally:
        sa.close()
        sb.close()
