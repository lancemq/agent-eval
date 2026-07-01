"""Pure-Python bootstrap confidence intervals and paired significance tests.

No external dependencies. For typical evaluation sample sizes (hundreds to
thousands of rows) the runtime is well under a second.
"""

from __future__ import annotations

import math
import random
from typing import Dict, List, Optional, Sequence, Tuple


def mean(xs: Sequence[float]) -> float:
    """Arithmetic mean; 0.0 for empty input."""
    if not xs:
        return 0.0
    return sum(xs) / len(xs)


def bootstrap_ci(
    xs: Sequence[float],
    n_resamples: int = 1000,
    confidence: float = 0.95,
    seed: Optional[int] = None,
) -> Tuple[float, float, float]:
    """Bootstrap confidence interval for the mean.

    Returns ``(low, high, point)`` where ``point`` is the sample mean.
    Uses the percentile method. For ``len(xs) < 2`` the CI collapses to the
    point estimate.
    """
    n = len(xs)
    point = mean(xs)
    if n < 2:
        return point, point, point

    rng = random.Random(seed)
    # Pre-convert to a list for fast indexing
    xs_list = list(xs)
    resampled_means: List[float] = []
    for _ in range(n_resamples):
        total = 0.0
        for _ in range(n):
            total += xs_list[rng.randrange(n)]
        resampled_means.append(total / n)

    resampled_means.sort()
    alpha = 1.0 - confidence
    low_idx = int(math.floor((alpha / 2.0) * n_resamples))
    high_idx = int(math.floor((1.0 - alpha / 2.0) * n_resamples))
    low_idx = max(0, min(low_idx, n_resamples - 1))
    high_idx = max(0, min(high_idx, n_resamples - 1))
    return resampled_means[low_idx], resampled_means[high_idx], point


def paired_bootstrap_delta(
    a: Sequence[float],
    b: Sequence[float],
    n_resamples: int = 2000,
    confidence: float = 0.95,
    seed: Optional[int] = None,
) -> Dict[str, float]:
    """Paired bootstrap on per-row scores ``b - a``.

    ``a`` is the baseline (first report), ``b`` is the contender. The two
    sequences must be paired (same length, same row order). For unpaired or
    unequal-length inputs we fall back to an unpaired bootstrap of the
    difference of means.

    Returns a dict with:
      - ``mean_delta``: mean(b) - mean(a)
      - ``ci_low`` / ``ci_high``: bootstrap CI of the delta
      - ``significant``: True if the CI excludes 0
      - ``p_value_approx``: rough p-value (0.05 if significant else >= 0.05)
      - ``n``: number of paired samples
      - ``positive`` / ``negative``: count of rows where b > a / b < a
    """
    a_list = list(a)
    b_list = list(b)

    point_a = mean(a_list)
    point_b = mean(b_list)
    mean_delta = point_b - point_a

    paired = len(a_list) == len(b_list) and len(a_list) > 0
    n = len(a_list) if paired else max(len(a_list), len(b_list), 1)

    positive = 0
    negative = 0
    if paired:
        for x, y in zip(a_list, b_list):
            if y > x:
                positive += 1
            elif y < x:
                negative += 1

    if n < 2:
        return {
            "mean_delta": mean_delta,
            "ci_low": mean_delta,
            "ci_high": mean_delta,
            "significant": False,
            "p_value_approx": 1.0,
            "n": n,
            "positive": positive,
            "negative": negative,
        }

    rng = random.Random(seed)
    resampled_deltas: List[float] = []
    if paired:
        for _ in range(n_resamples):
            total = 0.0
            for _ in range(n):
                idx = rng.randrange(n)
                total += b_list[idx] - a_list[idx]
            resampled_deltas.append(total / n)
    else:
        na = len(a_list)
        nb = len(b_list)
        for _ in range(n_resamples):
            ta = sum(a_list[rng.randrange(na)] for _ in range(na)) / na if na else 0.0
            tb = sum(b_list[rng.randrange(nb)] for _ in range(nb)) / nb if nb else 0.0
            resampled_deltas.append(tb - ta)

    resampled_deltas.sort()
    alpha = 1.0 - confidence
    low_idx = max(0, min(int(math.floor((alpha / 2.0) * n_resamples)), n_resamples - 1))
    high_idx = max(0, min(int(math.floor((1.0 - alpha / 2.0) * n_resamples)), n_resamples - 1))
    ci_low = resampled_deltas[low_idx]
    ci_high = resampled_deltas[high_idx]
    significant = (ci_low > 0 or ci_high < 0) and not (ci_low <= 0 <= ci_high)

    # Rough p-value: fraction of resamples crossing zero (two-sided *2).
    crossing = sum(1 for d in resampled_deltas if d <= 0)
    frac = crossing / n_resamples
    p_value_approx = min(1.0, 2.0 * min(frac, 1.0 - frac))

    return {
        "mean_delta": mean_delta,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "significant": significant,
        "p_value_approx": round(p_value_approx, 4),
        "n": n,
        "positive": positive,
        "negative": negative,
    }
