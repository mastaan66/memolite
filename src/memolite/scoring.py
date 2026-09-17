"""Scoring and decay utilities."""

from __future__ import annotations

import math
import time


def recency_factor(
    last_accessed: int, half_life_days: float = 30.0, now: int | None = None
) -> float:
    """Exponential decay in [0,1], 1 = now."""
    if now is None:
        now = int(time.time())
    age_days = max(0.0, (now - last_accessed) / 86400.0)
    if half_life_days <= 0:
        return 1.0
    return math.exp(-math.log(2) * age_days / half_life_days)


def frequency_factor(access_count: int) -> float:
    """Log-normalized frequency in [0,1)."""
    return math.log1p(access_count) / (math.log1p(access_count) + 1.5)


def composite_score(
    importance: float,
    access_count: int,
    last_accessed: int,
    reward: float = 0.0,
    *,
    w_imp: float = 0.4,
    w_freq: float = 0.3,
    w_rec: float = 0.2,
    w_rew: float = 0.1,
    half_life_days: float = 30.0,
    now: int | None = None,
) -> float:
    rec = recency_factor(last_accessed, half_life_days, now=now)
    freq = frequency_factor(access_count)
    # clamp importance/reward
    imp = max(0.0, min(1.0, importance))
    rew = max(0.0, min(1.0, reward))
    return w_imp * imp + w_freq * freq + w_rec * rec + w_rew * rew
