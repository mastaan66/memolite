"""Claude - plug and play via tool_use."""

from memolite import MemoryStore
from memolite.adapters.anthropic import AnthropicAdapter

store = MemoryStore(":memory:")
store.add_turn(session="s1", role="user", content="Remember I work on data pipelines")

adapter = AnthropicAdapter(store)
tools = adapter.tools

fake_blocks = [
    {
        "type": "tool_use",
        "id": "to1",
        "name": "memolite_recall",
        "input": {"query": "work", "session_id": "s1"},
    },
]
print(adapter.handle_tool_use(fake_blocks))
print(adapter.inject("what do I work on?", session_id="s1"))
