"""Eval v1: fixed facts + paraphrased queries. Offline, deterministic.

Run: python examples/07_eval_recall.py
Compares FTS-only vs hybrid rerank on recall@1/recall@3 + latency.
"""

from __future__ import annotations

import time

from memolite import Config, MemoryStore

FACTS = [
    "Project SHUCHI uses Maya OS kiosk on Rs35k mini-PC",
    "Deploy key rotates every Friday at 18:00",
    "DB host is db-1 internal port 5432",
    "User prefers concise Python with type hints",
    "Navy needs 2-3 sanitiser units per base",
    "DGQA requires hash-chain WORM audit logs",
    "YARA rules live in /opt/shuchi/rules",
    "ClamAV runs offline with daily cvd updates",
    "TPM 2.0 signs every sanitised file receipt",
    "DoD 3-pass wipe before USB reuse",
    "Matisoft ships heavy 7-module enterprise suite",
    "OPSWAT kiosk costs around Rs15L imported",
    "iDEX Open Challenge deadline 30 Sep 2026",
    "Agent.btz infected SIPRNet via USB in 2008",
    "Buckshot Yankee took 14 months to clean",
    "Glasswall rebuilds files per ISO32000 offline",
    "oletools plus mraptor score macro risk",
    "Hindi OOXML fidelity measured after CDR rebuild",
    "Gemma 4 open models for offline macro scoring",
    "DMI essay forum launched 16 Sep 2026",
]

QUERIES = [  # (query, expected substring)
    ("what OS does the kiosk run?", "Maya OS"),
    ("when does deploy key rotate?", "Friday"),
    ("where is the database?", "db-1"),
    ("coding style?", "type hints"),
    ("how many units per base?", "2-3"),
    ("audit requirement?", "WORM"),
    ("where are YARA rules?", "/opt/shuchi"),
    ("antivirus updates?", "cvd"),
    ("what signs receipts?", "TPM"),
    ("wipe standard?", "DoD 3-pass"),
    ("Matisoft product?", "7-module"),
    ("OPSWAT cost?", "Rs15L"),
    ("challenge deadline?", "30 Sep 2026"),
    ("2008 USB worm?", "Agent.btz"),
    ("cleanup op name?", "Buckshot Yankee"),
    ("CDR standard?", "ISO32000"),
    ("macro tools?", "mraptor"),
    ("Hindi fidelity?", "CDR rebuild"),
    ("offline model?", "Gemma 4"),
    ("DMI launch?", "16 Sep 2026"),
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
    ("Maya OS kiosk", "Maya OS"),
    ("deploy key Friday", "Friday"),
    ("db-1 host", "db-1"),
    ("type hints", "type hints"),
    ("units per base", "2-3"),
    ("WORM audit", "WORM"),
    ("YARA rules path", "/opt/shuchi"),
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
