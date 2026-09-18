"""Eval v1: fixed facts + paraphrased queries. Offline, deterministic.

Run: python examples/07_eval_recall.py
Compares FTS-only vs hybrid rerank on recall@1/recall@3 + latency.
All facts are fictional and generic — no real project data.
"""

from __future__ import annotations

import time

from memolite import Config, MemoryStore

FACTS = [
    "Project Atlas runs on Ubuntu mini-PC under Rs50k",
    "Deploy key rotates every Friday at 18:00",
    "DB host is db-1 internal port 5432",
    "User prefers concise Python with type hints",
    "Field team needs 2-3 scanner units per site",
    "Compliance requires hash-chain WORM audit logs",
    "YARA rules live in /opt/agent/rules",
    "ClamAV runs offline with daily cvd updates",
    "TPM 2.0 signs every processed file receipt",
    "DoD 3-pass wipe before USB reuse",
    "VendorX ships heavy 7-module enterprise suite",
    "Import kiosk costs around Rs15L landed",
    "Launch deadline 30 Sep 2026",
    "2008 USB worm took down the test grid",
    "Cleanup op took 14 months to finish",
    "Rebuilder works per ISO32000 fully offline",
    "Scanner plus parser score macro risk",
    "Hindi document fidelity measured after rebuild",
    "Open 7B models for offline macro scoring",
    "Dev forum launched 16 Sep 2026",
]

QUERIES = [  # (query, expected substring)
    ("what OS does the node run?", "Ubuntu"),
    ("when does deploy key rotate?", "Friday"),
    ("where is the database?", "db-1"),
    ("coding style?", "type hints"),
    ("how many units per site?", "2-3"),
    ("audit requirement?", "WORM"),
    ("where are YARA rules?", "/opt/agent"),
    ("antivirus updates?", "cvd"),
    ("what signs receipts?", "TPM"),
    ("wipe standard?", "DoD 3-pass"),
    ("VendorX product?", "7-module"),
    ("import cost?", "Rs15L"),
    ("launch deadline?", "30 Sep 2026"),
    ("2008 USB worm?", "test grid"),
    ("cleanup duration?", "14 months"),
    ("rebuild standard?", "ISO32000"),
    ("macro tools?", "macro risk"),
    ("Hindi fidelity?", "rebuild"),
    ("offline model?", "7B"),
    ("forum launch?", "16 Sep 2026"),
]


def run(config: Config, queries: list[tuple[str, str]] | None = None) -> dict[str, float]:
    s = MemoryStore(":memory:", config)
    for f in FACTS:
        s.remember(f, importance=0.8)
    qs = queries or QUERIES
    r1 = r3 = 0
    t0 = time.time()
    for q, exp in qs:
        res = s.recall(q, limit=3)
        texts = [m.summary + " " + m.content for m in res.memories]
        if texts and exp.lower() in texts[0].lower():
            r1 += 1
        if any(exp.lower() in t.lower() for t in texts):
            r3 += 1
    dt = (time.time() - t0) * 1000 / max(1, len(qs))
    s.close()
    return {"recall@1": r1 / len(qs), "recall@3": r3 / len(qs), "ms/query": round(dt, 2)}


KEYWORD_QUERIES = [  # same facts, keyword wording (what the engine is built for)
    ("Ubuntu node", "Ubuntu"),
    ("deploy key Friday", "Friday"),
    ("db-1 host", "db-1"),
    ("type hints", "type hints"),
    ("units per site", "2-3"),
    ("WORM audit", "WORM"),
    ("YARA rules path", "/opt/agent"),
    ("ClamAV cvd", "cvd"),
    ("TPM receipt", "TPM"),
    ("DoD wipe", "DoD 3-pass"),
]


if __name__ == "__main__":
    print("paraphrase suite (hard for keyword engines — documents the gap):")
    print("  FTS-only :", run(Config(hybrid_enabled=False, auto_consolidate_every=0)))
    print("  hybrid   :", run(Config(hybrid_enabled=True, auto_consolidate_every=0)))
    print("keyword suite (what the engine is built for):")
    print(
        "  FTS-only :", run(Config(hybrid_enabled=False, auto_consolidate_every=0), KEYWORD_QUERIES)
    )
    print(
        "  hybrid   :", run(Config(hybrid_enabled=True, auto_consolidate_every=0), KEYWORD_QUERIES)
    )
