"""Sync MemoryStore - core of memolite."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from memolite.config import Config
from memolite.consolidator import heuristic_consolidate
from memolite.exceptions import NotFoundError, ValidationError
from memolite.models import Memory, RecallResult, Session, ToolCall, Turn
from memolite.schema import SCHEMA_SQL
from memolite.scoring import composite_score, recency_factor


class MemoryStore:
    """SQLite-backed agentic memory. Thread-safe via busy_timeout + WAL."""

    def __init__(self, path: str | Path, config: Config | None = None) -> None:
        self.path = str(path)
        self.config = config or Config()
        self._conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(f"PRAGMA busy_timeout={self.config.busy_timeout_ms}")
        if self.config.wal_mode:
            self._conn.execute("PRAGMA journal_mode=WAL")
        if self.config.foreign_keys:
            self._conn.execute("PRAGMA foreign_keys=ON")
        for k, v in self.config.extra_pragmas.items():
            self._conn.execute(f"PRAGMA {k}={v}")
        self._conn.executescript(SCHEMA_SQL)
        # ensure stm budget quick
        self._turn_counter: dict[str, int] = {}

    # ---- sessions / turns ----

    def create_session(self, session_id: str, meta: dict[str, object] | None = None) -> Session:
        if not session_id:
            raise ValidationError("session_id required")
        now = int(time.time())
        try:
            self._conn.execute(
                "INSERT INTO sessions(id, meta_json, created_at) VALUES (?,?,?)",
                (session_id, json.dumps(meta) if meta else None, now),
            )
        except sqlite3.IntegrityError:
            pass  # idempotent
        return Session(id=session_id, meta=meta, created_at=now)

    def add_turn(self, session: str, role: str, content: str, tokens: int | None = None) -> Turn:
        if not session or not role or content is None:
            raise ValidationError("session/role/content required")
        if role not in {"user", "assistant", "system", "tool"}:
            raise ValidationError(f"invalid role {role}")
        self.create_session(session)
        now = int(time.time())
        toks = tokens if tokens is not None else len(content) // 4
        cur = self._conn.execute(
            "INSERT INTO turns(session_id, role, content, tokens, ts) VALUES (?,?,?,?,?)",
            (session, role, content, toks, now),
        )
        turn = Turn(
            id=cur.lastrowid or 0,
            session_id=session,
            role=role,
            content=content,
            tokens=toks,
            ts=now,
        )
        # also store episodic mirror for recall fusion (lightweight)
        # auto-consolidate
        cnt = self._turn_counter.get(session, 0) + 1
        self._turn_counter[session] = cnt
        if self.config.auto_consolidate_every and cnt % self.config.auto_consolidate_every == 0:
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
        if not name:
            raise ValidationError("tool name required")
        # verify turn exists
        row = self._conn.execute("SELECT id FROM turns WHERE id=?", (turn_id,)).fetchone()
        if not row:
            raise NotFoundError(f"turn {turn_id} not found")
        now = int(time.time())
        cur = self._conn.execute(
            "INSERT INTO tool_calls(turn_id, name, args_json, result_json, success, ts) VALUES (?,?,?,?,?,?)",
            (
                turn_id,
                name,
                json.dumps(args) if args is not None else None,
                json.dumps(result) if result is not None else None,
                1 if success else 0 if success is False else None,
                now,
            ),
        )
        # procedural memory on success
        if success:
            self.remember(
                f"Tool {name} succeeded for {json.dumps(args)[:120]}",
                kind="procedural",
                importance=0.6,
            )
        return ToolCall(
            id=cur.lastrowid or 0,
            turn_id=turn_id,
            name=name,
            args=args,
            result=result,
            success=success,
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
        now = int(time.time())
        summ = summary or content[:200]
        sc = composite_score(
            importance,
            0,
            now,
            reward,
            w_imp=self.config.weight_importance,
            w_freq=self.config.weight_frequency,
            w_rec=self.config.weight_recency,
            w_rew=self.config.weight_reward,
            half_life_days=self.config.recency_half_life_days,
            now=now,
        )
        cur = self._conn.execute(
            """INSERT INTO memories(kind, session_id, content, summary, importance, access_count, reward, score, created_at, last_accessed)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (kind, session_id, content, summ, importance, 0, reward, sc, now, now),
        )
        mid = cur.lastrowid or 0
        row = self._conn.execute("SELECT * FROM memories WHERE id=?", (mid,)).fetchone()
        assert row is not None
        return self._row_to_memory(row)

    def consolidate(self, session: str) -> list[Memory]:
        """Distill recent turns into semantic memories. Returns new memories."""
        rows = self._conn.execute(
            "SELECT content FROM turns WHERE session_id=? ORDER BY ts DESC LIMIT ?",
            (session, self.config.auto_consolidate_every * 2),
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
            if not content:
                continue
            summary_val = c.get("summary")
            summary = str(summary_val) if isinstance(summary_val, str) else None
            kind_val = c.get("kind", "semantic")
            kind = str(kind_val) if isinstance(kind_val, str) else "semantic"
            imp_val = c.get("importance", 0.5)
            try:
                imp = float(imp_val)  # type: ignore[arg-type]
            except Exception:
                imp = 0.5
            # dedup: skip if near-duplicate exists
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
        # 1. STM
        stm: list[Turn] = []
        if session:
            rows = self._conn.execute(
                "SELECT * FROM turns WHERE session_id=? ORDER BY ts DESC LIMIT ?", (session, stm_n)
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
        # 2. memories via FTS5 + score fusion
        memories: list[Memory] = []
        tool_calls: list[ToolCall] = []
        if query and query.strip():
            # try FTS, fallback to score sort
            try:
                # escape FTS query
                q = query.replace('"', '""')
                # BM25 via rank, join with score
                fts_rows = self._conn.execute(
                    """
                    SELECT m.*, rank FROM memories m
                    JOIN memories_fts f ON m.id = f.rowid
                    WHERE memories_fts MATCH ?
                    ORDER BY rank LIMIT ?
                    """,
                    (f'"{q}"' if " " not in q else q, limit * 3),
                ).fetchall()
                # if no FTS hits, fallback to like
                if not fts_rows:
                    raise sqlite3.OperationalError("no fts hits")
                # re-rank by composite of bm25 rank + our score + recency
                scored = []
                for r in fts_rows:
                    mem = self._row_to_memory(r)
                    # boost by recency
                    rec = recency_factor(mem.last_accessed, self.config.recency_half_life_days)
                    fused = mem.score * 0.7 + rec * 0.3 - (r["rank"] * 0.05)
                    scored.append((fused, mem))
                scored.sort(key=lambda x: x[0], reverse=True)
                memories = [m for _, m in scored[:limit]]
            except Exception:
                # fallback: score-ordered LIKE
                like_q = f"%{query.strip()}%"
                rows2 = self._conn.execute(
                    "SELECT * FROM memories WHERE summary LIKE ? OR content LIKE ? ORDER BY score DESC LIMIT ?",
                    (like_q, like_q, limit),
                ).fetchall()
                memories = [self._row_to_memory(r) for r in rows2]
                if not memories:
                    # final fallback: top scored
                    rows3 = self._conn.execute(
                        "SELECT * FROM memories ORDER BY score DESC LIMIT ?", (limit,)
                    ).fetchall()
                    memories = [self._row_to_memory(r) for r in rows3]
        else:
            rows = self._conn.execute(
                "SELECT * FROM memories ORDER BY score DESC LIMIT ?", (limit,)
            ).fetchall()
            memories = [self._row_to_memory(r) for r in rows]

        # bump access_count + last_accessed for recalled
        now = int(time.time())
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
            # also update in-memory object for returned result
            # (mutate via new instance)
        # refresh memories with bumped counts for caller
        refreshed: list[Memory] = []
        for m in memories:
            row = self._conn.execute("SELECT * FROM memories WHERE id=?", (m.id,)).fetchone()
            if row:
                refreshed.append(self._row_to_memory(row))
        memories = refreshed

        if session and stm:
            # collect tool calls for stm turns
            ids = [t.id for t in stm]
            if ids:
                qmarks = ",".join("?" for _ in ids)
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
        row = self._conn.execute("SELECT * FROM memories WHERE id=?", (memory_id,)).fetchone()
        if not row:
            raise NotFoundError(f"memory {memory_id} not found")
        now = int(time.time())
        new_reward = max(0.0, min(1.0, reward))
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
        return {
            "sessions": self._conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0],
            "turns": self._conn.execute("SELECT COUNT(*) FROM turns").fetchone()[0],
            "memories": self._conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0],
            "tool_calls": self._conn.execute("SELECT COUNT(*) FROM tool_calls").fetchone()[0],
        }

    def close(self) -> None:
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
