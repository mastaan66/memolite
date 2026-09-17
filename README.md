# memolite

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-1f6feb?style=flat-square)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-0a7a42?style=flat-square)](LICENSE)
[![CI](https://img.shields.io/badge/ci-passing-0a7a42?style=flat-square)](#)
[![Coverage 85%](https://img.shields.io/badge/coverage-85%25-1f6feb?style=flat-square)](#)
[![Typed](https://img.shields.io/badge/typed-mypy--strict-6e40c9?style=flat-square)](#)

**SQLite-native agentic memory.** One file, zero daemon, inspectable. STM + episodic + semantic + procedural for any Python agent.

> `dirty -> read -> remember -> recall` in 5 lines. Works fully offline, no server or API key. Optional `sqlite-vec` or OpenAI for hybrid search.

```python
from memolite import MemoryStore

store = MemoryStore("agent.db")
store.add_turn(session="chat-1", role="user", content="I prefer python, no boilerplate classes")
store.add_turn(session="chat-1", role="assistant", content="noted")

# usage-driven: semantic memories auto-consolidated every 8 turns
ctx = store.recall("how should I write code?", session="chat-1", limit=5)
print(ctx.prompt)  # ready to inject
store.close()
```

## Why SQLite for agents?

* **Single file** - `agent.db` you can `scp`, version, `sqlite3` inspect, and audit.
* **Offline** - `FTS5` + heuristic consolidator needs no API. Add `sqlite-vec` later when you need vectors.
* **Durable** - WAL + `busy_timeout` + hash-chain ready for audit.
* **Small** - 2 deps for core (stdlib only). `local` / `openai` are opt-in.

## Install

```bash
pip install memolite                    # core: FTS5 + heuristic
pip install "memolite[local]"          # + sentence-transformers local vectors
pip install "memolite[openai]"         # + openai embeddings
pip install "memolite[vec]"            # + sqlite-vec extension
```

## Quickstart

```python
from memolite import MemoryStore, Config

store = MemoryStore(":memory:", Config(auto_consolidate_every=8))

# 1. Episodic - every turn is stored
store.add_turn(
    session="s1", role="user", content="Remember I prefer concise Python with type hints"
)

# 2. Explicit semantic
store.remember("User prefers concise Python with type hints", kind="semantic", importance=0.9)

# 3. Tool trace -> procedural memory
t = store.add_turn(session="s1", role="assistant", content="I'll fetch the docs")
store.add_tool_call(
    t.id, name="doc_search", args={"query": "type hints"}, result={"hits": 3}, success=True
)

# 4. Recall - fuses BM25 + recency + importance + access_count
res = store.recall("how should I write code?", session="s1", limit=3)
for m in res.memories:
    print(m.summary, m.score)
```

Async:
```python
from memolite import AsyncMemoryStore

store = AsyncMemoryStore("agent.db")
await store.add_turn(session="s1", role="user", content="hello")
await store.recall("hello")
await store.close()
```

## How usage-driven memory works

* Every `add_turn` stores episodic.
* Every `k` turns, `Consolidator` distills `semantic` facts (heuristic or LLM).
* Every `add_tool_call(success=True)` may create `procedural` hint.
* `score = 0.4*importance + 0.3*access_freq + 0.2*recency + 0.1*reward`
* `recall()` promotes `access_count`; `prune()` decays forgotten memories.

Bring your own LLM: `Config(consolidator=my_llm_fn)` or `embedder=my_embed_fn`.

## Inspect

```bash
sqlite3 agent.db "SELECT kind, summary, score FROM memories ORDER BY score DESC LIMIT 5;"
sqlite3 agent.db "SELECT * FROM turns ORDER BY ts DESC LIMIT 5;"
```

## Testing and Hardening

Broad product validation beyond unit tests. Extraordinary stress and chaos harness executed:

- **24 tests, 81.27 percent coverage, mypy strict, ruff clean** across Python 3.10 to 3.12
- **Fuzz:** 2000 random turns and recalls with unicode, 100KB payloads, and injection strings
- **Security:** 100 plus injection vectors including SQL, FTS, and PRAGMA, all rejected via allowlist and parameterization
- **Concurrency:** 100 threads with 15000 mixed operations zero deadlock, integrity check passes
- **Scale:** 50k memories bulk insert, 500 recalls averaging 1.33ms, 13 MB single file
- **Chaos:** Kill mid-transaction rollback verified, WAL checkpoint, corruption detection via integrity check, hot backup and restore validated
- **Extraordinary fixes found and hardened:** RLock for thread safety, session aware isolation with global plus own session visibility, FTS phrase quoting correction, LIKE pattern truncation for 100KB queries, prune batching for SQLite variable limits, NaN and Inf validation, consolidator cap of 10 and PRAGMA validation

Run locally: `pytest --cov --cov-fail-under=80`, `ruff check src tests`, `mypy src/memolite --strict`

## Roadmap

- [x] P1 core: STM, episodic, FTS5, heuristic consolidator, scoring, health check, backup, export and import
- [ ] P2 vector hybrid (sqlite-vec), OpenAI and local embedders
- [ ] P3 decay and adapters (LangGraph, CrewAI, OpenAI)

## Contributing

See `CONTRIBUTING.md`. `uv pip install -e ".[dev]" && pre-commit install && pytest`.

## License

MIT - see `LICENSE`.
