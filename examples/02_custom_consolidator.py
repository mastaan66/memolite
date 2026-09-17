"""Custom LLM consolidator + openai embedder hook."""

from memolite import Config, MemoryStore


def my_llm_consolidator(texts: list[str]) -> list[dict]:
    # plug your LLM here - must return [{"content","summary","importance","kind"}]
    # example heuristic that promotes lines with "remember"
    out = []
    for t in texts:
        if "remember" in t.lower():
            out.append({"content": t, "summary": t, "importance": 0.85, "kind": "semantic"})
    return out


store = MemoryStore(":memory:", Config(consolidator=my_llm_consolidator, auto_consolidate_every=2))
store.add_turn(session="s1", role="user", content="remember I use neovim")
store.add_turn(session="s1", role="user", content="hello")
print(store.recall("editor", session="s1").prompt)
store.close()
