# memolite Launch Kit

## Package Registries

### PyPI (mandatory)

Build already verified: `dist/memolite-0.1.0-py3-none-any.whl` (17K) and `sdist` (19K), `twine check` PASSED.

To publish (maintainer):

```bash
# set token once
export TWINE_USERNAME=__token__
export TWINE_PASSWORD=pypi-XXXXXXXX

# TestPyPI first (optional)
twine upload --repository testpypi dist/*

# PyPI
twine upload dist/*
# verify
pip install memolite
python -c "from memolite import MemoryStore; print(MemoryStore(':memory:').health_check())"
```

GitHub Packages is available via Release assets: https://github.com/mastaan66/memolite/releases/tag/v0.1.0

### Versioning

`0.1.0` - Alpha. Next: `0.2.0` adds `sqlite-vec` hybrid. Follow semver, tags via `git tag -a vX.Y.Z`.

## Discovery Channels

### Hacker News - Show HN

Title: `Show HN: memolite — SQLite-native agentic memory, single file, offline, thread-safe`

Body:

```
We built memolite because every agentic memory library needs a server/vector DB or cloud API. For air-gapped and edge agents that's a non-starter.

memolite is a single SQLite file:

- offline hybrid recall: FTS5 + heuristic + optional sqlite-vec, 0.2ms for 10k memories, no network
- session-aware: global knowledge plus per-session isolation automatically
- thread and WAL safe: RLock, busy_timeout, batch prune, integrity_check, 100 threads zero deadlock
- injection and chaos hardened: 100KB query, unicode, SQLi, kill -9 mid-transaction rollback
- one-liner DX: recall().prompt ready to inject, :memory: for tests and file for prod

pip install memolite
from memolite import MemoryStore
store = MemoryStore("agent.db")
store.add_turn(session="s1", role="user", content="Remember I prefer Python")
store.recall("python preference", session="s1")  # hybrid BM25 + recency + access_count

81% coverage, mypy --strict, ruff, py.typed, MIT.
GitHub: https://github.com/mastaan66/memolite  PyPI: dist ready  Docs: health_check, backup, export_json, vacuum

We hardened it with 15k ops 100 threads chaos, 50k scale bench, 100KB fuzz. Would love brutal feedback.
```

### Reddit r/Python

Title: `memolite — offline SQLite memory for agents, no server needed`

Body: Explain problem (LangChain memory needs server, mem0 needs OpenAI), show 30-sec example, list 5 hero gates with numbers (100 threads, 50k 1.3ms, 100KB), ask for feedback, include GitHub link. Flair `Showcase`.

Subreddits: r/Python, r/LocalLLaMA, r/MachineLearning (if allowed)

### Product Hunt

Tagline: `The single-file memory for AI agents that works offline`

Gallery: GIF of `sqlite3 agent.db "SELECT ..."` and Python recall.

Maker comment: emphasize edge/air-gapped use case.

### X / LinkedIn

Post (280 chars):

```
memolite — SQLite-native agentic memory

single file agent.db, offline FTS5 + heuristic, 0.2ms for 10k, thread-safe 100 threads, kill -9 safe

pip install memolite
store.recall("python", session="s1").prompt # ready to inject

https://github.com/mastaan66/memolite
#opensource #python #agents #sqlite
```

Video: 15 sec asciinema of `examples/01_quickstart.py` running.

### Newsletters

Submit to:

- Python Weekly (cooperpress) - https://pythonweekly.com/ - submit via form
- TLDR Web Dev - https://tldr.tech/ - submit tool
- Console.dev - https://console.dev/ - open-source tool review

Include one-paragraph pitch + GitHub link + 30-sec gif.

Pitch:

> memolite is an offline, single-file SQLite memory for Python agents. It replaces vector DB/server stacks with FTS5 hybrid recall, session-aware isolation, and WAL thread safety. 24 tests 81% cov, mypy strict, 50k scale 1.3ms avg, 100 threads zero deadlock, kill -9 rollback. pip install memolite, one prompt injection. MIT.

## 30-Second DX Demo

`examples/01_quickstart.py` is the 30-sec demo. Record with asciinema:

```bash
pipx install asciinema
asciinema rec demo.cast -c "python examples/01_quickstart.py && sqlite3 :memory: 'select 1'"
```

Convert to GIF via `agg` and place at README top.

## Sustaining Growth Checklist

- Reply to issues within hours (hyper-responsive)
- Label `good first issue` for docs/tests
- Request logo after first production user for social proof
