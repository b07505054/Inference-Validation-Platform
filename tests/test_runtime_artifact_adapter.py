"""Tests for runtime artifact adapter and optimization impact integration pipeline.

All tests use temp files or fixture dicts. No access to heterogeneous-inference-runtime.
"""

import json
from pathlib import Path

import pytest

from src.ivp.runtime_artifact_adapter import (
    extract_prefix_cache_fields,
    load_artifact_from_path,
)
from src.ivp.optimization_impact_integration import run_optimization_impact_integration

_TB_CACHE = "prefix_cache_simulated_adjusted_plan_not_real_kv_cache_or_network_measurement"
_TB_PLAN = "pd_split_schedule_static_plan_not_live_cluster_execution"


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _plan_artifact(
    hit_type: str = "local_hit",
    saved_prefill_ms: float = 10.0,
    remote_transfer_bytes: float = 0.0,
    remote_transfer_cost_ms: float = 0.0,
    optimized_ttft: float = 21.525,
    tpot: float = 8.5,
    selected_policy: str = "pd_split",
    model_name: str = "llama3_8b",
) -> dict:
    """Minimal distributed_runtime_plan dict matching the PDSplitPlanner dataclass layout."""
    baseline_ttft = optimized_ttft + saved_prefill_ms - remote_transfer_cost_ms
    return {
        "model_name": model_name,
        "target_profile_id": "profile-001",
        "truth_boundary": _TB_PLAN,
        "total_compiler_cost_ms": optimized_ttft + tpot,
        "decision_comparison": {
            "selected_policy": selected_policy,
            "decision_reason": "pd_split selected: lower total cost",
            "slo_ttft_ms": 200.0,
            "slo_tpot_ms": 20.0,
            "goodput_proxy": 0.025,
            "truth_boundary": "goodput_proxy_not_cluster_throughput",
            "colocated": {
                "ttft_ms": baseline_ttft,
                "tpot_ms": tpot,
                "prefill_service_ms": baseline_ttft,
                "decode_service_ms": tpot,
                "total_ms": baseline_ttft + tpot,
                "queue_wait_ms": 0.0,
                "service_time_model_source": "compiler_estimate",
                "truth_boundary": "prefill_decode_cost_model_based_on_compiler_estimates",
            },
            "pd_split": {
                "ttft_ms": optimized_ttft,
                "tpot_ms": tpot,
                "prefill_service_ms": optimized_ttft - 0.325,
                "kv_transfer_ms": 0.125,
                "kv_transfer_bytes": 4194304,
                "handoff_overhead_ms": 0.2,
                "queue_wait_prefill_ms": 0.0,
                "queue_wait_decode_ms": 0.0,
                "decode_service_ms": tpot,
                "total_ms": optimized_ttft + tpot,
                "service_time_model_source": "compiler_estimate",
                "truth_boundary": "kv_transfer_cost_model_not_measured_network",
            },
        },
        "prefix_cache_adjustment": {
            "hit_type": hit_type,
            "hit_tokens": 50,
            "saved_prefill_ms": saved_prefill_ms,
            "remote_transfer_bytes": remote_transfer_bytes,
            "remote_transfer_cost_ms": remote_transfer_cost_ms,
            "adjusted_prefill_service_ms": optimized_ttft - 0.325,
            "truth_boundary": _TB_CACHE,
        },
    }


def _write_artifact(tmp_path: Path, artifact: dict) -> Path:
    p = tmp_path / "distributed_runtime_plan.json"
    p.write_text(json.dumps(artifact), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Required tests
# ---------------------------------------------------------------------------

def test_adapter_extracts_prefix_cache_fields():
    artifact = _plan_artifact("local_hit", saved_prefill_ms=10.0)
    extracted = extract_prefix_cache_fields(artifact)

    assert extracted["model_name"] == "llama3_8b"
    assert extracted["selected_policy"] == "pd_split"
    assert extracted["prefix_cache_hit_type"] == "local_hit"
    assert extracted["prefix_cache_hit_tokens"] == 50
    assert extracted["prefix_cache_saved_prefill_ms"] == pytest.approx(10.0)
    assert extracted["prefix_cache_remote_transfer_bytes"] == pytest.approx(0.0)
    # optimized TTFT comes from decision_comparison.pd_split.ttft_ms
    assert extracted["optimized_ttft_ms"] == pytest.approx(21.525)
    # baseline reconstructed: optimized + saved - remote_cost = 21.525 + 10 - 0 = 31.525
    assert extracted["baseline_ttft_ms"] == pytest.approx(31.525)
    assert extracted["optimized_tpot_ms"] == pytest.approx(8.5)
    assert extracted["baseline_tpot_ms"] == pytest.approx(8.5)
    assert extracted["truth_boundary"] == _TB_CACHE


def test_writes_json_and_markdown_reports(tmp_path):
    artifact_file = _write_artifact(tmp_path, _plan_artifact())
    out_dir = tmp_path / "out"

    json_path, md_path = run_optimization_impact_integration(
        artifact_path=artifact_file,
        output_dir=out_dir,
    )

    assert json_path.exists()
    assert md_path.exists()
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert "overall_status" in data
    assert "optimization_evidence" in data
    assert md_path.read_text(encoding="utf-8").strip()


def test_missing_artifact_emits_warning_report(tmp_path):
    nonexistent = tmp_path / "no_such_file.json"
    json_path, _ = run_optimization_impact_integration(
        artifact_path=nonexistent,
        output_dir=tmp_path / "out",
    )

    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["overall_status"] == "warn"


def test_malformed_artifact_emits_warning_report(tmp_path):
    bad = tmp_path / "distributed_runtime_plan.json"
    bad.write_text("not valid JSON !!!", encoding="utf-8")

    json_path, _ = run_optimization_impact_integration(
        artifact_path=bad,
        output_dir=tmp_path / "out",
    )

    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["overall_status"] == "warn"


def test_integration_does_not_require_sibling_repo(tmp_path):
    """Integration works with an explicit artifact_path — sibling repo not consulted."""
    artifact_file = _write_artifact(tmp_path, _plan_artifact())

    # Explicitly pass artifact_path: no sibling repo lookup.
    json_path, md_path = run_optimization_impact_integration(
        artifact_path=artifact_file,
        output_dir=tmp_path / "reports",
    )

    assert json_path.exists()
    assert md_path.exists()
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert isinstance(data.get("optimization_evidence"), list)


def test_existing_runtime_validation_still_passes():
    """Verify that the existing validate_runtime_artifacts module still imports and works."""
    from scripts.validate_runtime_artifacts import (
        build_statistical_validation,
        extract_policy_sample_distributions,
        build_scheduler_analysis,
        build_kv_cache_analysis,
        build_backend_validation,
        build_runtime_decision_validation,
    )
    assert callable(build_statistical_validation)
    assert callable(extract_policy_sample_distributions)
    assert callable(build_scheduler_analysis)
    assert callable(build_kv_cache_analysis)
    assert callable(build_backend_validation)
    assert callable(build_runtime_decision_validation)


def test_markdown_mentions_prefix_cache_and_delta(tmp_path):
    artifact_file = _write_artifact(tmp_path, _plan_artifact("local_hit", saved_prefill_ms=10.0))
    _, md_path = run_optimization_impact_integration(
        artifact_path=artifact_file,
        output_dir=tmp_path / "out",
    )

    md = md_path.read_text(encoding="utf-8")
    assert "prefix_cache" in md
    assert "ttft_ms" in md
    assert "-10.000" in md     # delta formatted as {value:+.3f}
    assert "improvement" in md


def test_json_report_is_stable(tmp_path):
    """JSON schema has all required top-level and evidence-level keys."""
    artifact_file = _write_artifact(tmp_path, _plan_artifact())
    json_path, _ = run_optimization_impact_integration(
        artifact_path=artifact_file,
        output_dir=tmp_path / "out",
    )

    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert {
        "artifact_name", "model_name", "selected_policy",
        "optimization_evidence", "overall_status", "truth_boundary",
    }.issubset(data.keys())

    ev = data["optimization_evidence"][0]
    assert {
        "optimization_name", "decision_name", "affected_metrics",
        "tradeoff_metrics", "truth_boundary", "evidence_status", "explanation",
    }.issubset(ev.keys())

    metric = ev["affected_metrics"][0]
    assert {
        "metric_name", "baseline_value", "optimized_value",
        "delta_value", "delta_pct", "direction", "unit",
    }.issubset(metric.keys())


def test_deterministic_output(tmp_path):
    artifact_file = _write_artifact(tmp_path, _plan_artifact())

    j1, m1 = run_optimization_impact_integration(
        artifact_path=artifact_file,
        output_dir=tmp_path / "run1",
    )
    j2, m2 = run_optimization_impact_integration(
        artifact_path=artifact_file,
        output_dir=tmp_path / "run2",
    )

    assert json.loads(j1.read_text()) == json.loads(j2.read_text())
    assert m1.read_text() == m2.read_text()


# ---------------------------------------------------------------------------
# Additional adapter coverage
# ---------------------------------------------------------------------------

def test_adapter_artifact_name_uses_model_name():
    artifact = _plan_artifact(model_name="mistral_7b")
    extracted = extract_prefix_cache_fields(artifact)
    assert "mistral_7b" in extracted["artifact_name"]


def test_adapter_explicit_artifact_name():
    extracted = extract_prefix_cache_fields(_plan_artifact(), artifact_name="my_plan")
    assert extracted["artifact_name"] == "my_plan"


def test_adapter_no_prefix_cache_adjustment_defaults_to_miss():
    artifact = _plan_artifact()
    del artifact["prefix_cache_adjustment"]
    extracted = extract_prefix_cache_fields(artifact)
    assert extracted["prefix_cache_hit_type"] == "miss"
    assert extracted["prefix_cache_saved_prefill_ms"] == pytest.approx(0.0)


def test_adapter_colocated_selected_reads_colocated_breakdown():
    artifact = _plan_artifact(selected_policy="colocated", optimized_ttft=35.0)
    # For colocated, optimized TTFT comes from decision_comparison.colocated.ttft_ms
    # which in the fixture equals baseline_ttft (since no adjustment for colocated breakdown)
    extracted = extract_prefix_cache_fields(artifact)
    assert extracted["selected_policy"] == "colocated"
    # Colocated breakdown ttft_ms in our fixture is baseline_ttft = 35 + 10 - 0 = 45
    assert extracted["optimized_ttft_ms"] == pytest.approx(45.0)


def test_adapter_remote_hit_reconstructs_baseline():
    # Remote hit: saved_ms=10, remote_cost=0.0625
    # baseline = optimized + 10 - 0.0625 = optimized + 9.9375
    optimized_ttft = 21.5875
    artifact = _plan_artifact(
        hit_type="remote_hit",
        saved_prefill_ms=10.0,
        remote_transfer_bytes=2 * 1024 * 1024,
        remote_transfer_cost_ms=0.0625,
        optimized_ttft=optimized_ttft,
    )
    extracted = extract_prefix_cache_fields(artifact)
    assert extracted["baseline_ttft_ms"] == pytest.approx(optimized_ttft + 10.0 - 0.0625)


def test_load_artifact_from_path_returns_empty_for_missing(tmp_path):
    result = load_artifact_from_path(tmp_path / "nonexistent.json")
    assert result == {}


def test_load_artifact_from_path_returns_empty_for_bad_json(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{bad json !! }", encoding="utf-8")
    result = load_artifact_from_path(bad)
    assert result == {}


def test_load_artifact_from_path_loads_valid_json(tmp_path):
    good = tmp_path / "good.json"
    good.write_text(json.dumps({"key": "value"}), encoding="utf-8")
    result = load_artifact_from_path(good)
    assert result == {"key": "value"}


def test_integration_uses_artifact_dir_when_no_explicit_path(tmp_path):
    artifact_file = _write_artifact(tmp_path, _plan_artifact())
    # Pass artifact_dir; should find distributed_runtime_plan.json there.
    json_path, _ = run_optimization_impact_integration(
        artifact_dir=tmp_path,
        output_dir=tmp_path / "out",
    )
    assert json_path.exists()
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["overall_status"] == "pass"


def test_integration_output_dir_is_created_if_missing(tmp_path):
    artifact_file = _write_artifact(tmp_path, _plan_artifact())
    deep_out = tmp_path / "a" / "b" / "c"
    assert not deep_out.exists()

    json_path, _ = run_optimization_impact_integration(
        artifact_path=artifact_file,
        output_dir=deep_out,
    )
    assert deep_out.exists()
    assert json_path.exists()
