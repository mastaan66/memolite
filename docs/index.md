# memolite documentation

Professional, offline-first agentic memory on SQLite.

## Standards

- Python 3.10+ | Typed (PEP 561) | `py.typed` included
- Lint: `ruff` | Type: `mypy --strict` | Test: `pytest --cov` (>80 percent)
- Packaging: PEP 517 (`hatchling`), `src` layout, `MIT`
- Security: parameterized SQL, PRAGMA allowlist, JSON validation

## Layout

- `src/memolite/store.py` - core `MemoryStore`
- `src/memolite/config.py` - `Config` (WAL, scoring weights, pluggable hooks)
- `src/memolite/schema.py` - single source of SQL truth
- `src/memolite/scoring.py` - recency and frequency scoring
- `src/memolite/consolidator.py` - heuristic consolidator (offline)

## Integrity

Run `store.health_check()` to verify `PRAGMA integrity_check`, journal mode, FTS status, and sizes.

```
health = store.health_check()
# {'integrity_ok': True, 'fts_ok': True, 'db_size_bytes': ..., 'stats': {...}}
```
