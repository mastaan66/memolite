"""Sync MemoryStore - core of memolite."""

from __future__ import annotations

import json
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

    def add_turn(self, session: str, role: str, content: str, tokens: int | None = None) -> Turn:
        if not session or not session.strip() or not role or content is None:
            raise ValidationError("session/role/content required")
        if role not in {"user", "assistant", "system", "tool"}:
            raise ValidationError(f"invalid role {role}")
        self.create_session(session)
        now = int(time.time())
        toks = tokens if tokens is not None else max(0, len(content) // 4)
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO turns(session_id, role, content, tokens, ts) VALUES (?,?,?,?,?)",
                (session, role, content, toks, now),
            )
            turn_id = cur.lastrowid or 0
        turn = Turn(id=turn_id, session_id=session, role=role, content=content, tokens=toks, ts=now)
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
    ) -> Memory:
        if not content or not content.strip():
            raise ValidationError("content empty")
        if kind not in {"semantic", "procedural", "episodic"}:
            raise ValidationError(f"invalid kind {kind}")
        # clamp importance/reward
        try:
            importance_f = float(importance)
        except Exception:
            raise ValidationError("importance must be numeric") from None
        try:
            reward_f = float(reward)
        except Exception:
            raise ValidationError("reward must be numeric") from None
        # ensure session exists if provided (FK)
        if session_id:
            self.create_session(session_id)
        now = int(time.time())
        summ = summary or content[:200]
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
                (kind, session_id, content, summ, importance_f, 0, reward_f, sc, now, now),
            )
            mid = cur.lastrowid or 0
            row = self._conn.execute("SELECT * FROM memories WHERE id=?", (mid,)).fetchone()
            assert row is not None
            return self._row_to_memory(row)

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
        texts = [r["content"] for r in rows][::-1]
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
        return created

    def recall(
        self, query: str, session: str | None = None, limit: int = 5, stm_limit: int | None = None
    ) -> RecallResult:
        if limit <= 0:
            raise ValidationError("limit must be >0")
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
                    content=r["content"],
                    tokens=r["tokens"],
                    ts=r["ts"],
                )
                for r in rows[::-1]
            ]
        memories: list[Memory] = []
        tool_calls: list[ToolCall] = []

        if query and query.strip():
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
                memories = [m for _, m in scored[:limit]]
                # if session filter gave 0 but global fallback should try
                if not memories and session:
                    raise sqlite3.OperationalError("no fts hits for session filter")
            except sqlite3.OperationalError:
                like_q = f"%{query.strip()}%"
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
        else:
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
        """Delete lowest-scored memories beyond keep limit. Returns deleted count."""
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
            if ids:
                qmarks = ",".join("?" for _ in ids)
                self._conn.execute(f"DELETE FROM memories WHERE id IN ({qmarks})", ids)
            return len(ids)

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "sessions": self._conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0],
                "turns": self._conn.execute("SELECT COUNT(*) FROM turns").fetchone()[0],
                "memories": self._conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0],
                "tool_calls": self._conn.execute("SELECT COUNT(*) FROM tool_calls").fetchone()[0],
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
        return Memory(
            id=r["id"],
            kind=r["kind"],
            session_id=r["session_id"],
            content=r["content"],
            summary=r["summary"],
            importance=float(r["importance"]),
            access_count=int(r["access_count"]),
            score=float(r["score"]),
            created_at=int(r["created_at"]),
            last_accessed=int(r["last_accessed"]),
        )
