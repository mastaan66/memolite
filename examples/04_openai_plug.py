"""OpenAI, ChatGPT, DeepSeek - plug and play. No server."""

from memolite import MemoryStore
from memolite.adapters.openai import OpenAIAdapter

store = MemoryStore(":memory:")
store.add_turn(session="s1", role="user", content="Remember I prefer Neovim")

adapter = OpenAIAdapter(store)

# 1. pass tools to any OpenAI compatible API
tools = adapter.tools  # use with client.chat.completions.create(tools=tools)

# 2. simulate a tool call from the model
fake_calls = [
    {
        "id": "call_1",
        "function": {
            "name": "memolite_recall",
            "arguments": '{"query": "editor", "session_id": "s1"}',
        },
    },
    {
        "id": "call_2",
        "function": {
            "name": "memolite_remember",
            "arguments": '{"content": "User uses Neovim on Linux", "importance": 0.9}',
        },
    },
]
outputs = adapter.handle_tool_calls(fake_calls)
print(outputs)

# 3. generic fallback also works if tools not supported
print(adapter.inject("what editor do I use?", session_id="s1"))
