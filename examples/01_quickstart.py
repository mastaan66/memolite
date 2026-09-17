"""Quickstart - 5 lines to agentic memory."""

from memolite import Config, MemoryStore

with MemoryStore(":memory:", Config(auto_consolidate_every=4)) as store:
    store.add_turn(session="demo", role="user", content="I prefer python, no boilerplate classes")
    store.add_turn(session="demo", role="assistant", content="noted - pythonic, minimal")
    store.add_turn(
        session="demo", role="user", content="Remember I prefer concise Python with type hints"
    )
    store.add_turn(
        session="demo", role="user", content="I work on data pipelines with strict typing"
    )

    # heuristic consolidator auto-ran at 4 turns
    res = store.recall("how should I write code?", session="demo", limit=3)
    print("--- prompt ---")
    print(res.prompt)
    print("\n--- memories ---")
    for m in res.memories:
        print(f"{m.kind} [{m.score:.2f}] {m.summary}")

    # explicit
    m = store.remember("user prefers functional style, minimal classes", importance=0.9)
    print("\nremembered:", m.summary)
    print(store.stats())
