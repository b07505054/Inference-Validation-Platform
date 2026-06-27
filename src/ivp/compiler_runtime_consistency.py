"""Compiler/runtime consistency validation for RuntimeResult dicts.

Validates that RuntimeResult dicts produced by heterogeneous-inference-runtime
are structurally consistent with the compiler plan fields echoed in CompilerSummary.

Truth boundary: "validation_of_compiler_runtime_consistency_not_measured_performance"

This validator checks structural consistency only.  It does not:
- Measure inference latency, memory, or throughput.
- Claim CUDA graph capture unless replay_decision.captured is True.
- Override truth boundaries set by the compiler or runtime layers.
"""

from __future__ import annotations

from dataclasses import dataclass

EXPECTED_DECISION_TRACE: list[str] = [
    "compiler_runtime_adapter",
    "scheduling_decision_evaluator",
    "memory_decision_evaluator",
    "replay_decision_evaluator",
    "backend_dispatcher",
    "execution_engine",
]

REPORT_TRUTH_BOUNDARY: str = (
    "validation_of_compiler_runtime_consistency_not_measured_performance"
)

_TB_BACKEND: str = "compiler_execution_provider_plan_not_runtime_dispatch"
_TB_MEMORY: str = "static_formula_estimate_not_measured_memory"
_TB_REPLAY: str = "static_shape_replay_eligibility_not_cuda_graph_capture"
_TB_SCHEDULING: str = "compiler_cost_estimate_not_measured_latency"
_TB_RESULT: str = "runtime_result_not_compiler_plan"

_RECOMMENDATIONS: dict[str, str] = {
    "backend_match_or_override_documented": (
        "Runtime backend override is undocumented; set runtime_override_reason "
        "before dispatch result is validated."
    ),
    "selected_backend_in_attempted_chain": (
        "Backend decision selected a backend outside the attempted chain; "
        "verify BackendDispatcher fallback ordering."
    ),
    "memory_kv_layout_preserved": (
        "Runtime memory layout diverged from compiler KV layout; verify "
        "MemoryDecisionEvaluator or runtime memory override."
    ),
    "replay_skipped_reason_present_when_requested": (
        "Replay was requested but skipped without a reason; set skipped_reason "
        "or disable replay request."
    ),
    "replay_captured_false": (
        "Runtime claims replay capture, but replay capture is not implemented "
        "in this validation path."
    ),
    "capture_attempted_false": (
        "Runtime claims capture was attempted, but replay capture is not "
        "implemented in this validation path."
    ),
    "scheduling_low_confidence_maps_conservative": (
        "Low-confidence compiler cost should map to conservative scheduling priority."
    ),
    "execution_statistics_present": (
        "No measured execution statistics were provided; report validates "
        "structural consistency, not latency/throughput."
    ),
}


@dataclass
class CheckResult:
    check_name: str
    status: str        # "pass" | "warn" | "fail"
    expected: object
    observed: object
    reason: str
    truth_boundary: str


@dataclass
class CompilerRuntimeConsistencyReport:
    report_type: str
    schema_version: str
    overall_status: str
    target_profile_id: str
    function_name: str
    checks: list[CheckResult]
    truth_boundary_summary: dict[str, str]
    decision_trace: list[str]
    decision_delta: dict[str, object]
    recommendations: list[str]
    report_truth_boundary: str

    def to_dict(self) -> dict:
        return {
            "report_type": self.report_type,
            "schema_version": self.schema_version,
            "overall_status": self.overall_status,
            "target_profile_id": self.target_profile_id,
            "function_name": self.function_name,
            "checks": [
                {
                    "check_name": c.check_name,
                    "status": c.status,
                    "expected": c.expected,
                    "observed": c.observed,
                    "reason": c.reason,
                    "truth_boundary": c.truth_boundary,
                }
                for c in self.checks
            ],
            "truth_boundary_summary": self.truth_boundary_summary,
            "decision_trace": self.decision_trace,
            "decision_delta": self.decision_delta,
            "recommendations": self.recommendations,
            "report_truth_boundary": self.report_truth_boundary,
        }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _pass(name: str, expected: object, observed: object, tb: str) -> CheckResult:
    return CheckResult(
        check_name=name, status="pass",
        expected=expected, observed=observed, reason="", truth_boundary=tb,
    )


def _fail(
    name: str, expected: object, observed: object, reason: str, tb: str
) -> CheckResult:
    return CheckResult(
        check_name=name, status="fail",
        expected=expected, observed=observed, reason=reason, truth_boundary=tb,
    )


def _warn(
    name: str, expected: object, observed: object, reason: str, tb: str
) -> CheckResult:
    return CheckResult(
        check_name=name, status="warn",
        expected=expected, observed=observed, reason=reason, truth_boundary=tb,
    )


# ---------------------------------------------------------------------------
# Main validation function
# ---------------------------------------------------------------------------

def validate_runtime_result(result_dict: dict) -> CompilerRuntimeConsistencyReport:
    """Validate a RuntimeResult dict for compiler/runtime structural consistency.

    Never raises.  Missing fields produce fail CheckResult entries with observed=None.
    """
    checks: list[CheckResult] = []

    # Extract sub-dicts safely.
    cs = result_dict.get("compiler_summary")
    cs = cs if isinstance(cs, dict) else {}
    bd = result_dict.get("backend_decision")
    bd = bd if isinstance(bd, dict) else {}
    md = result_dict.get("memory_decision")
    md = md if isinstance(md, dict) else {}
    rd = result_dict.get("replay_decision")
    rd = rd if isinstance(rd, dict) else {}
    sd = result_dict.get("scheduling_decision")
    sd = sd if isinstance(sd, dict) else {}

    # Top-level fields.
    function_name: str = result_dict.get("function_name") or ""
    target_profile_id: str = result_dict.get("target_profile_id") or ""
    compiler_vs_runtime_backend = result_dict.get("compiler_vs_runtime_backend")
    runtime_truth_boundary = result_dict.get("runtime_truth_boundary")
    decision_trace = result_dict.get("decision_trace")
    if not isinstance(decision_trace, list):
        decision_trace = []
    execution_statistics = result_dict.get("execution_statistics")

    # CompilerSummary fields.
    compiler_primary_backend = cs.get("compiler_primary_backend")
    compiler_kv_layout = cs.get("compiler_kv_layout")
    compiler_cost_ms = cs.get("compiler_cost_ms")
    compiler_truth_boundary: str = cs.get("compiler_truth_boundary") or ""

    # BackendDecision fields.
    selected_backend = bd.get("selected_backend")
    override_reason = bd.get("override_reason")
    attempted_backends = bd.get("attempted_backends")
    if not isinstance(attempted_backends, list):
        attempted_backends = []

    # MemoryDecision fields.
    kv_layout_used = md.get("kv_layout_used")
    estimated_mb = md.get("estimated_mb_from_compiler")
    admitted = md.get("admitted")
    rejection_reason = md.get("rejection_reason")
    memory_truth_boundary: str = md.get("truth_boundary") or ""

    # ReplayDecision fields.
    replay_requested = rd.get("replay_requested")
    capture_attempted = rd.get("capture_attempted")
    captured = rd.get("captured")
    skipped_reason = rd.get("skipped_reason")
    replay_truth_boundary: str = rd.get("truth_boundary") or ""

    # SchedulingDecision fields.
    sched_cost_ms = sd.get("compiler_cost_ms")
    confidence = sd.get("confidence")
    priority = sd.get("priority")
    admitted_to_batch = sd.get("admitted_to_batch")
    sched_truth_boundary: str = sd.get("truth_boundary") or ""

    # -----------------------------------------------------------------------
    # Backend checks
    # -----------------------------------------------------------------------

    # 1. backend_match_or_override_documented
    if selected_backend is None or compiler_primary_backend is None or override_reason is None:
        checks.append(_fail(
            "backend_match_or_override_documented",
            expected="selected_backend, compiler_primary_backend, and override_reason all present",
            observed=None,
            reason="missing required backend fields",
            tb=_TB_BACKEND,
        ))
    elif selected_backend != compiler_primary_backend and override_reason == "":
        checks.append(_fail(
            "backend_match_or_override_documented",
            expected=(
                f"non-empty override_reason when"
                f" selected={selected_backend!r} != primary={compiler_primary_backend!r}"
            ),
            observed=override_reason,
            reason="backend override is undocumented",
            tb=_TB_BACKEND,
        ))
    else:
        checks.append(_pass(
            "backend_match_or_override_documented",
            expected="override documented when selected != primary",
            observed=override_reason,
            tb=_TB_BACKEND,
        ))

    # 2. compiler_vs_runtime_backend_flag_consistent
    if (
        selected_backend is None
        or compiler_primary_backend is None
        or compiler_vs_runtime_backend is None
    ):
        checks.append(_fail(
            "compiler_vs_runtime_backend_flag_consistent",
            expected="compiler_vs_runtime_backend flag present and consistent with selected/primary",
            observed=None,
            reason="missing fields for flag consistency check",
            tb=_TB_BACKEND,
        ))
    else:
        actually_match = selected_backend == compiler_primary_backend
        flag_says_match = compiler_vs_runtime_backend == "match"
        if actually_match != flag_says_match:
            checks.append(_fail(
                "compiler_vs_runtime_backend_flag_consistent",
                expected="match" if actually_match else "override",
                observed=compiler_vs_runtime_backend,
                reason="compiler_vs_runtime_backend flag does not agree with actual selected/primary comparison",
                tb=_TB_BACKEND,
            ))
        else:
            checks.append(_pass(
                "compiler_vs_runtime_backend_flag_consistent",
                expected=compiler_vs_runtime_backend,
                observed=compiler_vs_runtime_backend,
                tb=_TB_BACKEND,
            ))

    # 3. selected_backend_in_attempted_chain
    if selected_backend is None:
        checks.append(_fail(
            "selected_backend_in_attempted_chain",
            expected="selected_backend present and in attempted_backends",
            observed=None,
            reason="selected_backend is missing",
            tb=_TB_BACKEND,
        ))
    elif selected_backend not in attempted_backends:
        checks.append(_fail(
            "selected_backend_in_attempted_chain",
            expected=f"{selected_backend!r} in attempted_backends",
            observed=selected_backend,
            reason="selected backend is not in the attempted chain",
            tb=_TB_BACKEND,
        ))
    else:
        checks.append(_pass(
            "selected_backend_in_attempted_chain",
            expected=f"{selected_backend!r} in attempted_backends",
            observed=selected_backend,
            tb=_TB_BACKEND,
        ))

    # 4. override_reason_absent_when_match
    if selected_backend is None or compiler_primary_backend is None or override_reason is None:
        checks.append(_fail(
            "override_reason_absent_when_match",
            expected="fields present for override_reason absence check",
            observed=None,
            reason="missing required fields",
            tb=_TB_BACKEND,
        ))
    elif selected_backend == compiler_primary_backend and override_reason != "":
        checks.append(_fail(
            "override_reason_absent_when_match",
            expected='""',
            observed=override_reason,
            reason="override_reason must be empty when selected == primary",
            tb=_TB_BACKEND,
        ))
    else:
        checks.append(_pass(
            "override_reason_absent_when_match",
            expected='""' if selected_backend == compiler_primary_backend else "any",
            observed=override_reason,
            tb=_TB_BACKEND,
        ))

    # -----------------------------------------------------------------------
    # Memory checks
    # -----------------------------------------------------------------------

    # 5. memory_kv_layout_preserved
    if kv_layout_used is None or compiler_kv_layout is None:
        checks.append(_fail(
            "memory_kv_layout_preserved",
            expected="kv_layout_used and compiler_kv_layout both present",
            observed=None,
            reason="missing kv layout fields",
            tb=_TB_MEMORY,
        ))
    elif kv_layout_used != compiler_kv_layout:
        checks.append(_fail(
            "memory_kv_layout_preserved",
            expected=compiler_kv_layout,
            observed=kv_layout_used,
            reason="runtime kv_layout_used does not match compiler kv_layout",
            tb=_TB_MEMORY,
        ))
    else:
        checks.append(_pass(
            "memory_kv_layout_preserved",
            expected=compiler_kv_layout,
            observed=kv_layout_used,
            tb=_TB_MEMORY,
        ))

    # 6. memory_estimated_mb_present
    if estimated_mb is None:
        checks.append(_fail(
            "memory_estimated_mb_present",
            expected=">= 0",
            observed=None,
            reason="estimated_mb_from_compiler is missing",
            tb=_TB_MEMORY,
        ))
    elif estimated_mb < 0:
        checks.append(_fail(
            "memory_estimated_mb_present",
            expected=">= 0",
            observed=estimated_mb,
            reason="estimated_mb_from_compiler is negative",
            tb=_TB_MEMORY,
        ))
    else:
        checks.append(_pass(
            "memory_estimated_mb_present",
            expected=">= 0",
            observed=estimated_mb,
            tb=_TB_MEMORY,
        ))

    # 7. memory_admitted_true_on_no_rejection
    if admitted is None or rejection_reason is None:
        checks.append(_fail(
            "memory_admitted_true_on_no_rejection",
            expected="admitted and rejection_reason both present",
            observed=None,
            reason="missing memory admission fields",
            tb=_TB_MEMORY,
        ))
    elif admitted is True and rejection_reason != "":
        checks.append(_fail(
            "memory_admitted_true_on_no_rejection",
            expected='""',
            observed=rejection_reason,
            reason="rejection_reason must be empty when admitted is True",
            tb=_TB_MEMORY,
        ))
    else:
        checks.append(_pass(
            "memory_admitted_true_on_no_rejection",
            expected="rejection_reason empty when admitted",
            observed=rejection_reason,
            tb=_TB_MEMORY,
        ))

    # -----------------------------------------------------------------------
    # Replay checks
    # -----------------------------------------------------------------------

    # 8. replay_captured_false
    if captured is None:
        checks.append(_fail(
            "replay_captured_false",
            expected=False,
            observed=None,
            reason="replay_decision.captured is missing",
            tb=_TB_REPLAY,
        ))
    elif captured is not False:
        checks.append(_fail(
            "replay_captured_false",
            expected=False,
            observed=captured,
            reason="runtime claims replay capture, but capture is not implemented",
            tb=_TB_REPLAY,
        ))
    else:
        checks.append(_pass(
            "replay_captured_false",
            expected=False,
            observed=captured,
            tb=_TB_REPLAY,
        ))

    # 9. capture_attempted_false
    if capture_attempted is None:
        checks.append(_fail(
            "capture_attempted_false",
            expected=False,
            observed=None,
            reason="replay_decision.capture_attempted is missing",
            tb=_TB_REPLAY,
        ))
    elif capture_attempted is not False:
        checks.append(_fail(
            "capture_attempted_false",
            expected=False,
            observed=capture_attempted,
            reason="runtime claims capture was attempted, but capture is not implemented",
            tb=_TB_REPLAY,
        ))
    else:
        checks.append(_pass(
            "capture_attempted_false",
            expected=False,
            observed=capture_attempted,
            tb=_TB_REPLAY,
        ))

    # 10. replay_skipped_reason_present_when_requested
    if replay_requested is None or capture_attempted is None:
        checks.append(_fail(
            "replay_skipped_reason_present_when_requested",
            expected="replay_requested and capture_attempted both present",
            observed=None,
            reason="missing replay fields for skipped_reason check",
            tb=_TB_REPLAY,
        ))
    elif replay_requested is True and capture_attempted is False and not skipped_reason:
        checks.append(_fail(
            "replay_skipped_reason_present_when_requested",
            expected="non-empty skipped_reason when replay_requested and not capture_attempted",
            observed=skipped_reason,
            reason="replay was requested but skipped without a reason",
            tb=_TB_REPLAY,
        ))
    else:
        checks.append(_pass(
            "replay_skipped_reason_present_when_requested",
            expected="skipped_reason present when needed",
            observed=skipped_reason,
            tb=_TB_REPLAY,
        ))

    # -----------------------------------------------------------------------
    # Scheduling checks
    # -----------------------------------------------------------------------

    # 11. scheduling_cost_preserved
    if sched_cost_ms is None or compiler_cost_ms is None:
        checks.append(_fail(
            "scheduling_cost_preserved",
            expected="scheduling_decision.compiler_cost_ms == compiler_summary.compiler_cost_ms",
            observed=None,
            reason="missing cost_ms fields",
            tb=_TB_SCHEDULING,
        ))
    elif sched_cost_ms != compiler_cost_ms:
        checks.append(_fail(
            "scheduling_cost_preserved",
            expected=compiler_cost_ms,
            observed=sched_cost_ms,
            reason="scheduling cost diverged from compiler summary cost",
            tb=_TB_SCHEDULING,
        ))
    else:
        checks.append(_pass(
            "scheduling_cost_preserved",
            expected=compiler_cost_ms,
            observed=sched_cost_ms,
            tb=_TB_SCHEDULING,
        ))

    # 12. scheduling_low_confidence_maps_conservative
    if confidence is None or priority is None:
        checks.append(_fail(
            "scheduling_low_confidence_maps_conservative",
            expected="confidence and priority both present",
            observed=None,
            reason="missing confidence or priority fields",
            tb=_TB_SCHEDULING,
        ))
    elif confidence == "low" and priority != "conservative":
        checks.append(_fail(
            "scheduling_low_confidence_maps_conservative",
            expected="conservative",
            observed=priority,
            reason="low-confidence compiler cost must map to conservative scheduling priority",
            tb=_TB_SCHEDULING,
        ))
    else:
        checks.append(_pass(
            "scheduling_low_confidence_maps_conservative",
            expected="conservative when confidence==low",
            observed=priority,
            tb=_TB_SCHEDULING,
        ))

    # 13. scheduling_admitted_to_batch_true
    if admitted_to_batch is None:
        checks.append(_fail(
            "scheduling_admitted_to_batch_true",
            expected=True,
            observed=None,
            reason="admitted_to_batch is missing",
            tb=_TB_SCHEDULING,
        ))
    elif admitted_to_batch is not True:
        checks.append(_fail(
            "scheduling_admitted_to_batch_true",
            expected=True,
            observed=admitted_to_batch,
            reason="admitted_to_batch must be True on current deterministic path",
            tb=_TB_SCHEDULING,
        ))
    else:
        checks.append(_pass(
            "scheduling_admitted_to_batch_true",
            expected=True,
            observed=admitted_to_batch,
            tb=_TB_SCHEDULING,
        ))

    # 14. scheduling_truth_boundary_present
    _expected_sched_tb = "compiler_cost_estimate_not_measured_latency"
    if sched_truth_boundary != _expected_sched_tb:
        checks.append(_fail(
            "scheduling_truth_boundary_present",
            expected=_expected_sched_tb,
            observed=sched_truth_boundary or None,
            reason="scheduling truth boundary missing or incorrect",
            tb=_TB_SCHEDULING,
        ))
    else:
        checks.append(_pass(
            "scheduling_truth_boundary_present",
            expected=_expected_sched_tb,
            observed=sched_truth_boundary,
            tb=_TB_SCHEDULING,
        ))

    # -----------------------------------------------------------------------
    # Truth boundary checks
    # -----------------------------------------------------------------------

    # 15. compiler_truth_boundary_present
    if not compiler_truth_boundary:
        checks.append(_fail(
            "compiler_truth_boundary_present",
            expected="non-empty compiler_summary.compiler_truth_boundary",
            observed=compiler_truth_boundary or None,
            reason="compiler_summary.compiler_truth_boundary is missing or empty",
            tb=_TB_RESULT,
        ))
    else:
        checks.append(_pass(
            "compiler_truth_boundary_present",
            expected="non-empty",
            observed=compiler_truth_boundary,
            tb=_TB_RESULT,
        ))

    # 16. memory_truth_boundary_present
    if not memory_truth_boundary:
        checks.append(_fail(
            "memory_truth_boundary_present",
            expected="non-empty memory_decision.truth_boundary",
            observed=memory_truth_boundary or None,
            reason="memory_decision.truth_boundary is missing or empty",
            tb=_TB_RESULT,
        ))
    else:
        checks.append(_pass(
            "memory_truth_boundary_present",
            expected="non-empty",
            observed=memory_truth_boundary,
            tb=_TB_RESULT,
        ))

    # 17. replay_truth_boundary_present
    if not replay_truth_boundary:
        checks.append(_fail(
            "replay_truth_boundary_present",
            expected="non-empty replay_decision.truth_boundary",
            observed=replay_truth_boundary or None,
            reason="replay_decision.truth_boundary is missing or empty",
            tb=_TB_RESULT,
        ))
    else:
        checks.append(_pass(
            "replay_truth_boundary_present",
            expected="non-empty",
            observed=replay_truth_boundary,
            tb=_TB_RESULT,
        ))

    # 18. runtime_result_truth_boundary_correct
    _expected_result_tb = "runtime_result_not_compiler_plan"
    if runtime_truth_boundary != _expected_result_tb:
        checks.append(_fail(
            "runtime_result_truth_boundary_correct",
            expected=_expected_result_tb,
            observed=runtime_truth_boundary,
            reason="runtime_truth_boundary is missing or incorrect",
            tb=_TB_RESULT,
        ))
    else:
        checks.append(_pass(
            "runtime_result_truth_boundary_correct",
            expected=_expected_result_tb,
            observed=runtime_truth_boundary,
            tb=_TB_RESULT,
        ))

    # -----------------------------------------------------------------------
    # Decision trace check
    # -----------------------------------------------------------------------

    # 19. decision_trace_ordered_correctly
    if decision_trace != EXPECTED_DECISION_TRACE:
        checks.append(_fail(
            "decision_trace_ordered_correctly",
            expected=list(EXPECTED_DECISION_TRACE),
            observed=list(decision_trace),
            reason="decision_trace does not match expected pipeline order",
            tb=REPORT_TRUTH_BOUNDARY,
        ))
    else:
        checks.append(_pass(
            "decision_trace_ordered_correctly",
            expected=list(EXPECTED_DECISION_TRACE),
            observed=list(decision_trace),
            tb=REPORT_TRUTH_BOUNDARY,
        ))

    # -----------------------------------------------------------------------
    # Execution statistics check
    # -----------------------------------------------------------------------

    # 20. execution_statistics_present
    if execution_statistics is None:
        checks.append(_warn(
            "execution_statistics_present",
            expected="execution_statistics dict present",
            observed=None,
            reason="no_measured_execution_statistics",
            tb=REPORT_TRUTH_BOUNDARY,
        ))
    else:
        checks.append(_pass(
            "execution_statistics_present",
            expected="execution_statistics dict present",
            observed=type(execution_statistics).__name__,
            tb=REPORT_TRUTH_BOUNDARY,
        ))

    # -----------------------------------------------------------------------
    # Assemble report
    # -----------------------------------------------------------------------

    if any(c.status == "fail" for c in checks):
        overall_status = "fail"
    elif any(c.status == "warn" for c in checks):
        overall_status = "warn"
    else:
        overall_status = "pass"

    recommendations: list[str] = []
    seen_recs: set[str] = set()
    for check in checks:
        if check.status in {"fail", "warn"}:
            rec = _RECOMMENDATIONS.get(check.check_name)
            if rec and rec not in seen_recs:
                recommendations.append(rec)
                seen_recs.add(rec)

    truth_boundary_summary: dict[str, str] = {
        "compiler_plan": compiler_truth_boundary,
        "memory_estimate": memory_truth_boundary,
        "replay_eligibility": replay_truth_boundary,
        "scheduling_estimate": sched_truth_boundary,
        "runtime_result": runtime_truth_boundary or "",
        "this_report": REPORT_TRUTH_BOUNDARY,
    }

    decision_delta: dict[str, object] = {
        "backend": {
            "compiler_primary_backend": compiler_primary_backend,
            "runtime_selected_backend": selected_backend,
            "match": (
                selected_backend == compiler_primary_backend
                if selected_backend is not None and compiler_primary_backend is not None
                else None
            ),
            "override_reason": override_reason,
        },
        "memory": {
            "compiler_kv_layout": compiler_kv_layout,
            "runtime_kv_layout_used": kv_layout_used,
            "match": (
                kv_layout_used == compiler_kv_layout
                if kv_layout_used is not None and compiler_kv_layout is not None
                else None
            ),
        },
        "replay": {
            "runtime_replay_requested": replay_requested,
            "runtime_capture_attempted": capture_attempted,
            "runtime_captured": captured,
            "skipped_reason": skipped_reason,
        },
        "scheduling": {
            "compiler_cost_ms": compiler_cost_ms,
            "runtime_compiler_cost_ms": sched_cost_ms,
            "confidence": confidence,
            "priority": priority,
        },
    }

    return CompilerRuntimeConsistencyReport(
        report_type="compiler_runtime_consistency_report",
        schema_version="1.0",
        overall_status=overall_status,
        target_profile_id=target_profile_id,
        function_name=function_name,
        checks=checks,
        truth_boundary_summary=truth_boundary_summary,
        decision_trace=list(decision_trace),
        decision_delta=decision_delta,
        recommendations=recommendations,
        report_truth_boundary=REPORT_TRUTH_BOUNDARY,
    )
