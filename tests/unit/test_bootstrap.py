"""Tests for bootstrap confidence intervals and paired significance."""

from agent_eval.stats import bootstrap_ci, mean, paired_bootstrap_delta


def test_mean_empty():
    assert mean([]) == 0.0


def test_mean_basic():
    assert mean([1.0, 2.0, 3.0]) == 2.0


def test_bootstrap_ci_deterministic_with_seed():
    xs = [0.1, 0.4, 0.6, 0.8, 0.3, 0.5, 0.7, 0.9, 0.2, 0.55]
    r1 = bootstrap_ci(xs, seed=42)
    r2 = bootstrap_ci(xs, seed=42)
    assert r1 == r2
    low, high, point = r1
    assert low <= point <= high
    assert 0.0 <= low <= 1.0


def test_bootstrap_ci_single_sample():
    low, high, point = bootstrap_ci([0.5], seed=1)
    assert low == high == point == 0.5


def test_bootstrap_ci_covers_population_mean():
    # For a reasonably-sized sample, the 95% CI should bracket the sample mean
    xs = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0] * 5
    low, high, point = bootstrap_ci(xs, n_resamples=500, seed=7)
    assert low <= point <= high


def test_paired_bootstrap_clear_improvement_is_significant():
    a = [0.2, 0.3, 0.25, 0.35, 0.2, 0.3, 0.25, 0.3, 0.2, 0.3]
    b = [0.8, 0.85, 0.9, 0.88, 0.82, 0.9, 0.85, 0.87, 0.83, 0.89]
    result = paired_bootstrap_delta(a, b, seed=42)
    assert result["mean_delta"] > 0.5
    assert result["significant"] is True
    assert result["ci_low"] > 0
    assert result["positive"] == 10
    assert result["negative"] == 0


def test_paired_bootstrap_no_difference_not_significant():
    a = [0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5]
    b = [0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5]
    result = paired_bootstrap_delta(a, b, seed=42)
    assert result["mean_delta"] == 0.0
    assert result["significant"] is False


def test_paired_bootstrap_deterministic():
    a = [0.1, 0.4, 0.6, 0.8, 0.3]
    b = [0.5, 0.7, 0.2, 0.9, 0.4]
    r1 = paired_bootstrap_delta(a, b, seed=99)
    r2 = paired_bootstrap_delta(a, b, seed=99)
    assert r1 == r2
