from memolite import MemoryStore, plug
from memolite.adapters.anthropic import AnthropicAdapter
from memolite.adapters.generic import GenericAdapter
from memolite.adapters.openai import OpenAIAdapter


def test_generic_inject() -> None:
    s = MemoryStore(":memory:")
    s.add_turn(session="s1", role="user", content="Remember I prefer Python")
    a = GenericAdapter(s)
    prompt = a.inject("how to code?", session_id="s1")
    assert "Python" in prompt or "Recent" in prompt
    msgs = a.build_messages(system="You are helpful", user_query="how to code?", session_id="s1")
    assert len(msgs) == 2
    s.close()


def test_openai_tools() -> None:
    s = MemoryStore(":memory:")
    a = OpenAIAdapter(s)
    assert len(a.tools) == 2
    # handle remember
    r = a.handle("memolite_remember", {"content": "hello", "importance": 0.8})
    assert "id" in r
    # recall
    r2 = a.handle("memolite_recall", {"query": "hello"})
    assert "memories" in r2
    # tool_calls
    out = a.handle_tool_calls(
        [{"id": "1", "function": {"name": "memolite_recall", "arguments": '{"query": "hello"}'}}]
    )
    assert out[0]["role"] == "tool"
    s.close()


def test_anthropic_tools() -> None:
    s = MemoryStore(":memory:")
    a = AnthropicAdapter(s)
    assert len(a.tools) == 2
    out = a.handle_tool_use(
        [{"type": "tool_use", "id": "1", "name": "memolite_recall", "input": {"query": "hello"}}]
    )
    assert out[0]["type"] == "tool_result"
    s.close()


def test_plug_dispatch() -> None:
    s = MemoryStore(":memory:")
    assert isinstance(plug(s, "openai"), OpenAIAdapter)
    assert isinstance(plug(s, "deepseek"), OpenAIAdapter)
    assert isinstance(plug(s, "claude"), AnthropicAdapter)
    assert isinstance(plug(s, "generic"), GenericAdapter)
    s.close()


def test_mcp_import() -> None:
    # import should work without mcp installed, run should error gracefully
    from memolite.mcp_server import run

    assert callable(run)
