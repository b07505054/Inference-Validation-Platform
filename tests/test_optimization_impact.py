"""Tests for OptimizationImpactValidator / validate_optimization_impact.

All tests use plain dict fixtures. No dependency on heterogeneous-inference-runtime.
"""

import copy
import json

import pytest

from src.ivp.optimization_impact import (
    OptimizationEvidence,
    OptimizationImpactReport,
    OptimizationImpactValidator,
    OptimizationMetricDelta,
    validate_optimization_impact,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_TB_CACHE = (
    "prefix_cache_simulated_adjusted_plan_not_real_kv_cache_or_network_measurement"
)
_TB_REPORT = (
    "optimization_impact_validation_simulated_not_measured_cluster_performance"
)

# Baseline values (match heterogeneous-inference-runtime fixture math):
#   prefill_service_ms = 31.2, kv_transfer = 4/32 = 0.125, handoff = 0.2
#   pd_ttft_baseline   = 31.525
#   pd_tpot_baseline   = 8.5
_BASELINE_TTFT = 31.525
_BASELINE_TPOT = 8.5


def _artifact(
    hit_type: str = "local_hit",
    saved_ms: float = 10.0,
    remote_bytes: float = 0.0,
    optimized_ttft: float | None = None,
    optimized_tpot: float | None = None,
    baseline_ttft: float = _BASELINE_TTFT,
    baseline_tpot: float = _BASELINE_TPOT,
    truth_boundary: str = _TB_CACHE,
    **extra,
) -> dict:
    if optimized_ttft is None:
        # Apply default expected improvement for the hit type.
        if hit_type == "local_hit":
            optimized_ttft = baseline_ttft - saved_ms
        elif hit_type == "remote_hit":
            # Assume 2 MB / 32 MB/ms = 0.0625 ms transfer cost.
            optimized_ttft = baseline_ttft - saved_ms + 0.0625
        else:
            optimized_ttft = baseline_ttft
    if optimized_tpot is None:
        optimized_tpot = baseline_tpot  # prefix cache does not affect TPOT

    d = {
        "artifact_name": "llm_plan_test",
        "model_name": "llama3_8b",
        "selected_policy": "pd_split",
        "truth_boundary": truth_boundary,
        "prefix_cache_hit_type": hit_type,
        "prefix_cache_hit_tokens": 50,
        "prefix_cache_saved_prefill_ms": saved_ms,
        "prefix_cache_remote_transfer_bytes": remote_bytes,
        "baseline_ttft_ms": baseline_ttft,
        "optimized_ttft_ms": optimized_ttft,
        "baseline_tpot_ms": baseline_tpot,
        "optimized_tpot_ms": optimized_tpot,
    }
    d.update(extra)
    return d


# ---------------------------------------------------------------------------
# Required tests
# ---------------------------------------------------------------------------

def test_local_hit_generates_ttft_improvement_evidence():
    report = validate_optimization_impact(_artifact("local_hit", saved_ms=10.0))
    assert isinstance(report, OptimizationImpactReport)
    ev = report.optimization_evidence[0]
    assert ev.optimization_name == "prefix_cache"
    assert ev.decision_name == "local_hit"
    ttft_deltas = [m for m in ev.affected_metrics if m.metric_name == "ttft_ms"]
    assert ttft_deltas, "ttft_ms must appear in affected_metrics"
    assert ttft_deltas[0].direction == "improvement"
    assert ttft_deltas[0].delta_value < 0
    assert report.overall_status == "pass"


def test_remote_hit_generates_transfer_tradeoff():
    remote_bytes = 2.0 * 1024 * 1024   # 2 MB
    report = validate_optimization_impact(
        _artifact("remote_hit", saved_ms=10.0, remote_bytes=remote_bytes)
    )
    ev = report.optimization_evidence[0]
    assert ev.decision_name == "remote_hit"
    transfer_tradeoffs = [
        m for m in ev.tradeoff_metrics if m.metric_name == "remote_transfer_bytes"
    ]
    assert transfer_tradeoffs, "remote_transfer_bytes must appear in tradeoff_metrics"
    assert transfer_tradeoffs[0].optimized_value == pytest.approx(remote_bytes)
    assert transfer_tradeoffs[0].direction == "regression"


def test_miss_generates_neutral_evidence():
    report = validate_optimization_impact(
        _artifact("miss", saved_ms=0.0, remote_bytes=0.0)
    )
    ev = report.optimization_evidence[0]
    assert ev.decision_name == "miss"
    # TTFT should be neutral (no change).
    if ev.affected_metrics:
        ttft = next((m for m in ev.affected_metrics if m.metric_name == "ttft_ms"), None)
        if ttft is not None:
            assert ttft.direction in ("neutral",)
    assert report.overall_status == "pass"


def test_missing_before_after_metrics_warns():
    artifact = {
        "artifact_name": "x",
        "model_name": "m",
        "selected_policy": "pd_split",
        "truth_boundary": _TB_CACHE,
        "prefix_cache_hit_type": "local_hit",
        "prefix_cache_saved_prefill_ms": 10.0,
        "prefix_cache_remote_transfer_bytes": 0.0,
        # Intentionally missing: baseline_ttft_ms, optimized_ttft_ms, etc.
    }
    report = validate_optimization_impact(artifact)
    assert report.overall_status == "warn"
    ev = report.optimization_evidence[0]
    assert ev.evidence_status == "warn"
    assert "missing" in ev.explanation.lower() or "before" in ev.explanation.lower()


def test_tpot_improvement_from_prefix_cache_warns():
    # TPOT improves materially → suspicious; prefix cache only affects prefill.
    report = validate_optimization_impact(
        _artifact("local_hit", saved_ms=10.0, optimized_tpot=_BASELINE_TPOT - 2.0)
    )
    assert report.overall_status == "warn"
    ev = report.optimization_evidence[0]
    assert ev.evidence_status == "warn"
    assert "tpot" in ev.explanation.lower()


def test_local_hit_with_remote_transfer_warns():
    report = validate_optimization_impact(
        _artifact("local_hit", saved_ms=10.0, remote_bytes=1024.0)
    )
    assert report.overall_status == "warn"
    ev = report.optimization_evidence[0]
    assert ev.evidence_status == "warn"
    assert "remote" in ev.explanation.lower() or "transfer" in ev.explanation.lower()


def test_remote_hit_without_transfer_warns():
    report = validate_optimization_impact(
        _artifact("remote_hit", saved_ms=10.0, remote_bytes=0.0)
    )
    assert report.overall_status == "warn"
    ev = report.optimization_evidence[0]
    assert ev.evidence_status == "warn"
    assert "remote" in ev.explanation.lower() or "transfer" in ev.explanation.lower()


def test_truth_boundary_required():
    artifact = _artifact("local_hit")
    artifact["truth_boundary"] = ""   # remove it
    report = validate_optimization_impact(artifact)
    assert report.overall_status == "warn"
    ev = report.optimization_evidence[0]
    assert ev.evidence_status == "warn"
    assert "truth_boundary" in ev.explanation.lower()


def test_report_overall_status_pass_when_all_evidence_pass():
    report = validate_optimization_impact(_artifact("local_hit", saved_ms=10.0))
    assert report.overall_status == "pass"
    assert all(e.evidence_status == "pass" for e in report.optimization_evidence)


def test_report_overall_status_warn_when_any_warn():
    # Inject a warning via missing truth_boundary.
    artifact = _artifact("local_hit")
    artifact["truth_boundary"] = ""
    report = validate_optimization_impact(artifact)
    assert report.overall_status == "warn"


def test_markdown_contains_before_after_delta():
    report = validate_optimization_impact(_artifact("local_hit", saved_ms=10.0))
    md = report.to_markdown()
    # Must contain before and after TTFT values and the delta.
    assert f"{_BASELINE_TTFT:.3f}" in md          # before
    assert f"{_BASELINE_TTFT - 10.0:.3f}" in md   # after
    assert "-10.000" in md                          # delta
    assert "ttft_ms" in md
    assert "improvement" in md


def test_deterministic_output():
    artifact = _artifact("local_hit", saved_ms=10.0)
    r1 = validate_optimization_impact(artifact)
    r2 = validate_optimization_impact(artifact)
    assert r1.to_dict() == r2.to_dict()
    assert r1.to_markdown() == r2.to_markdown()


# ---------------------------------------------------------------------------
# Additional coverage
# ---------------------------------------------------------------------------

def test_report_has_validator_truth_boundary():
    report = validate_optimization_impact(_artifact("local_hit"))
    assert report.truth_boundary == _TB_REPORT


def test_evidence_truth_boundary_is_from_artifact():
    report = validate_optimization_impact(_artifact("local_hit"))
    assert report.optimization_evidence[0].truth_boundary == _TB_CACHE


def test_to_dict_is_json_serializable():
    report = validate_optimization_impact(_artifact("local_hit", saved_ms=10.0))
    d = report.to_dict()
    # Must not raise.
    json.dumps(d)


def test_to_json_round_trips():
    report = validate_optimization_impact(_artifact("local_hit", saved_ms=10.0))
    parsed = json.loads(report.to_json())
    assert parsed["overall_status"] == report.overall_status
    assert parsed["truth_boundary"] == report.truth_boundary
    assert len(parsed["optimization_evidence"]) == len(report.optimization_evidence)


def test_validator_class_matches_function():
    artifact = _artifact("local_hit", saved_ms=10.0)
    r_fn = validate_optimization_impact(artifact)
    r_cls = OptimizationImpactValidator().validate(artifact)
    assert r_fn.to_dict() == r_cls.to_dict()


def test_does_not_mutate_input():
    artifact = _artifact("local_hit", saved_ms=10.0)
    snapshot = copy.deepcopy(artifact)
    validate_optimization_impact(artifact)
    assert artifact == snapshot


def test_remote_hit_ttft_lower_than_baseline():
    remote_bytes = 2.0 * 1024 * 1024
    report = validate_optimization_impact(
        _artifact("remote_hit", saved_ms=10.0, remote_bytes=remote_bytes)
    )
    ev = report.optimization_evidence[0]
    ttft = next(m for m in ev.affected_metrics if m.metric_name == "ttft_ms")
    assert ttft.direction == "improvement"
    assert ttft.delta_value < 0


def test_miss_with_nonzero_savings_warns():
    report = validate_optimization_impact(
        _artifact("miss", saved_ms=5.0, remote_bytes=0.0)
    )
    assert report.overall_status == "warn"
    ev = report.optimization_evidence[0]
    assert "miss" in ev.explanation.lower()
    assert "savings" in ev.explanation.lower() or "saved" in ev.explanation.lower()


def test_full_local_hit_evidence_fields():
    report = validate_optimization_impact(_artifact("local_hit", saved_ms=10.0))
    ev = report.optimization_evidence[0]
    assert isinstance(ev, OptimizationEvidence)
    assert ev.optimization_name == "prefix_cache"
    assert ev.decision_name == "local_hit"
    assert isinstance(ev.affected_metrics, list)
    assert isinstance(ev.tradeoff_metrics, list)
    assert ev.evidence_status == "pass"
    assert ev.explanation
    assert ev.truth_boundary


def test_metric_delta_fields():
    report = validate_optimization_impact(_artifact("local_hit", saved_ms=10.0))
    ev = report.optimization_evidence[0]
    ttft = next(m for m in ev.affected_metrics if m.metric_name == "ttft_ms")
    assert isinstance(ttft, OptimizationMetricDelta)
    assert ttft.metric_name == "ttft_ms"
    assert ttft.unit == "ms"
    assert ttft.baseline_value == pytest.approx(_BASELINE_TTFT)
    assert ttft.optimized_value == pytest.approx(_BASELINE_TTFT - 10.0)
    assert ttft.delta_value == pytest.approx(-10.0)
    assert ttft.delta_pct < 0
    assert ttft.direction == "improvement"


def test_local_hit_no_transfer_tradeoff():
    report = validate_optimization_impact(_artifact("local_hit", saved_ms=10.0))
    ev = report.optimization_evidence[0]
    assert not ev.tradeoff_metrics


def test_remote_hit_evidence_status_pass_when_correct():
    remote_bytes = 2.0 * 1024 * 1024
    report = validate_optimization_impact(
        _artifact("remote_hit", saved_ms=10.0, remote_bytes=remote_bytes)
    )
    ev = report.optimization_evidence[0]
    assert ev.evidence_status == "pass"


def test_markdown_contains_truth_boundary():
    report = validate_optimization_impact(_artifact("local_hit", saved_ms=10.0))
    md = report.to_markdown()
    assert _TB_CACHE in md
    assert _TB_REPORT in md


def test_markdown_contains_artifact_and_model():
    report = validate_optimization_impact(_artifact("local_hit"))
    md = report.to_markdown()
    assert "llm_plan_test" in md
    assert "llama3_8b" in md


def test_missing_artifact_name_does_not_crash():
    artifact = _artifact("local_hit")
    del artifact["artifact_name"]
    report = validate_optimization_impact(artifact)
    assert isinstance(report, OptimizationImpactReport)


def test_completely_empty_artifact_does_not_crash():
    report = validate_optimization_impact({})
    assert isinstance(report, OptimizationImpactReport)
    assert report.overall_status == "warn"


def test_remote_hit_markdown_shows_tradeoff():
    remote_bytes = 2.0 * 1024 * 1024
    report = validate_optimization_impact(
        _artifact("remote_hit", saved_ms=10.0, remote_bytes=remote_bytes)
    )
    md = report.to_markdown()
    assert "remote_transfer_bytes" in md
    assert "regression" in md
