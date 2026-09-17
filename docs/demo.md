# 30-Second Demo

```bash
pip install memolite
```

```python
from memolite import MemoryStore

store = MemoryStore("agent.db")
store.add_turn(session="s1", role="user", content="Remember I prefer Python, no classes")
store.add_turn(session="s1", role="user", content="SHUCHI is a Maya OS kiosk")

# hybrid recall: FTS5 + recency + frequency
result = store.recall("python preference", session="s1", limit=3)
print(result.prompt)  # copy-paste into LLM
# # Long-term memories
# - [semantic:1 score=0.71] Remember I prefer Python, no classes

print(store.health_check())
# {'integrity_ok': True, 'fts_ok': True, 'db_size_bytes': 69632, ...}
```

Inspect:

```bash
sqlite3 agent.db "SELECT kind, summary, score FROM memories ORDER BY score DESC LIMIT 5;"
```

Time to first recall: under 30 seconds, no server, no API key.
