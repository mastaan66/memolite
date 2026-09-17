# memolite

**SQLite-native agentic memory.** One file, zero daemon, inspectable. STM + episodic + semantic + procedural for any Python agent.

> `dirty -> read -> remember -> recall` in 5 lines. Works fully offline (Maya OS / air-gapped friendly). Optional `sqlite-vec` / OpenAI for hybrid search.

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

* **Single file** - `agent.db` you can `scp`, version, `sqlite3` inspect. DGQA-friendly.
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
store.add_turn(session="s1", role="user", content="Remember I work on SHUCHI kiosk")

# 2. Explicit semantic
store.remember("SHUCHI = USB sanitiser kiosk for Maya OS", kind="semantic", importance=0.9)

# 3. Tool trace -> procedural memory
t = store.add_turn(session="s1", role="assistant", content="I'll scan the USB")
store.add_tool_call(t.id, name="clamav_scan", args={"path": "/mnt/usb"}, result={"infected": False}, success=True)

# 4. Recall - fuses BM25 + recency + importance + access_count
res = store.recall("what project am I on?", session="s1", limit=3)
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

## Roadmap

- [x] P1 core: STM, episodic, FTS5, heuristic consolidator, scoring
- [ ] P2 vector hybrid (sqlite-vec), OpenAI/local embedders
- [ ] P3 decay + adapters (LangGraph, CrewAI, OpenAI)

## Contributing

See `CONTRIBUTING.md`. `uv pip install -e ".[dev]" && pre-commit install && pytest`.

## License

MIT - see `LICENSE`.
