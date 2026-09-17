"""Quickstart - 5 lines to agentic memory."""

from memolite import Config, MemoryStore

with MemoryStore(":memory:", Config(auto_consolidate_every=4)) as store:
    store.add_turn(session="demo", role="user", content="I prefer python, no boilerplate classes")
    store.add_turn(session="demo", role="assistant", content="noted - pythonic, minimal")
    store.add_turn(
        session="demo", role="user", content="Remember SHUCHI is USB sanitiser for Maya OS"
    )
    store.add_turn(session="demo", role="user", content="We use ClamAV + YARA + oletools")

    # heuristic consolidator auto-ran at 4 turns
    res = store.recall("what project am I on?", session="demo", limit=3)
    print("--- prompt ---")
    print(res.prompt)
    print("\n--- memories ---")
    for m in res.memories:
        print(f"{m.kind} [{m.score:.2f}] {m.summary}")

    # explicit
    m = store.remember("user is staff eng, fintech", importance=0.9)
    print("\nremembered:", m.summary)
    print(store.stats())
