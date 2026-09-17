"""Heuristic consolidator - offline, no LLM required."""

from __future__ import annotations

import re

# naive heuristics: extract lines that look like facts/preferences
_FACT_PATTERNS = [
    re.compile(r"^\s*(remember|note|prefer|i am|i work on|my name is|i like|i use)\b", re.I),
    re.compile(r"\b(prefer|uses?|works on|project is|called)\b", re.I),
]

_STOPWORDS = {"the", "is", "a", "an", "and", "or", "to", "of", "in", "on", "for", "with", "my", "i"}


def heuristic_consolidate(texts: list[str]) -> list[dict[str, object]]:
    """Extract candidate semantic memories from recent turns.

    Returns list of {content, summary, importance}.
    Pure python, deterministic.
    """
    out: list[dict[str, object]] = []
    seen: set[str] = set()
    for raw in texts:
        # split into sentences-ish
        for sent in re.split(r"[.\n]+", raw):
            s = sent.strip()
            if len(s) < 12 or len(s) > 400:
                continue
            low = s.lower()
            if low in seen:
                continue
            # score pattern match
            is_fact = any(p.search(s) for p in _FACT_PATTERNS)
            # fallback: contains 2+ non-stopword caps? treat as entity line
            words = [w for w in re.findall(r"\w+", low) if w not in _STOPWORDS]
            is_entity = len(words) >= 3 and len(s.split()) <= 20
            if not (is_fact or is_entity):
                continue
            seen.add(low)
            # importance: fact patterns higher, longer = slightly lower
            imp = 0.75 if is_fact else 0.55
            if len(s) > 120:
                imp -= 0.1
            out.append(
                {"content": s, "summary": s, "importance": max(0.2, imp), "kind": "semantic"}
            )
            if len(out) >= 5:
                break
        if len(out) >= 5:
            break
    return out
