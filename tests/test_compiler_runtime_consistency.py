"""Tests for compiler/runtime consistency validation.

All tests use plain dict fixtures.  No dependency on heterogeneous-inference-runtime.
"""

import copy

import pytest

from src.ivp.compiler_runtime_consistency import (
    EXPECTED_DECISION_TRACE,
    REPORT_TRUTH_BOUNDARY,
    CompilerRuntimeConsistencyReport,
    validate_runtime_result,
)

# ---------------------------------------------------------------------------
# Base clean fixture
# ---------------------------------------------------------------------------

_CLEAN_RESULT: dict = {
    "function_name": "decode",
    "target_profile_id": "apple-a17pro-mobile",
    "compiler_summary": {
        "function_name": "decode",
        "compiler_primary_backend": "coreml",
        "compiler_decision_source": "target_preferred",
        "compiler_cost_ms": 4.8,
        "compiler_kv_layout": "contiguous",
        "compiler_truth_boundary": "compiler_execution_provider_plan_not_runtime_dispatch",
    },
    "backend_decision": {
        "selected_backend": "coreml",
        "backend_state": "available",
        "override_reason": "",
        "attempted_backends": ["coreml"],
    },
    "scheduling_decision": {
        "execution_policy": "colocated",
        "priority": "conservative",
        "compiler_cost_ms": 4.8,
        "confidence": "low",
        "batch_policy": "single_request",
        "admitted_to_batch": True,
        "reason": "compiler_plan_admitted",
        "truth_boundary": "compiler_cost_estimate_not_measured_latency",
    },
    "memory_decision": {
        "kv_layout_used": "contiguous",
        "estimated_mb_from_compiler": 6.75,
        "admitted": True,
        "rejection_reason": "",
        "allocator_kind": "contiguous",
        "page_budget_estimate": 7,
        "truth_boundary": "static_formula_estimate_not_measured_memory",
    },
    "replay_decision": {
        "replay_requested": True,
        "replay_eligible_from_compiler": True,
        "bucket": "decode_static",
        "capture_attempted": False,
        "captured": False,
        "skipped_reason": "capture_not_implemented",
        "truth_boundary": "static_shape_replay_eligibility_not_cuda_graph_capture",
    },
    "compiler_vs_runtime_backend": "match",
    "runtime_truth_boundary": "runtime_result_not_compiler_plan",
    "decision_trace": list(EXPECTED_DECISION_TRACE),
    "execution_statistics": None,
}


def _clean() -> dict:
    return copy.deepcopy(_CLEAN_RESULT)


def _check(report: CompilerRuntimeConsistencyReport, name: str):
    return next(c for c in report.checks if c.check_name == name)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_clean_result_warns_only_for_missing_execution_statistics():
    report = validate_runtime_result(_clean())
    assert report.overall_status == "warn"
    fail_checks = [c for c in report.checks if c.status == "fail"]
    assert fail_checks == []
    warn_check = _check(report, "execution_statistics_present")
    assert warn_check.status == "warn"
    assert any("execution" in r.lower() for r in report.recommendations)


def test_backend_override_with_reason_passes():
    d = _clean()
    d["backend_decision"]["selected_backend"] = "metal"
    d["backend_decision"]["override_reason"] = "primary_backend_unavailable"
    d["backend_decision"]["attempted_backends"] = ["coreml", "metal"]
    d["compiler_vs_runtime_backend"] = "override"
    report = validate_runtime_result(d)
    backend_fail = [
        c for c in report.checks
        if c.check_name == "backend_match_or_override_documented" and c.status == "fail"
    ]
    assert backend_fail == []


def test_backend_override_without_reason_fails():
    d = _clean()
    d["backend_decision"]["selected_backend"] = "metal"
    d["backend_decision"]["override_reason"] = ""
    d["backend_decision"]["attempted_backends"] = ["coreml", "metal"]
    d["compiler_vs_runtime_backend"] = "override"
    report = validate_runtime_result(d)
    check = _check(report, "backend_match_or_override_documented")
    assert check.status == "fail"
    assert report.overall_status == "fail"


def test_selected_backend_not_in_attempted_chain_fails():
    d = _clean()
    d["backend_decision"]["selected_backend"] = "cuda"
    d["backend_decision"]["attempted_backends"] = ["coreml", "metal", "cpu"]
    d["backend_decision"]["override_reason"] = "primary_backend_unavailable"
    d["compiler_vs_runtime_backend"] = "override"
    report = validate_runtime_result(d)
    check = _check(report, "selected_backend_in_attempted_chain")
    assert check.status == "fail"
    assert report.overall_status == "fail"


def test_memory_layout_mismatch_fails():
    d = _clean()
    d["memory_decision"]["kv_layout_used"] = "paged"
    report = validate_runtime_result(d)
    check = _check(report, "memory_kv_layout_preserved")
    assert check.status == "fail"
    assert check.expected == "contiguous"
    assert check.observed == "paged"
    assert report.overall_status == "fail"


def test_replay_requested_without_skipped_reason_fails():
    d = _clean()
    d["replay_decision"]["replay_requested"] = True
    d["replay_decision"]["capture_attempted"] = False
    d["replay_decision"]["skipped_reason"] = ""
    report = validate_runtime_result(d)
    check = _check(report, "replay_skipped_reason_present_when_requested")
    assert check.status == "fail"
    assert report.overall_status == "fail"


def test_replay_captured_true_fails():
    d = _clean()
    d["replay_decision"]["captured"] = True
    report = validate_runtime_result(d)
    check = _check(report, "replay_captured_false")
    assert check.status == "fail"
    assert report.overall_status == "fail"


def test_low_confidence_not_conservative_fails():
    d = _clean()
    d["scheduling_decision"]["priority"] = "normal"
    report = validate_runtime_result(d)
    check = _check(report, "scheduling_low_confidence_maps_conservative")
    assert check.status == "fail"
    assert check.expected == "conservative"
    assert check.observed == "normal"
    assert report.overall_status == "fail"


def test_missing_truth_boundary_fails():
    d = _clean()
    d["compiler_summary"]["compiler_truth_boundary"] = ""
    report = validate_runtime_result(d)
    check = _check(report, "compiler_truth_boundary_present")
    assert check.status == "fail"
    assert report.overall_status == "fail"


def test_wrong_decision_trace_order_fails():
    d = _clean()
    d["decision_trace"] = [
        "compiler_runtime_adapter",
        "scheduling_decision_evaluator",
        "backend_dispatcher",        # wrong: backend before replay
        "memory_decision_evaluator",
        "replay_decision_evaluator",
        "execution_engine",
    ]
    report = validate_runtime_result(d)
    check = _check(report, "decision_trace_ordered_correctly")
    assert check.status == "fail"
    assert report.overall_status == "fail"


def test_execution_statistics_present_removes_warning():
    d = _clean()
    d["execution_statistics"] = {"actual_latency_ms": 5.2}
    report = validate_runtime_result(d)
    assert report.overall_status == "pass"
    check = _check(report, "execution_statistics_present")
    assert check.status == "pass"


def test_to_dict_contains_structured_delta_and_recommendations():
    d = _clean()
    d["backend_decision"]["selected_backend"] = "metal"
    d["backend_decision"]["override_reason"] = ""
    d["backend_decision"]["attempted_backends"] = ["coreml", "metal"]
    d["compiler_vs_runtime_backend"] = "override"
    report = validate_runtime_result(d)
    result = report.to_dict()
    assert result["report_type"] == "compiler_runtime_consistency_report"
    assert isinstance(result["checks"], list)
    assert all(isinstance(c, dict) for c in result["checks"])
    assert isinstance(result["decision_delta"], dict)
    assert "backend" in result["decision_delta"]
    assert "memory" in result["decision_delta"]
    assert "replay" in result["decision_delta"]
    assert "scheduling" in result["decision_delta"]
    assert isinstance(result["recommendations"], list)
    assert any("override" in r.lower() for r in result["recommendations"])
    assert result["report_truth_boundary"] == REPORT_TRUTH_BOUNDARY


def test_missing_fields_do_not_raise():
    report = validate_runtime_result({})
    assert isinstance(report, CompilerRuntimeConsistencyReport)
    assert report.overall_status == "fail"
    observed_none = [c for c in report.checks if c.observed is None]
    assert len(observed_none) > 0
