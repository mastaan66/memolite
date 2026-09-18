"""Sync MemoryStore - core of memolite."""

from __future__ import annotations

import json
import math
import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from memolite.config import Config
from memolite.consolidator import heuristic_consolidate
from memolite.exceptions import NotFoundError, ValidationError
from memolite.models import Memory, RecallResult, Session, ToolCall, Turn
from memolite.schema import SCHEMA_SQL
from memolite.scoring import composite_score, recency_factor
from memolite.security import (
    chain_hash,
    decrypt_str,
    encrypt_str,
    file_perms_ok,
    harden_file,
    is_encrypted,
    redact_pii,
)

_PRAGMA_KEY_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
_PRAGMA_VAL_RE = re.compile(r"^[a-zA-Z0-9_\-\+\.]+$")


class MemoryStore:
    """SQLite-backed agentic memory. Thread-safe via RLock + WAL + busy_timeout."""

    def __init__(self, path: str | Path, config: Config | None = None) -> None:
        self.path = str(path)
        self.config = config or Config()
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        # busy_timeout must be int
        try:
            timeout = int(self.config.busy_timeout_ms)
        except Exception:
            timeout = 5000
        self._conn.execute(f"PRAGMA busy_timeout={timeout}")
        if self.config.wal_mode and self.path != ":memory:":
            try:
                self._conn.execute("PRAGMA journal_mode=WAL")
            except sqlite3.OperationalError:
                pass
        if self.config.foreign_keys:
            self._conn.execute("PRAGMA foreign_keys=ON")
        for k, v in self.config.extra_pragmas.items():
            if not _PRAGMA_KEY_RE.match(k):
                raise ValidationError(f"invalid pragma key: {k}")
            if not isinstance(v, str) or not _PRAGMA_VAL_RE.match(v):
                raise ValidationError(f"invalid pragma value for {k}: {v!r}")
            # safe after regex
            self._conn.execute(f"PRAGMA {k}={v}")
        with self._lock:
            self._conn.executescript(SCHEMA_SQL)
            # migrate old DBs: writers column added in P4
            try:
                cols = [
                    r[1] for r in self._conn.execute("PRAGMA table_info(session_acl)").fetchall()
                ]
                if "writers_json" not in cols:
                    self._conn.execute("ALTER TABLE session_acl ADD COLUMN writers_json TEXT")
            except sqlite3.OperationalError:
                pass
        if self.path != ":memory:":
            harden_file(self.path)

    def _enc(self, text: str) -> str:
        if self.config.require_encryption:
            return encrypt_str(text, self.config.encryption_key_env)
        return text

    def _dec(self, token: str) -> str:
        if is_encrypted(token):
            return decrypt_str(token, self.config.encryption_key_env)
        return token

    def _redact(self, text: str) -> str:
        if self.config.redact_pii:
            return redact_pii(text)
        return text

    # ---- ACL ----

    def grant(
        self,
        session_id: str,
        owner: str,
        readers: list[str] | None = None,
        writers: list[str] | None = None,
    ) -> None:
        """Set owner + readers + writers for a session. Creates session if missing."""
        import time as _t

        self.create_session(session_id)
        readers_json = json.dumps(readers or [])
        writers_json = json.dumps(writers if writers is not None else (readers or []))
        now = int(_t.time())
        with self._lock:
            try:
                self._conn.execute(
                    "INSERT INTO session_acl(session_id, owner, readers_json, writers_json,"
                    " created_at) VALUES (?,?,?,?,?)"
                    " ON CONFLICT(session_id) DO UPDATE SET owner=?, readers_json=?,"
                    " writers_json=?",
                    (
                        session_id,
                        owner,
                        readers_json,
                        writers_json,
                        now,
                        owner,
                        readers_json,
                        writers_json,
                    ),
                )
            except sqlite3.OperationalError:
                # old schema without writers_json
                self._conn.execute(
                    "INSERT INTO session_acl(session_id, owner, readers_json, created_at)"
                    " VALUES (?,?,?,?)"
                    " ON CONFLICT(session_id) DO UPDATE SET owner=?, readers_json=?",
                    (session_id, owner, readers_json, now, owner, readers_json),
                )

    def _check_acl(self, session_id: str | None, actor: str | None, mode: str = "write") -> None:
        if not self.config.require_acl or not session_id:
            return
        with self._lock:
            try:
                row = self._conn.execute(
                    "SELECT owner, readers_json, writers_json FROM session_acl WHERE session_id=?",
                    (session_id,),
                ).fetchone()
            except sqlite3.OperationalError:
                row = self._conn.execute(
                    "SELECT owner, readers_json FROM session_acl WHERE session_id=?",
                    (session_id,),
                ).fetchone()
        if not row:
            # first writer becomes owner
            if actor:
                self.grant(session_id, actor)
                return
            raise ValidationError("acl: unknown session, actor required")
        import json as _j

        def _load(key: str) -> list[str]:
            try:
                keys = list(row.keys())
                v = row[key] if key in keys else None
                loaded: list[str] = _j.loads(v or "[]")
                return loaded
            except Exception:
                return []

        readers = _load("readers_json")
        writers = _load("writers_json") or readers  # backward compat: readers could write
        if actor is None:
            raise ValidationError("acl: access denied")
        if actor == row["owner"]:
            return
        if mode == "read":
            if actor not in readers and actor not in writers:
                raise ValidationError("acl: access denied")
        else:
            if actor not in writers:
                raise ValidationError("acl: access denied")

    # ---- sessions / turns ----

    def create_session(self, session_id: str, meta: dict[str, object] | None = None) -> Session:
        if not session_id or not session_id.strip():
            raise ValidationError("session_id required")
        now = int(time.time())
        meta_json = None
        if meta is not None:
            try:
                meta_json = json.dumps(meta)
            except (TypeError, ValueError) as e:
                raise ValidationError(f"meta not JSON serializable: {e}") from e
        with self._lock:
            try:
                self._conn.execute(
                    "INSERT INTO sessions(id, meta_json, created_at) VALUES (?,?,?)",
                    (session_id, meta_json, now),
                )
            except sqlite3.IntegrityError:
                pass  # idempotent
        return Session(id=session_id, meta=meta, created_at=now)

    def add_turn(
        self,
        session: str,
        role: str,
        content: str,
        tokens: int | None = None,
        actor: str | None = None,
    ) -> Turn:
        if not session or not session.strip() or not role or content is None:
            raise ValidationError("session/role/content required")
        if role not in {"user", "assistant", "system", "tool"}:
            raise ValidationError(f"invalid role {role}")
        self._check_acl(session, actor)
        self.create_session(session)
        now = int(time.time())
        safe = self._redact(content)
        stored = self._enc(safe)
        toks = tokens if tokens is not None else max(0, len(safe) // 4)
        # Cross-process atomic turn+chain: BEGIN IMMEDIATE serializes writers.
        # Threading RLock alone cannot stop two processes reading the same prev hash.
        with self._lock:
            try:
                self._conn.execute("BEGIN IMMEDIATE")
            except sqlite3.OperationalError:
                pass  # already in transaction; busy_timeout still applies
            try:
                cur = self._conn.execute(
                    "INSERT INTO turns(session_id, role, content, tokens, ts) VALUES (?,?,?,?,?)",
                    (session, role, stored, toks, now),
                )
                turn_id = cur.lastrowid or 0
                if self.config.worm_enabled:
                    prev_row = self._conn.execute(
                        "SELECT hash FROM audit_log ORDER BY id DESC LIMIT 1"
                    ).fetchone()
                    prev = str(prev_row["hash"]) if prev_row else "GENESIS"
                    h = chain_hash(prev, session, role, safe, now)
                    self._conn.execute(
                        "INSERT INTO audit_log(session_id, turn_id, prev_hash, hash, ts)"
                        " VALUES (?,?,?,?,?)",
                        (session, turn_id, prev, h, now),
                    )
                try:
                    self._conn.execute("COMMIT")
                except sqlite3.OperationalError:
                    pass
            except Exception:
                try:
                    self._conn.execute("ROLLBACK")
                except sqlite3.OperationalError:
                    pass
                raise
        turn = Turn(id=turn_id, session_id=session, role=role, content=safe, tokens=toks, ts=now)
        # auto-consolidate based on DB count (persistent, not in-memory)
        if self.config.auto_consolidate_every:
            with self._lock:
                cnt_row = self._conn.execute(
                    "SELECT COUNT(*) FROM turns WHERE session_id=?", (session,)
                ).fetchone()
                cnt = int(cnt_row[0]) if cnt_row else 0
            if cnt % self.config.auto_consolidate_every == 0:
                self.consolidate(session)
        return turn

    def add_tool_call(
        self,
        turn_id: int,
        name: str,
        args: dict[str, object] | None = None,
        result: Any | None = None,
        success: bool | None = None,
    ) -> ToolCall:
        if not name or not name.strip():
            raise ValidationError("tool name required")
        with self._lock:
            row = self._conn.execute("SELECT id FROM turns WHERE id=?", (turn_id,)).fetchone()
            if not row:
                raise NotFoundError(f"turn {turn_id} not found")
        # validate json serializable early
        args_json = None
        result_json = None
        if args is not None:
            try:
                args_json = json.dumps(args)
            except (TypeError, ValueError) as e:
                raise ValidationError(f"args not JSON serializable: {e}") from e
        if result is not None:
            try:
                result_json = json.dumps(result)
            except (TypeError, ValueError) as e:
                raise ValidationError(f"result not JSON serializable: {e}") from e
        now = int(time.time())
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO tool_calls(turn_id, name, args_json, result_json, success, ts) VALUES (?,?,?,?,?,?)",
                (
                    turn_id,
                    name,
                    args_json,
                    result_json,
                    1 if success else 0 if success is False else None,
                    now,
                ),
            )
            tool_id = cur.lastrowid or 0
        if success:
            try:
                preview = json.dumps(args)[:120] if args is not None else ""
            except Exception:
                preview = ""
            try:
                self.remember(
                    f"Tool {name} succeeded for {preview}",
                    kind="procedural",
                    importance=0.6,
                )
            except Exception:
                pass
        return ToolCall(
            id=tool_id, turn_id=turn_id, name=name, args=args, result=result, success=success
        )

    # ---- memories ----

    def remember(
        self,
        content: str,
        *,
        summary: str | None = None,
        kind: str = "semantic",
        session_id: str | None = None,
        importance: float = 0.5,
        reward: float = 0.0,
        actor: str | None = None,
    ) -> Memory:
        if not content or not content.strip():
            raise ValidationError("content empty")
        if kind not in {"semantic", "procedural", "episodic"}:
            raise ValidationError(f"invalid kind {kind}")
        # clamp importance/reward + reject NaN/Inf
        try:
            importance_f = float(importance)
        except Exception:
            raise ValidationError("importance must be numeric") from None
        if math.isnan(importance_f) or math.isinf(importance_f):
            raise ValidationError("importance must be finite [0,1]")
        try:
            reward_f = float(reward)
        except Exception:
            raise ValidationError("reward must be numeric") from None
        if math.isnan(reward_f) or math.isinf(reward_f):
            raise ValidationError("reward must be finite [0,1]")
        # ensure session exists if provided (FK)
        if session_id:
            self._check_acl(session_id, actor)
            self.create_session(session_id)
        now = int(time.time())
        safe_content = self._redact(content)
        safe_summary = self._redact(summary) if summary else safe_content[:200]
        stored_content = self._enc(safe_content)
        stored_summary = self._enc(safe_summary)
        sc = composite_score(
            importance_f,
            0,
            now,
            reward_f,
            w_imp=self.config.weight_importance,
            w_freq=self.config.weight_frequency,
            w_rec=self.config.weight_recency,
            w_rew=self.config.weight_reward,
            half_life_days=self.config.recency_half_life_days,
            now=now,
        )
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO memories(kind, session_id, content, summary, importance, access_count, reward, score, created_at, last_accessed)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    kind,
                    session_id,
                    stored_content,
                    stored_summary,
                    importance_f,
                    0,
                    reward_f,
                    sc,
                    now,
                    now,
                ),
            )
            mid = cur.lastrowid or 0
            # hybrid embedding (best-effort, fail-open; embeds safe plaintext)
            try:
                if self.config.hybrid_enabled:
                    from memolite.vec import hash_embed, pack

                    dim = self.config.embedding_dim or self.config.hybrid_dim
                    if self.config.embedder is not None:
                        vecs = self.config.embedder([safe_content + " " + safe_summary])
                    else:
                        vecs = hash_embed([safe_content + " " + safe_summary], dim)
                    if vecs:
                        self._conn.execute(
                            "UPDATE memories SET embedding=?, need_embed=0 WHERE id=?",
                            (pack(vecs[0]), mid),
                        )
            except Exception:
                try:
                    self._conn.execute("UPDATE memories SET need_embed=1 WHERE id=?", (mid,))
                except Exception:
                    pass
            row = self._conn.execute("SELECT * FROM memories WHERE id=?", (mid,)).fetchone()
            assert row is not None
            return self._row_to_memory(row)

    def backfill_embeddings(self, limit: int = 1000) -> int:
        """Compute missing embeddings. Returns count filled."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT id FROM memories WHERE embedding IS NULL OR need_embed=1 LIMIT ?",
                (limit,),
            ).fetchall()
            ids = [r["id"] for r in rows]
        n = 0
        for mid in ids:
            try:
                with self._lock:
                    row = self._conn.execute(
                        "SELECT content, summary FROM memories WHERE id=?", (mid,)
                    ).fetchone()
                if not row:
                    continue
                text = self._dec(str(row["content"])) + " " + self._dec(str(row["summary"]))
                from memolite.vec import hash_embed, pack

                dim = self.config.embedding_dim or self.config.hybrid_dim
                if self.config.embedder is not None:
                    vecs = self.config.embedder([text])
                else:
                    vecs = hash_embed([text], dim)
                if vecs:
                    with self._lock:
                        self._conn.execute(
                            "UPDATE memories SET embedding=?, need_embed=0 WHERE id=?",
                            (pack(vecs[0]), mid),
                        )
                    n += 1
            except Exception:
                continue
        return n

    def _vec_rerank(self, query: str, scored: list[tuple[float, Any]]) -> list[tuple[float, Any]]:
        """Cosine rerank over FTS candidates. Fail-open to input order."""
        try:
            if not self.config.hybrid_enabled or not scored:
                return scored
            from memolite.vec import cosine, hash_embed, hybrid_score, unpack

            dim = self.config.embedding_dim or self.config.hybrid_dim
            if self.config.embedder is not None:
                qv = self.config.embedder([query])[0]
            else:
                qv = hash_embed([query], dim)[0]
            ids = [m.id for _, m in scored]
            qmarks = ",".join("?" for _ in ids)
            with self._lock:
                rows = self._conn.execute(
                    f"SELECT id, embedding FROM memories WHERE id IN ({qmarks})", ids
                ).fetchall()
            emb = {}
            for r in rows:
                if r["embedding"] is not None:
                    try:
                        emb[r["id"]] = unpack(bytes(r["embedding"]))
                    except Exception:
                        continue
            if not emb:
                return scored
            out = []
            for fused, m in scored:
                v = emb.get(m.id)
                sim = cosine(qv, v) if v is not None else 0.0
                out.append(
                    (
                        hybrid_score(
                            fused, sim, self.config.hybrid_w_fts, self.config.hybrid_w_vec
                        ),
                        m,
                    )
                )
            out.sort(key=lambda x: x[0], reverse=True)
            return out
        except Exception:
            return scored

    def consolidate(self, session: str) -> list[Memory]:
        """Distill recent turns into semantic memories. Returns new memories."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT content FROM turns WHERE session_id=? ORDER BY ts DESC LIMIT ?",
                (
                    session,
                    max(1, self.config.auto_consolidate_every * 2)
                    if self.config.auto_consolidate_every
                    else 16,
                ),
            ).fetchall()
        texts = []
        for r in rows:
            try:
                texts.append(self._dec(r["content"]))
            except Exception:
                continue
        texts = texts[::-1]
        if not texts:
            return []
        if self.config.consolidator:
            try:
                candidates = self.config.consolidator(texts)
            except Exception:
                candidates = heuristic_consolidate(texts)
        else:
            candidates = heuristic_consolidate(texts)
        created: list[Memory] = []
        for c in candidates:
            content = str(c.get("content", ""))
            if not content or not content.strip():
                continue
            summary_val = c.get("summary")
            summary = str(summary_val) if isinstance(summary_val, str) else None
            kind_val = c.get("kind", "semantic")
            kind = str(kind_val) if isinstance(kind_val, str) else "semantic"
            if kind not in {"semantic", "procedural", "episodic"}:
                kind = "semantic"
            imp_val = c.get("importance", 0.5)
            try:
                imp = float(imp_val)  # type: ignore[arg-type]
            except Exception:
                imp = 0.5
            if math.isnan(imp) or math.isinf(imp):
                imp = 0.5
            imp = max(0.0, min(1.0, imp))
            # dedup: skip if near-duplicate exists
            with self._lock:
                dup = self._conn.execute(
                    "SELECT id FROM memories WHERE summary=? LIMIT 1", (summary or content,)
                ).fetchone()
            if dup:
                continue
            m = self.remember(
                content,
                summary=summary,
                kind=kind,
                session_id=session,
                importance=imp,
            )
            created.append(m)
            # cap consolidator DoS: max 10 per consolidation + respect max_memories
            if len(created) >= 10:
                break
            if self.stats()["memories"] >= self.config.max_memories:
                break
        return created

    def recall(
        self,
        query: str,
        session: str | None = None,
        limit: int = 5,
        stm_limit: int | None = None,
        actor: str | None = None,
    ) -> RecallResult:
        if limit <= 0:
            raise ValidationError("limit must be >0")
        if session:
            self._check_acl(session, actor, mode="read")
        stm_n = stm_limit if stm_limit is not None else self.config.stm_window
        stm: list[Turn] = []
        if session:
            with self._lock:
                rows = self._conn.execute(
                    "SELECT * FROM turns WHERE session_id=? ORDER BY ts DESC LIMIT ?",
                    (session, stm_n),
                ).fetchall()
            stm = [
                Turn(
                    id=r["id"],
                    session_id=r["session_id"],
                    role=r["role"],
                    content=self._dec(r["content"]),
                    tokens=r["tokens"],
                    ts=r["ts"],
                )
                for r in rows[::-1]
            ]
        memories: list[Memory] = []
        tool_calls: list[ToolCall] = []

        if self.config.require_encryption:
            # ciphertext is unsearchable: fetch by score, decrypt, substring-rank in Python
            with self._lock:
                if session:
                    erows = self._conn.execute(
                        "SELECT * FROM memories WHERE session_id IS NULL"
                        " OR session_id = ? ORDER BY score DESC LIMIT ?",
                        (session, limit * 3),
                    ).fetchall()
                else:
                    erows = self._conn.execute(
                        "SELECT * FROM memories ORDER BY score DESC LIMIT ?",
                        (limit * 3,),
                    ).fetchall()
            cands = [self._row_to_memory(r) for r in erows]
            ql = query.strip().lower()
            ranked = sorted(
                cands,
                key=lambda m: (ql in (m.summary + " " + m.content).lower(), m.score),
                reverse=True,
            )
            memories = ranked[:limit]

        if not self.config.require_encryption and query and query.strip():
            # try FTS, fallback to LIKE/score
            try:
                q = query.replace('"', '""')
                fts_query = f'"{q}"' if " " in q.strip() else q
                with self._lock:
                    if session:
                        fts_rows = self._conn.execute(
                            """
                            SELECT m.*, rank FROM memories m
                            JOIN memories_fts f ON m.id = f.rowid
                            WHERE memories_fts MATCH ?
                              AND (m.session_id IS NULL OR m.session_id = ?)
                            ORDER BY rank LIMIT ?
                            """,
                            (fts_query, session, limit * 3),
                        ).fetchall()
                    else:
                        fts_rows = self._conn.execute(
                            """
                            SELECT m.*, rank FROM memories m
                            JOIN memories_fts f ON m.id = f.rowid
                            WHERE memories_fts MATCH ?
                            ORDER BY rank LIMIT ?
                            """,
                            (fts_query, limit * 3),
                        ).fetchall()
                if not fts_rows:
                    raise sqlite3.OperationalError("no fts hits")
                scored = []
                for r in fts_rows:
                    mem = self._row_to_memory(r)
                    rec = recency_factor(mem.last_accessed, self.config.recency_half_life_days)
                    fused = mem.score * 0.7 + rec * 0.3 - (r["rank"] * 0.05)
                    scored.append((fused, mem))
                scored.sort(key=lambda x: x[0], reverse=True)
                scored = self._vec_rerank(query, scored)
                memories = [m for _, m in scored[:limit]]
                # if session filter gave 0 but global fallback should try
                if not memories and session:
                    raise sqlite3.OperationalError("no fts hits for session filter")
            except sqlite3.OperationalError:
                # LIKE fallback with guard for pattern too complex / huge query
                q_stripped = query.strip()
                # truncate for LIKE to avoid "too complex" on 100kb queries
                like_q = f"%{q_stripped[:200]}%"
                try:
                    with self._lock:
                        if session:
                            rows2 = self._conn.execute(
                                "SELECT * FROM memories WHERE (summary LIKE ? OR content LIKE ?) AND (session_id IS NULL OR session_id = ?) ORDER BY score DESC LIMIT ?",
                                (like_q, like_q, session, limit),
                            ).fetchall()
                        else:
                            rows2 = self._conn.execute(
                                "SELECT * FROM memories WHERE summary LIKE ? OR content LIKE ? ORDER BY score DESC LIMIT ?",
                                (like_q, like_q, limit),
                            ).fetchall()
                    memories = [self._row_to_memory(r) for r in rows2]
                except sqlite3.OperationalError:
                    memories = []
                if not memories:
                    with self._lock:
                        if session:
                            rows3 = self._conn.execute(
                                "SELECT * FROM memories WHERE session_id IS NULL OR session_id = ? ORDER BY score DESC LIMIT ?",
                                (session, limit),
                            ).fetchall()
                        else:
                            rows3 = self._conn.execute(
                                "SELECT * FROM memories ORDER BY score DESC LIMIT ?", (limit,)
                            ).fetchall()
                    memories = [self._row_to_memory(r) for r in rows3]
            except Exception:
                with self._lock:
                    if session:
                        rows3 = self._conn.execute(
                            "SELECT * FROM memories WHERE session_id IS NULL OR session_id = ? ORDER BY score DESC LIMIT ?",
                            (session, limit),
                        ).fetchall()
                    else:
                        rows3 = self._conn.execute(
                            "SELECT * FROM memories ORDER BY score DESC LIMIT ?", (limit,)
                        ).fetchall()
                    memories = [self._row_to_memory(r) for r in rows3]
        elif not self.config.require_encryption:
            with self._lock:
                if session:
                    rows = self._conn.execute(
                        "SELECT * FROM memories WHERE session_id IS NULL OR session_id = ? ORDER BY score DESC LIMIT ?",
                        (session, limit),
                    ).fetchall()
                else:
                    rows = self._conn.execute(
                        "SELECT * FROM memories ORDER BY score DESC LIMIT ?", (limit,)
                    ).fetchall()
            memories = [self._row_to_memory(r) for r in rows]

        # bump access_count + last_accessed for recalled
        now = int(time.time())
        refreshed: list[Memory] = []
        with self._lock:
            for m in memories:
                new_score = composite_score(
                    m.importance,
                    m.access_count + 1,
                    now,
                    0.0,
                    w_imp=self.config.weight_importance,
                    w_freq=self.config.weight_frequency,
                    w_rec=self.config.weight_recency,
                    w_rew=self.config.weight_reward,
                    half_life_days=self.config.recency_half_life_days,
                    now=now,
                )
                self._conn.execute(
                    "UPDATE memories SET access_count=access_count+1, last_accessed=?, score=? WHERE id=?",
                    (now, new_score, m.id),
                )
            # refresh after bump
            for m in memories:
                row = self._conn.execute("SELECT * FROM memories WHERE id=?", (m.id,)).fetchone()
                if row:
                    refreshed.append(self._row_to_memory(row))
        memories = refreshed

        if session and stm:
            ids = [t.id for t in stm]
            if ids:
                qmarks = ",".join("?" for _ in ids)
                with self._lock:
                    tro = self._conn.execute(
                        f"SELECT * FROM tool_calls WHERE turn_id IN ({qmarks}) ORDER BY ts", ids
                    ).fetchall()
                tool_calls = [
                    ToolCall(
                        id=r["id"],
                        turn_id=r["turn_id"],
                        name=r["name"],
                        args=json.loads(r["args_json"]) if r["args_json"] else None,
                        result=json.loads(r["result_json"]) if r["result_json"] else None,
                        success=bool(r["success"]) if r["success"] is not None else None,
                    )
                    for r in tro
                ]
        return RecallResult(query=query, stm=stm, memories=memories, tool_calls=tool_calls)

    def feedback(self, memory_id: int, reward: float) -> Memory:
        with self._lock:
            row = self._conn.execute("SELECT * FROM memories WHERE id=?", (memory_id,)).fetchone()
            if not row:
                raise NotFoundError(f"memory {memory_id} not found")
        now = int(time.time())
        try:
            reward_f = float(reward)
        except Exception:
            raise ValidationError("reward must be numeric") from None
        if math.isnan(reward_f) or math.isinf(reward_f):
            raise ValidationError("reward must be finite")
        new_reward = max(0.0, min(1.0, reward_f))
        new_score = composite_score(
            row["importance"],
            row["access_count"],
            now,
            new_reward,
            w_imp=self.config.weight_importance,
            w_freq=self.config.weight_frequency,
            w_rec=self.config.weight_recency,
            w_rew=self.config.weight_reward,
            half_life_days=self.config.recency_half_life_days,
            now=now,
        )
        with self._lock:
            self._conn.execute(
                "UPDATE memories SET reward=?, score=?, last_accessed=? WHERE id=?",
                (new_reward, new_score, now, memory_id),
            )
            row2 = self._conn.execute("SELECT * FROM memories WHERE id=?", (memory_id,)).fetchone()
            assert row2 is not None
            return self._row_to_memory(row2)

    def prune(self, keep: int | None = None) -> int:
        """Delete lowest-scored memories beyond keep limit. Returns deleted count. Batches for sqlite MAX_VARIABLE_NUMBER."""
        cap = keep if keep is not None else self.config.max_memories
        if cap < 0:
            raise ValidationError("keep must be >=0")
        with self._lock:
            count = self._conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
            if count <= cap:
                return 0
            to_delete = count - cap
            rows = self._conn.execute(
                "SELECT id FROM memories ORDER BY score ASC LIMIT ?", (to_delete,)
            ).fetchall()
            ids = [r["id"] for r in rows]
            # batch to avoid sqlite "too many SQL variables" (default 999)
            batch_size = 900
            total = 0
            for i in range(0, len(ids), batch_size):
                chunk = ids[i : i + batch_size]
                qmarks = ",".join("?" for _ in chunk)
                self._conn.execute(f"DELETE FROM memories WHERE id IN ({qmarks})", chunk)
                total += len(chunk)
            return total

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "sessions": self._conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0],
                "turns": self._conn.execute("SELECT COUNT(*) FROM turns").fetchone()[0],
                "memories": self._conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0],
                "tool_calls": self._conn.execute("SELECT COUNT(*) FROM tool_calls").fetchone()[0],
            }

    # ---- 5 killer dev-exp extras ----

    def health_check(self) -> dict[str, object]:
        """Deep health: integrity, WAL, FTS, sizes + hardening. Zero-dependency."""
        with self._lock:
            integ = self._conn.execute("PRAGMA integrity_check").fetchone()[0]
            wal = self._conn.execute("PRAGMA journal_mode").fetchone()[0]
            page_cnt = self._conn.execute("PRAGMA page_count").fetchone()[0]
            page_sz = self._conn.execute("PRAGMA page_size").fetchone()[0]
            fts_ok = True
            try:
                self._conn.execute("SELECT * FROM memories_fts LIMIT 1")
            except sqlite3.OperationalError:
                fts_ok = False
            try:
                audit_count = int(
                    self._conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
                )
            except sqlite3.OperationalError:
                audit_count = 0
            try:
                acl_count = int(
                    self._conn.execute("SELECT COUNT(*) FROM session_acl").fetchone()[0]
                )
            except sqlite3.OperationalError:
                acl_count = 0
            db_size = page_cnt * page_sz if page_cnt and page_sz else 0
            wal_path = self.path + "-wal" if self.path != ":memory:" else ""
            wal_size = 0
            try:
                if wal_path and Path(wal_path).exists():
                    wal_size = Path(wal_path).stat().st_size
            except Exception:
                pass
            worm_ok: object = True
            perms = file_perms_ok(self.path)
        # verify outside inner lock (RLock-safe anyway, but cheaper)
        if self.config.worm_enabled:
            try:
                v = self.verify_chain()
                worm_ok = v.get("ok", False)
            except Exception:
                worm_ok = False
        with self._lock:
            return {
                "integrity": integ,
                "integrity_ok": integ == "ok",
                "journal_mode": wal,
                "db_size_bytes": db_size,
                "wal_size_bytes": wal_size,
                "fts_ok": fts_ok,
                "stats": self.stats(),
                "worm_enabled": self.config.worm_enabled,
                "worm_ok": worm_ok,
                "audit_count": audit_count,
                "redact_pii": self.config.redact_pii,
                "encryption": self.config.require_encryption,
                "acl": self.config.require_acl,
                "acl_count": acl_count,
                "perms_ok": perms,
            }

    def vacuum(self) -> None:
        """Reclaim space + optimize FTS. Safe to call hot."""
        with self._lock:
            try:
                self._conn.execute("VACUUM")
            except sqlite3.OperationalError:
                pass
            try:
                self._conn.execute("INSERT INTO memories_fts(memories_fts) VALUES('optimize')")
            except sqlite3.OperationalError:
                pass

    def backup(self, dest: str | Path) -> None:
        """Online backup via sqlite3 backup API (hot, not blocking)."""
        dest = str(dest)
        with self._lock:
            dst = sqlite3.connect(dest)
            try:
                self._conn.backup(dst)
            finally:
                dst.close()
        harden_file(dest)

    def export_json(self, dest: str | Path) -> dict[str, int]:
        """Dump to JSON file. Returns counts. Inspector-friendly."""
        dest = Path(dest)
        data: dict[str, list[dict[str, object]]] = {
            "sessions": [],
            "turns": [],
            "memories": [],
            "tool_calls": [],
        }
        with self._lock:
            for row in self._conn.execute("SELECT * FROM sessions").fetchall():
                data["sessions"].append(dict(row))
            for row in self._conn.execute("SELECT * FROM turns").fetchall():
                d = dict(row)
                try:
                    d["content"] = self._dec(str(d.get("content", "")))
                except Exception:
                    pass
                data["turns"].append(d)
            for row in self._conn.execute("SELECT * FROM memories").fetchall():
                d = dict(row)
                try:
                    d["content"] = self._dec(str(d.get("content", "")))
                    d["summary"] = self._dec(str(d.get("summary", "")))
                except Exception:
                    pass
                data["memories"].append(d)
            for row in self._conn.execute("SELECT * FROM tool_calls").fetchall():
                data["tool_calls"].append(dict(row))
        # json can't handle bytes for embedding, base64? skip
        for m in data["memories"]:
            if m.get("embedding") is not None:
                m["embedding"] = None
        dest.write_text(json.dumps(data, indent=2))
        return {k: len(v) for k, v in data.items()}

    def import_json(self, src: str | Path) -> dict[str, int]:
        """Restore from export_json. Idempotent for sessions, append for others."""
        src_p = Path(src)
        data = json.loads(src_p.read_text())
        counts = {"sessions": 0, "turns": 0, "memories": 0, "tool_calls": 0}
        with self._lock:
            for s in data.get("sessions", []):
                try:
                    self._conn.execute(
                        "INSERT OR IGNORE INTO sessions(id, meta_json, created_at) VALUES (?,?,?)",
                        (s["id"], s.get("meta_json"), s["created_at"]),
                    )
                    counts["sessions"] += 1
                except Exception:
                    pass
            for t in data.get("turns", []):
                try:
                    self._conn.execute(
                        "INSERT INTO turns(id, session_id, role, content, tokens, ts) VALUES (?,?,?,?,?,?)",
                        (t["id"], t["session_id"], t["role"], t["content"], t["tokens"], t["ts"]),
                    )
                    counts["turns"] += 1
                except Exception:
                    pass
            for m in data.get("memories", []):
                try:
                    self._conn.execute(
                        "INSERT INTO memories(id, kind, session_id, content, summary, importance, access_count, reward, score, created_at, last_accessed) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            m["id"],
                            m["kind"],
                            m.get("session_id"),
                            m["content"],
                            m["summary"],
                            m["importance"],
                            m["access_count"],
                            m["reward"],
                            m["score"],
                            m["created_at"],
                            m["last_accessed"],
                        ),
                    )
                    counts["memories"] += 1
                except Exception:
                    pass
            for tc in data.get("tool_calls", []):
                try:
                    self._conn.execute(
                        "INSERT INTO tool_calls(id, turn_id, name, args_json, result_json, success, ts) VALUES (?,?,?,?,?,?,?)",
                        (
                            tc["id"],
                            tc["turn_id"],
                            tc["name"],
                            tc.get("args_json"),
                            tc.get("result_json"),
                            tc.get("success"),
                            tc["ts"],
                        ),
                    )
                    counts["tool_calls"] += 1
                except Exception:
                    pass
        return counts

    def chat(
        self,
        session: str,
        user_msg: str,
        llm_fn: Any,
        system: str = "",
        limit: int = 5,
        actor: str | None = None,
    ) -> dict[str, Any]:
        """Fully-auto plug-and-use: recall -> LLM -> store -> extract. No remember() needed."""
        from memolite.auto import auto_chat

        return auto_chat(self, session, user_msg, llm_fn, system, limit, actor)

    def explain_recall(
        self, query: str, session: str | None = None, limit: int = 5
    ) -> dict[str, object]:
        """Debug helper: shows FTS vs LIKE path, scores, timings."""
        t0 = time.time()
        res = self.recall(query, session=session, limit=limit)
        dt = (time.time() - t0) * 1000
        return {
            "query": query,
            "session": session,
            "took_ms": round(dt, 2),
            "returned": len(res.memories),
            "memories": [
                {"id": m.id, "kind": m.kind, "score": round(m.score, 3), "summary": m.summary[:80]}
                for m in res.memories
            ],
            "stm_count": len(res.stm),
            "prompt_chars": len(res.prompt),
        }

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.commit()
                self._conn.close()
            except Exception:
                pass

    def __enter__(self) -> MemoryStore:
        return self

    def __exit__(self, *a: Any) -> None:
        self.close()

    # internal
    def _row_to_memory(self, r: sqlite3.Row) -> Memory:
        try:
            content = self._dec(r["content"])
        except Exception:
            content = "[DECRYPT_FAILED]"
        try:
            summary = self._dec(r["summary"])
        except Exception:
            summary = "[DECRYPT_FAILED]"
        return Memory(
            id=r["id"],
            kind=r["kind"],
            session_id=r["session_id"],
            content=content,
            summary=summary,
            importance=float(r["importance"]),
            access_count=int(r["access_count"]),
            score=float(r["score"]),
            created_at=int(r["created_at"]),
            last_accessed=int(r["last_accessed"]),
        )

    def verify_chain(self, session_id: str | None = None) -> dict[str, object]:
        """Verify WORM hash-chain. Returns {ok, count, bad_id}."""
        with self._lock:
            if session_id:
                rows = self._conn.execute(
                    "SELECT a.id, a.session_id, a.prev_hash, a.hash, a.ts,"
                    " t.role, t.content FROM audit_log a"
                    " JOIN turns t ON t.id=a.turn_id"
                    " WHERE a.session_id=? ORDER BY a.id",
                    (session_id,),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT a.id, a.session_id, a.prev_hash, a.hash, a.ts,"
                    " t.role, t.content FROM audit_log a"
                    " JOIN turns t ON t.id=a.turn_id ORDER BY a.id"
                ).fetchall()
            rows = list(rows)
        prev = "GENESIS"
        count = 0
        for r in rows:
            if str(r["prev_hash"]) != prev:
                return {"ok": False, "count": count, "bad_id": r["id"]}
            try:
                plain = self._dec(str(r["content"]))
            except Exception:
                return {"ok": False, "count": count, "bad_id": r["id"]}
            exp = chain_hash(prev, str(r["session_id"]), str(r["role"]), plain, int(r["ts"]))
            if exp != str(r["hash"]):
                return {"ok": False, "count": count, "bad_id": r["id"]}
            prev = str(r["hash"])
            count += 1
        return {"ok": True, "count": count, "bad_id": None}
