"""SQLite schema."""

SCHEMA_SQL = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS sessions(
  id TEXT PRIMARY KEY,
  meta_json TEXT,
  created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS turns(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  tokens INTEGER NOT NULL DEFAULT 0,
  ts INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_turns_session_ts ON turns(session_id, ts);
CREATE INDEX IF NOT EXISTS idx_turns_ts ON turns(ts);

CREATE TABLE IF NOT EXISTS tool_calls(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  turn_id INTEGER NOT NULL REFERENCES turns(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  args_json TEXT,
  result_json TEXT,
  success INTEGER,
  ts INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tool_turn ON tool_calls(turn_id);

CREATE TABLE IF NOT EXISTS memories(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL CHECK(kind IN ('semantic','procedural','episodic')),
  session_id TEXT REFERENCES sessions(id) ON DELETE SET NULL,
  content TEXT NOT NULL,
  summary TEXT NOT NULL,
  importance REAL NOT NULL DEFAULT 0.5,
  access_count INTEGER NOT NULL DEFAULT 0,
  reward REAL NOT NULL DEFAULT 0.0,
  score REAL NOT NULL DEFAULT 0.0,
  embedding BLOB,
  need_embed INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL,
  last_accessed INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mem_score ON memories(score DESC);
CREATE INDEX IF NOT EXISTS idx_mem_kind ON memories(kind);
CREATE INDEX IF NOT EXISTS idx_mem_session ON memories(session_id);

-- FTS5 for hybrid search - content + summary
CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
  summary, content,
  content='memories',
  content_rowid='id',
  tokenize='porter unicode61'
);

-- triggers to keep FTS in sync
CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
  INSERT INTO memories_fts(rowid, summary, content) VALUES (new.id, new.summary, new.content);
END;
CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
  INSERT INTO memories_fts(memories_fts, rowid, summary, content) VALUES('delete', old.id, old.summary, old.content);
END;
CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
  INSERT INTO memories_fts(memories_fts, rowid, summary, content) VALUES('delete', old.id, old.summary, old.content);
  INSERT INTO memories_fts(rowid, summary, content) VALUES (new.id, new.summary, new.content);
END;
"""
