import math
import random
from collections import Counter


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    rank = math.ceil((p / 100.0) * len(ordered)) - 1
    rank = max(0, min(rank, len(ordered) - 1))
    return ordered[rank]


def bootstrap_percentile_ci(
    values: list[float],
    percentile_value: float = 95.0,
    confidence: float = 0.95,
    resamples: int = 1000,
    seed: int = 0,
) -> dict:
    samples = [float(value) for value in values]
    estimate = percentile(samples, percentile_value)
    if not samples:
        return {
            "sample_count": 0,
            "p95": 0.0,
            "p95_ci": [0.0, 0.0],
            "confidence_level": confidence,
            "resamples": resamples,
            "method": "bootstrap_nearest_rank",
            "seed": seed,
            "available": False,
            "reason": "empty_samples",
        }

    rng = random.Random(seed)
    bootstrapped = []
    for _ in range(resamples):
        resample = [samples[rng.randrange(len(samples))] for _ in samples]
        bootstrapped.append(percentile(resample, percentile_value))

    alpha = 1.0 - confidence
    lower = percentile(bootstrapped, (alpha / 2.0) * 100.0)
    upper = percentile(bootstrapped, (1.0 - alpha / 2.0) * 100.0)
    return {
        "sample_count": len(samples),
        "p95": round(estimate, 6),
        "p95_ci": [round(lower, 6), round(upper, 6)],
        "confidence_level": confidence,
        "resamples": resamples,
        "method": "bootstrap_nearest_rank",
        "seed": seed,
        "available": True,
    }


def _rank_samples(values: list[tuple[float, int]]) -> tuple[list[float], float]:
    ordered = sorted(values, key=lambda item: item[0])
    ranks = [0.0] * len(ordered)
    tie_term = 0.0
    i = 0
    while i < len(ordered):
        j = i + 1
        while j < len(ordered) and ordered[j][0] == ordered[i][0]:
            j += 1
        average_rank = (i + 1 + j) / 2.0
        for index in range(i, j):
            ranks[index] = average_rank
        tie_size = j - i
        tie_term += tie_size**3 - tie_size
        i = j
    return ranks, tie_term


def mann_whitney_u_test(baseline: list[float], candidate: list[float]) -> dict:
    x = [float(value) for value in baseline]
    y = [float(value) for value in candidate]
    if not x or not y:
        return {
            "available": False,
            "reason": "empty_samples",
            "u_statistic": None,
            "p_value": None,
            "effect_direction": "unknown",
        }

    combined = [(value, 0) for value in x] + [(value, 1) for value in y]
    ranks, tie_term = _rank_samples(combined)
    rank_sum_x = sum(rank for rank, item in zip(ranks, sorted(combined, key=lambda row: row[0])) if item[1] == 0)
    n1 = len(x)
    n2 = len(y)
    u1 = rank_sum_x - (n1 * (n1 + 1) / 2.0)
    u2 = n1 * n2 - u1
    u = min(u1, u2)

    mean_u = n1 * n2 / 2.0
    n = n1 + n2
    tie_correction = tie_term / (n * (n - 1)) if n > 1 else 0.0
    variance = (n1 * n2 / 12.0) * ((n + 1) - tie_correction)
    if variance <= 0.0:
        p_value = 1.0
        z_score = 0.0
    else:
        z_score = (u - mean_u) / math.sqrt(variance)
        p_value = math.erfc(abs(z_score) / math.sqrt(2.0))

    baseline_median = percentile(x, 50)
    candidate_median = percentile(y, 50)
    if candidate_median < baseline_median:
        direction = "candidate_faster"
    elif candidate_median > baseline_median:
        direction = "candidate_slower"
    else:
        direction = "no_shift"

    return {
        "available": True,
        "u_statistic": round(u, 6),
        "u_baseline": round(u1, 6),
        "u_candidate": round(u2, 6),
        "p_value": round(p_value, 12),
        "z_score": round(z_score, 6),
        "effect_direction": direction,
        "baseline_sample_count": n1,
        "candidate_sample_count": n2,
    }


def regression_gate(
    baseline: list[float],
    candidate: list[float],
    threshold_pct: float = 3.0,
    alpha: float = 0.05,
) -> dict:
    baseline_p95 = percentile(baseline, 95)
    candidate_p95 = percentile(candidate, 95)
    mann_whitney = mann_whitney_u_test(baseline, candidate)

    if not baseline or not candidate:
        return {
            "passed": True,
            "reason": "insufficient_samples",
            "baseline_p95": baseline_p95,
            "candidate_p95": candidate_p95,
            "p95_delta_pct": 0.0,
            "threshold_pct": threshold_pct,
            "alpha": alpha,
            "mann_whitney": mann_whitney,
        }

    if baseline_p95 == 0.0:
        delta_pct = 0.0 if candidate_p95 == 0.0 else math.inf
    else:
        delta_pct = ((candidate_p95 - baseline_p95) / baseline_p95) * 100.0

    significant = (
        mann_whitney.get("available") is True
        and mann_whitney.get("p_value") is not None
        and mann_whitney["p_value"] < alpha
    )
    regression = delta_pct > threshold_pct and significant

    if candidate_p95 <= baseline_p95:
        reason = "candidate_not_regressed"
    elif delta_pct <= threshold_pct:
        reason = "within_regression_threshold"
    elif not significant:
        reason = "not_statistically_significant"
    else:
        reason = "significant_regression"

    return {
        "passed": not regression,
        "reason": reason,
        "baseline_p95": round(baseline_p95, 6),
        "candidate_p95": round(candidate_p95, 6),
        "p95_delta_pct": round(delta_pct, 6) if math.isfinite(delta_pct) else "inf",
        "threshold_pct": threshold_pct,
        "alpha": alpha,
        "mann_whitney": mann_whitney,
    }
