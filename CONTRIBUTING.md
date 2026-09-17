# Contributing

## Setup
```bash
pip install -e ".[dev]"
pre-commit install
pytest -q
```

## Workflow
1. Fork + branch `feat/<name>`
2. `ruff check --fix . && ruff format . && mypy src/memolite`
3. `pytest --cov=memolite`
4. Commit with conventional commits `feat:`, `fix:`, `docs:`
5. PR - CI must pass (ruff, mypy --strict, pytest, coverage >80%)

## Design rules
- Core stays stdlib only. Optional deps under `project.optional-dependencies`.
- All public APIs typed, slots dataclasses, no `Any` leaks.
- SQL via `?` placeholders only - no string interpolation.
- File is single source of SQL truth: `schema.py`.
