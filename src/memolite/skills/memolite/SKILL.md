---
name: memolite
description: Plug and play SQLite memory for any LLM, CLI, or agent. Use whenever the user wants persistent memory, recall, or cross-session context for Claude, ChatGPT, DeepSeek, Cursor, OpenCode, or any OpenAI-compatible model. Triggers on remember, recall, memory, session, or when an agent needs durable context without a server.
---

# memolite — single file memory as a skill

Add persistent memory to any LLM provider or coding CLI in one command. No server, no API key, one `agent.db` file works everywhere.

## When to use

Use this skill when the user says `remember`, `recall`, `memory`, `session`, `context`, or asks for durable memory for an agent. Also use when building any agent that needs STM plus semantic recall across sessions. Prefer this over vector DB setup for offline, edge, or single file use.

## Install as a skill — one line

```bash
pip install memolite
memolite skill install --all        # opencode + claude + cursor + windsurf
# or targeted
memolite skill install --target opencode
memolite skill install --target claude
```

This copies the skill to the correct location for each CLI. Verify:

```bash
memolite skill status
memolite health --db agent.db
```

Alternative without CLI:

```bash
# opencode
cp -r skills/memolite ~/.config/opencode/skills/
# claude code
cp -r skills/memolite ~/.claude/skills/
# cursor
cp -r skills/memolite ~/.cursor/skills/
```

## How to use — same store, every provider

The store is the contract. One file, every adapter reads the same SQLite.

### 1. Any LLM via prompt injection — no tools needed

Works with local models, DeepSeek, or any chat API.

```python
from memolite import MemoryStore
from memolite import plug

store = MemoryStore("agent.db")
store.add_turn(session="s1", role="user", content="I prefer concise Python")

adapter = plug(store, llm="generic")
prompt = adapter.inject("how should I write code?", session_id="s1")
# send prompt to any LLM
```

### 2. ChatGPT, OpenAI, DeepSeek — tool calling

DeepSeek is OpenAI compatible.

```python
from memolite import MemoryStore
from memolite.adapters.openai import OpenAIAdapter

store = MemoryStore("agent.db")
adapter = OpenAIAdapter(store)

response = client.chat.completions.create(
    model="gpt-4o",  # or deepseek-chat
    messages=[{"role": "user", "content": "Remember I use Neovim"}],
    tools=adapter.tools,
)
if response.choices[0].message.tool_calls:
    outputs = adapter.handle_tool_calls(
        [c.model_dump() for c in response.choices[0].message.tool_calls]
    )
```

### 3. Claude — tool_use and MCP

```python
from memolite.adapters.anthropic import AnthropicAdapter

adapter = AnthropicAdapter(store)
response = client.messages.create(
    model="claude-3-5-sonnet-20240620",
    messages=[{"role": "user", "content": "..."}],
    tools=adapter.tools,
)
results = adapter.handle_tool_use([b for b in response.content if b.type == "tool_use"])
```

Claude Desktop and Cursor via MCP, no code:

```bash
pip install "memolite[mcp]"
memolite-mcp --db agent.db
```

`claude_desktop_config.json`:

```json
{"mcpServers": {"memolite": {"command": "memolite-mcp", "args": ["--db", "/path/to/agent.db"]}}}
```

Tools exposed: `remember`, `recall`, `health`.

### 4. OpenCode, Cursor, Windsurf — as a skill

Once installed via `memolite skill install`, the skill is auto-discovered. Invoke naturally:

```
remember that I prefer type hints
recall what do I prefer for Python?
```

The skill will use `MemoryStore` and `recall().prompt` injection internally.

## Store contract

```python
from memolite import MemoryStore, Config

store = MemoryStore("agent.db", Config(auto_consolidate_every=8))
store.add_turn(session="s1", role="user", content="hello")
store.remember("fact", importance=0.9, session_id="s1")
result = store.recall("hello", session="s1", limit=5)
print(result.prompt)  # ready to inject
print(store.health_check())
store.backup("backup.db")
store.export_json("dump.json")
```

Inspect:

```bash
sqlite3 agent.db "SELECT kind, summary, score FROM memories ORDER BY score DESC LIMIT 5;"
memolite health --db agent.db
```

## References

- Core: `src/memolite/store.py` — MemoryStore
- Adapters: `src/memolite/adapters/` — openai, anthropic, generic
- MCP: `src/memolite/mcp_server.py` — memolite-mcp
- CLI: `src/memolite/cli.py` — memolite skill install
