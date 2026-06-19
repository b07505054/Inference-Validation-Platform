from src.ivp.statistics import (
    bootstrap_percentile_ci,
    mann_whitney_u_test,
    percentile,
    regression_gate,
)


def test_percentile_nearest_rank_edges():
    assert percentile([], 95) == 0.0
    assert percentile([7.0], 95) == 7.0
    assert percentile([1, 2, 3, 4], 50) == 2.0
    assert percentile([1, 2, 3, 4, 5], 95) == 5.0


def test_bootstrap_percentile_ci_is_deterministic():
    values = [1, 2, 3, 4, 5, 6, 7, 8]
    first = bootstrap_percentile_ci(values, resamples=200, seed=42)
    second = bootstrap_percentile_ci(values, resamples=200, seed=42)

    assert first == second
    assert first["available"] is True
    assert first["sample_count"] == len(values)
    assert first["p95_ci"][0] <= first["p95"] <= first["p95_ci"][1]


def test_mann_whitney_detects_directional_shifts():
    faster = mann_whitney_u_test(
        baseline=[10, 11, 12, 13, 14, 15],
        candidate=[1, 2, 3, 4, 5, 6],
    )
    slower = mann_whitney_u_test(
        baseline=[1, 2, 3, 4, 5, 6],
        candidate=[10, 11, 12, 13, 14, 15],
    )
    same = mann_whitney_u_test(
        baseline=[1, 1, 2, 2, 3, 3],
        candidate=[1, 1, 2, 2, 3, 3],
    )

    assert faster["available"] is True
    assert faster["effect_direction"] == "candidate_faster"
    assert faster["p_value"] < 0.05
    assert slower["effect_direction"] == "candidate_slower"
    assert slower["p_value"] < 0.05
    assert same["effect_direction"] == "no_shift"
    assert same["p_value"] > 0.9


def test_regression_gate_allows_improvement_and_small_regression():
    improved = regression_gate(
        baseline=[100, 101, 102, 103, 104, 105],
        candidate=[80, 81, 82, 83, 84, 85],
    )
    small_regression = regression_gate(
        baseline=[100, 101, 102, 103, 104, 105],
        candidate=[101, 102, 103, 104, 105, 108],
        threshold_pct=3.0,
    )

    assert improved["passed"] is True
    assert improved["reason"] == "candidate_not_regressed"
    assert small_regression["passed"] is True
    assert small_regression["reason"] in {
        "within_regression_threshold",
        "not_statistically_significant",
    }


def test_regression_gate_fails_significant_large_regression():
    failed = regression_gate(
        baseline=list(range(10, 60)),
        candidate=list(range(30, 80)),
        threshold_pct=3.0,
        alpha=0.05,
    )

    assert failed["passed"] is False
    assert failed["reason"] == "significant_regression"
