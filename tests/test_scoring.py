from memolite.scoring import composite_score, frequency_factor, recency_factor


def test_recency() -> None:
    assert recency_factor(0, half_life_days=30, now=30 * 86400) == 0.5
    assert recency_factor(0, half_life_days=30, now=0) == 1.0


def test_frequency() -> None:
    assert frequency_factor(0) == 0
    assert frequency_factor(100) > frequency_factor(1)


def test_composite() -> None:
    s = composite_score(0.8, 5, 0, 0.5, now=0)
    assert 0 <= s <= 1
