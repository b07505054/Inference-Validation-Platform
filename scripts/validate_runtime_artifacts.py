import argparse
import json
import math
from collections import Counter
from pathlib import Path


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_optional_json(path: Path, fallback):
    if not path.exists():
        return fallback
    return load_json(path)


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def percentile(values, p):
    if not values:
        return 0.0
    values = sorted(values)
    rank = math.ceil((p / 100.0) * len(values)) - 1
    rank = max(0, min(rank, len(values) - 1))
    return values[rank]


def event_times(serving_trace, event_name):
    return [
        event["time_ms"]
        for event in serving_trace.get("events", [])
        if event.get("event") == event_name
    ]


def build_request_timeline(serving_trace):
    per_request = {}

    for event in serving_trace.get("events", []):
        request_id = event.get("request_id")
        if not request_id:
            continue

        row = per_request.setdefault(
            request_id,
            {
                "request_id": request_id,
                "arrival_ms": None,
                "prefill_start_ms": None,
                "decode_start_ms": None,
                "finish_ms": None,
                "status": "running",
                "tokens_generated": 0,
                "queue_wait_ms": 0.0,
            },
        )

        name = event.get("event")
        if name == "request_admitted":
            row["arrival_ms"] = event["time_ms"]
            row["queue_wait_ms"] = event.get("queue_wait_ms", 0.0)
        elif name == "request_rejected":
            row["finish_ms"] = event["time_ms"]
            row["status"] = "rejected"
        elif name == "prefill_start":
            row["prefill_start_ms"] = event["time_ms"]
        elif name == "decode_step" and row["decode_start_ms"] is None:
            row["decode_start_ms"] = event["time_ms"]
        elif name == "tokens_generated":
            row["tokens_generated"] = event.get("tokens_generated", 0)
            row["finish_ms"] = event["time_ms"]
            row["status"] = "completed"

    requests = list(per_request.values())
    requests.sort(key=lambda row: row["request_id"])
    return requests


def build_scheduler_analysis(scheduler_trace, serving_trace):
    decode_steps = [
        step
        for step in scheduler_trace.get("steps", [])
        if step.get("event") == "decode_batch"
    ]
    batch_sizes = [step.get("batch_size", 1) for step in decode_steps]
    queue_waits = [
        event.get("queue_wait_ms", 0.0)
        for event in serving_trace.get("events", [])
        if event.get("event") == "request_admitted"
    ]
    active_counts = [
        len(step.get("active_requests", []))
        for step in decode_steps
    ]

    return {
        "source": "heterogeneous-inference-runtime/scheduler_trace.json",
        "policy": scheduler_trace.get("policy"),
        "decode_batch_events": len(decode_steps),
        "avg_decode_batch_size": round(sum(batch_sizes) / len(batch_sizes), 4) if batch_sizes else 0.0,
        "max_active_requests": max(active_counts) if active_counts else 0,
        "avg_queue_wait_ms": round(sum(queue_waits) / len(queue_waits), 4) if queue_waits else 0.0,
        "p95_queue_wait_ms": round(percentile(queue_waits, 95), 4),
        "decode_batch_efficiency": round(
            (sum(batch_sizes) / len(batch_sizes)) / scheduler_trace.get("max_decode_batch_size", 1),
            4,
        ) if batch_sizes else 0.0,
    }


def build_kv_cache_analysis(kv_cache_trace):
    total_blocks = kv_cache_trace.get("total_blocks", 0)
    peak_blocks = kv_cache_trace.get("peak_allocated_blocks", 0)
    requests = kv_cache_trace.get("requests", [])
    allocated_per_request = [
        len(request.get("allocated_blocks", []))
        for request in requests
    ]

    page_lifecycle = kv_cache_trace.get("page_lifecycle", {})
    candidate_page_lifecycle = kv_cache_trace.get("candidate_page_lifecycle", {})
    inflight_page_lifecycle = candidate_page_lifecycle.get(
        "inflight_paged_kv_continuous_batching",
        {},
    )

    return {
        "source": "heterogeneous-inference-runtime/kv_cache_trace.json",
        "total_blocks": total_blocks,
        "peak_blocks_used": peak_blocks,
        "block_utilization": round(peak_blocks / total_blocks, 4) if total_blocks else 0.0,
        "fragmentation_ratio": kv_cache_trace.get("fragmentation_ratio", 0.0),
        "peak_kv_cache_mb": kv_cache_trace.get("peak_kv_cache_mb", 0.0),
        "avg_blocks_per_request": round(
            sum(allocated_per_request) / len(allocated_per_request),
            4,
        ) if allocated_per_request else 0.0,
        "max_blocks_per_request": max(allocated_per_request) if allocated_per_request else 0,
        "failed_allocations": 0,
        "evictions": 0,
        "page_lifecycle": page_lifecycle,
        "candidate_page_lifecycle": candidate_page_lifecycle,
        "inflight_page_leak_count": inflight_page_lifecycle.get("page_leak_count"),
        "inflight_pages_allocated": inflight_page_lifecycle.get("allocated_pages"),
        "inflight_pages_freed": inflight_page_lifecycle.get("freed_pages"),
    }


def build_backend_validation(backend_trace):
    placements = backend_trace.get("placements", [])
    backend_counts = Counter(item.get("backend", "unknown") for item in placements)
    op_counts = Counter(item.get("op", "unknown") for item in placements)
    latencies = [item.get("latency_ms", 0.0) for item in placements]

    return {
        "source": "heterogeneous-inference-runtime/backend_trace.json",
        "placement_count": len(placements),
        "backend_counts": dict(backend_counts),
        "op_counts": dict(op_counts),
        "avg_placement_latency_ms": round(sum(latencies) / len(latencies), 4) if latencies else 0.0,
        "p95_placement_latency_ms": round(percentile(latencies, 95), 4),
        "heterogeneous_execution_detected": len(backend_counts) > 1,
        "summary": backend_trace.get("summary", {}),
    }


def build_runtime_decision_validation(decision_report):
    policies = {
        row.get("policy"): row
        for row in decision_report.get("policies", [])
    }
    baseline = policies.get("fcfs_fixed_batch", {})
    optimized = policies.get("cost_aware_memory_pressure", {})
    page_prefetch = policies.get("cost_aware_memory_pressure_page_prefetch", {})
    improvement = decision_report.get("improvement", {})

    tokens_delta = improvement.get("tokens_per_second_delta", 0.0)
    p95_delta = improvement.get("p95_latency_ms_delta", 0.0)
    batch_eff_delta = improvement.get("decode_batch_efficiency_delta", 0.0)
    selected_policy = decision_report.get("selected_policy")
    pressure_limited = optimized.get("pressure_limited_candidates", 0)

    throughput_improved = tokens_delta > 0
    latency_not_regressed = p95_delta <= 0
    batching_improved = batch_eff_delta >= 0
    optimized_family = {
        "cost_aware_memory_pressure",
        "cost_aware_memory_pressure_page_prefetch",
    }
    selected_optimized = selected_policy in optimized_family
    selected_policy_row = policies.get(selected_policy, optimized)
    pressure_policy_exercised = (
        pressure_limited > 0
        or selected_policy_row.get("pressure_limited_candidates", 0) > 0
        or bool(page_prefetch.get("page_prefetch", {}).get("attempts", 0))
    )

    return {
        "artifact_type": "runtime_decision_validation_report",
        "source": "heterogeneous-inference-runtime/scheduler_decision_report.json",
        "selected_policy": selected_policy,
        "passed": (
            selected_optimized
            and throughput_improved
            and latency_not_regressed
            and batching_improved
        ),
        "baseline_policy": baseline,
        "optimized_policy": optimized,
        "page_prefetch_policy": page_prefetch,
        "improvement": improvement,
        "checks": {
            "selected_optimized": selected_optimized,
            "throughput_improved": throughput_improved,
            "latency_not_regressed": latency_not_regressed,
            "batching_improved": batching_improved,
            "pressure_policy_exercised": pressure_policy_exercised,
        },
        "regression_detected": not latency_not_regressed or not throughput_improved,
    }


def build_inflight_scheduler_validation(scheduler_trace, kv_cache_trace, decision_report):
    candidates = scheduler_trace.get("candidate_traces", {})
    inflight = candidates.get("inflight_paged_kv_continuous_batching", {})
    lifecycle = inflight.get("lifecycle", {})
    page_lifecycle = (
        kv_cache_trace.get("candidate_page_lifecycle", {})
        .get("inflight_paged_kv_continuous_batching", {})
    )
    steps = inflight.get("steps", [])
    gate = decision_report.get("inflight_paged_kv_candidate", {}) if decision_report else {}
    selected_policy = decision_report.get("selected_policy") if decision_report else None
    invariants = lifecycle.get("invariants", {})
    config = lifecycle.get("config", {})
    hard_limit = config.get("memory_pressure_hard_limit", 1.0)
    request_states = lifecycle.get("request_states", [])

    def invariant_passes(value):
        if isinstance(value, bool):
            return value
        return value == 0

    lifecycle_complete = bool(request_states) and all(
        row.get("state") in {"finished", "rejected"}
        for row in request_states
    )
    hard_limit_behavior = all(
        not step.get("prefill_request_ids")
        for step in steps
        if step.get("memory_pressure_before", 0.0) >= hard_limit
    )
    gate_consistent = (
        (selected_policy == "inflight_paged_kv_continuous_batching")
        == bool(gate.get("passes_gate"))
    )
    page_lifecycle_balanced = (
        page_lifecycle.get("page_leak_count") == 0
        and page_lifecycle.get("allocated_pages") == page_lifecycle.get("freed_pages")
    )
    scheduler_tick_present = any(step.get("event") == "scheduler_tick" for step in steps)
    mixed_or_decode_present = any(
        step.get("selected_action") in {"mixed_step", "decode_batch", "drain_decode"}
        for step in steps
    )
    invariant_checks_pass = bool(invariants) and all(
        invariant_passes(value)
        for value in invariants.values()
    )

    return {
        "artifact_type": "inflight_scheduler_validation_report",
        "source": "heterogeneous-inference-runtime/scheduler_trace.json",
        "passed": (
            bool(inflight)
            and scheduler_tick_present
            and mixed_or_decode_present
            and lifecycle_complete
            and invariant_checks_pass
            and page_lifecycle_balanced
            and hard_limit_behavior
            and gate_consistent
        ),
        "policy": "inflight_paged_kv_continuous_batching",
        "positioning": inflight.get("positioning"),
        "selected_policy": selected_policy,
        "gate": gate,
        "lifecycle_invariants": invariants,
        "page_lifecycle": page_lifecycle,
        "checks": {
            "inflight_candidate_trace_exists": bool(inflight),
            "scheduler_tick_present": scheduler_tick_present,
            "mixed_or_decode_present": mixed_or_decode_present,
            "lifecycle_complete": lifecycle_complete,
            "invariant_checks_pass": invariant_checks_pass,
            "page_lifecycle_balanced": page_lifecycle_balanced,
            "hard_limit_forbids_prefill": hard_limit_behavior,
            "policy_gate_selection_consistent": gate_consistent,
        },
        "metrics": {
            "ttft_ms": lifecycle.get("ttft_ms", {}),
            "tpot_ms": lifecycle.get("tpot_ms", {}),
            "pressure_limited_ticks": lifecycle.get("pressure_limited_ticks"),
            "prefill_chunk_count": lifecycle.get("prefill_chunk_count"),
            "avg_decode_batch_size": inflight.get("avg_decode_batch_size"),
            "decode_batch_efficiency": inflight.get("decode_batch_efficiency"),
            "page_hit_rate": page_lifecycle.get("prefetch_hit_rate"),
            "pages_allocated": page_lifecycle.get("allocated_pages"),
            "pages_freed": page_lifecycle.get("freed_pages"),
        },
    }


def build_serving_framework_validation(serving_framework_report):
    if not serving_framework_report:
        return None

    comparisons = serving_framework_report.get("comparisons", [])
    styles = {row.get("framework_style") for row in comparisons}
    metrics = serving_framework_report.get("metrics", {})
    required_styles = {
        "baseline_fcfs",
        "vllm_sglang_style",
        "vllm_style_page_prefetch",
        "tensorrt_llm_aligned_local_runtime_policy",
        "triton_server_style",
        "tensorrt_style",
    }
    required_metrics = {
        "ttft_ms",
        "tpot_p95_ms",
        "e2e_p95_ms",
        "throughput_tokens_per_s",
        "peak_kv_cache_mb",
    }
    missing_styles = sorted(required_styles - styles)
    missing_metrics = sorted(
        name for name in required_metrics
        if metrics.get(name) is None
    )

    return {
        "artifact_type": "serving_framework_validation_report",
        "source": "heterogeneous-inference-runtime/serving_framework_report.json",
        "passed": not missing_styles and not missing_metrics,
        "selected_framework_style": serving_framework_report.get("selected_framework_style"),
        "framework_targets": serving_framework_report.get("framework_targets", []),
        "comparison_count": len(comparisons),
        "available_framework_styles": sorted(style for style in styles if style),
        "missing_framework_styles": missing_styles,
        "missing_metrics": missing_metrics,
        "metrics": metrics,
        "improvement": serving_framework_report.get("improvement", {}),
        "selection_reason": serving_framework_report.get("selection_reason"),
    }


def build_page_prefetch_validation(report):
    if not report:
        return None

    gate = report.get("technology_gate", {})
    metric = report.get("metric", {})
    required_gate_fields = ["input", "decision", "metric"]
    missing_gate_fields = [
        field for field in required_gate_fields
        if not gate.get(field)
    ]
    selected = report.get("selected_policy")
    candidate = report.get("candidate_policy")
    fallback = report.get("fallback_policy")
    counters_valid = (
        metric.get("prefetch_attempts", 0) >= 0
        and metric.get("prefetch_hits", 0) >= 0
        and metric.get("prefetch_misses", 0) >= 0
        and 0.0 <= metric.get("prefetch_hit_rate", 0.0) <= 1.0
    )
    no_oom_regression = metric.get("oom_events", 1) == 0
    selected_valid = selected in {candidate, fallback}
    fallback_guard_present = bool(report.get("selection_reason")) and bool(report.get("decision", {}).get("fallback_guard"))

    return {
        "artifact_type": "page_prefetch_validation_report",
        "source": "heterogeneous-inference-runtime/page_prefetch_report.json",
        "passed": (
            report.get("artifact_type") == "vllm_style_page_prefetch_report"
            and gate.get("passes_gate") is True
            and not missing_gate_fields
            and counters_valid
            and no_oom_regression
            and selected_valid
            and fallback_guard_present
        ),
        "integration_level": report.get("integration_level"),
        "technology_gate": gate,
        "missing_gate_fields": missing_gate_fields,
        "selected_policy": selected,
        "candidate_policy": candidate,
        "fallback_policy": fallback,
        "selection_reason": report.get("selection_reason"),
        "metric": metric,
        "checks": {
            "counters_valid": counters_valid,
            "no_oom_regression": no_oom_regression,
            "selected_policy_valid": selected_valid,
            "fallback_guard_present": fallback_guard_present,
        },
        "remaining_work": report.get("remaining_work", []),
    }


def build_distributed_serving_validation(report):
    if not report:
        return None

    gate = report.get("technology_gate", {})
    summaries = report.get("policy_summaries", {})
    required = {"round_robin", "least_queue", "kv_aware"}
    missing = sorted(required - set(summaries))
    kv = summaries.get("kv_aware", {})
    least = summaries.get("least_queue", {})
    selected = report.get("selected_policy")
    selected_valid = selected in {"kv_aware", "least_queue"}
    cache_gate = kv.get("cache_hit_rate", 0.0) >= least.get("cache_hit_rate", 0.0)
    metrics_present = all(
        summaries.get(policy, {}).get(field) is not None
        for policy in required
        for field in ["ttft_p95_ms", "tpot_p95_ms", "throughput_tokens_per_s", "cache_hit_rate"]
    )

    return {
        "artifact_type": "distributed_serving_validation_report",
        "source": "heterogeneous-inference-runtime/distributed_serving_report.json",
        "passed": (
            report.get("artifact_type") == "distributed_serving_report"
            and gate.get("passes_gate") is True
            and not missing
            and selected_valid
            and metrics_present
        ),
        "technology_gate": gate,
        "selected_policy": selected,
        "selection_reason": report.get("selection_reason"),
        "missing_policies": missing,
        "policy_summaries": summaries,
        "checks": {
            "selected_policy_valid": selected_valid,
            "metrics_present": metrics_present,
            "kv_cache_hit_rate_not_worse_than_least_queue": cache_gate,
        },
    }


def build_load_balancing_validation(report):
    if not report:
        return None

    policies = {
        row.get("policy"): row
        for row in report.get("policies", [])
    }
    comparisons = report.get("comparisons", {}).get("kv_aware_vs_least_queue", {})
    required = {"round_robin", "least_queue", "kv_aware"}
    return {
        "artifact_type": "load_balancing_validation_report",
        "source": "heterogeneous-inference-runtime/load_balancing_report.json",
        "passed": (
            report.get("artifact_type") == "load_balancing_report"
            and required.issubset(set(policies))
            and report.get("selected_policy") in {"kv_aware", "least_queue"}
            and comparisons.get("cache_hit_rate_delta") is not None
            and comparisons.get("tpot_p95_delta_ms") is not None
            and comparisons.get("throughput_delta_tokens_per_s") is not None
        ),
        "selected_policy": report.get("selected_policy"),
        "selection_reason": report.get("selection_reason"),
        "policy_count": len(policies),
        "comparisons": comparisons,
        "policies": policies,
    }


def build_fault_tolerance_validation(report, health_report):
    if not report:
        return None

    metrics = report.get("metrics", {})
    health = report.get("worker_health", {})
    events = health_report.get("events", []) if health_report else []
    timeout_seen = any(event.get("event") == "worker_timeout" for event in events)
    failover_seen = any(event.get("event") == "request_failover" for event in events)
    quarantined_worker_seen = any(
        row.get("quarantined")
        for row in (health_report or {}).get("final_worker_state", [])
    )

    return {
        "artifact_type": "fault_tolerance_validation_report",
        "source": "heterogeneous-inference-runtime/fault_tolerance_report.json",
        "passed": (
            report.get("artifact_type") == "fault_tolerance_report"
            and report.get("passed") is True
            and metrics.get("failed_requests", 1) == 0
            and metrics.get("retry_count", 0) > 0
            and metrics.get("failover_count", 0) > 0
            and metrics.get("quarantine_count", 0) > 0
            and timeout_seen
            and failover_seen
            and quarantined_worker_seen
        ),
        "technology_gate": report.get("technology_gate", {}),
        "worker_health": health,
        "metrics": metrics,
        "latency_regression": report.get("latency_regression", {}),
        "checks": {
            "timeout_seen": timeout_seen,
            "failover_seen": failover_seen,
            "quarantined_worker_seen": quarantined_worker_seen,
            "no_request_loss": metrics.get("failed_requests", 1) == 0,
        },
    }


def build_grpc_contract_validation(report):
    if not report:
        return None

    schema = report.get("schema_messages", {})
    required = [
        "GenerateRequest",
        "GenerateResponse",
        "WorkerHealth",
        "RouteDecision",
        "KVShardMetadata",
    ]
    missing = [name for name in required if not schema.get(name)]
    return {
        "artifact_type": "grpc_contract_validation_report",
        "source": "heterogeneous-inference-runtime/grpc_contract_report.json",
        "passed": (
            report.get("artifact_type") == "grpc_contract_report"
            and not missing
            and report.get("service_defined") is True
        ),
        "technology_gate": report.get("technology_gate", {}),
        "schema_messages": schema,
        "missing_messages": missing,
        "service_defined": report.get("service_defined"),
        "stub_generation": report.get("stub_generation"),
        "claim_boundary": report.get("claim_boundary"),
    }


def build_cold_start_validation(cold_start_report):
    if not cold_start_report:
        return None

    artifact_load = cold_start_report.get("artifact_load", {})
    backend_init = cold_start_report.get("backend_initialization", {})
    first_token = cold_start_report.get("first_token_warmup", {})
    steady_state = cold_start_report.get("steady_state", {})
    available_artifacts = [
        name for name, row in artifact_load.items()
        if row.get("available")
    ]
    required_sections = [
        "artifact_load",
        "backend_initialization",
        "first_token_warmup",
        "steady_state",
        "initialization_reduction_plan",
    ]
    missing_sections = [
        name for name in required_sections
        if not cold_start_report.get(name)
    ]
    cold_ttft = first_token.get("cold_ttft_ms")
    warm_ttft = first_token.get("warm_ttft_ms")
    first_request_penalty = first_token.get("first_request_penalty_ms")

    return {
        "artifact_type": "cold_start_validation_report",
        "source": "heterogeneous-inference-runtime/cold_start_report.json",
        "passed": (
            not missing_sections
            and bool(available_artifacts)
            and cold_ttft is not None
            and warm_ttft is not None
            and first_request_penalty is not None
            and cold_ttft >= warm_ttft
        ),
        "available_artifacts": available_artifacts,
        "missing_sections": missing_sections,
        "cold_ttft_ms": cold_ttft,
        "warm_ttft_ms": warm_ttft,
        "first_request_penalty_ms": first_request_penalty,
        "steady_state_tpot_p95_ms": steady_state.get("tpot_p95_ms"),
        "steady_state_throughput_tokens_per_s": steady_state.get("throughput_tokens_per_s"),
        "tensorrt_available": backend_init.get("tensorrt_available"),
        "tensorrt_reason": backend_init.get("tensorrt_reason"),
        "recommendation_count": len(cold_start_report.get("initialization_reduction_plan", [])),
    }




def build_trace_adapter_validation(report, expected_artifact_type):
    if not report:
        return None

    gate = report.get("technology_gate", {})
    runtime_decision = report.get("runtime_decision", {})
    serving_metrics = report.get("serving_metrics", {})
    required_gate_fields = ["input", "decision", "metric"]
    missing_gate_fields = [
        name for name in required_gate_fields
        if not gate.get(name)
    ]
    passed = (
        report.get("artifact_type") == expected_artifact_type
        and gate.get("passes_gate") is True
        and not missing_gate_fields
        and report.get("imported_request_count", 0) > 0
        and bool(runtime_decision)
        and bool(serving_metrics)
        and serving_metrics.get("throughput_tokens_per_s", 0) > 0
    )

    return {
        "artifact_type": f"{expected_artifact_type}_validation",
        "source": f"heterogeneous-inference-runtime/{expected_artifact_type}.json",
        "passed": passed,
        "integration_level": report.get("integration_level"),
        "technology_gate": gate,
        "missing_gate_fields": missing_gate_fields,
        "imported_request_count": report.get("imported_request_count", 0),
        "runtime_decision": runtime_decision,
        "serving_metrics": serving_metrics,
        "remaining_work": report.get("remaining_work", []),
    }


def build_technology_gate_validation(audit):
    if not audit:
        return None

    main_plan = audit.get("main_plan", [])
    remaining = audit.get("remaining_not_in_main_plan", [])
    required_fields = ["technology", "input", "decision", "metric", "status"]
    invalid_main_plan_items = [
        item.get("technology", "unknown")
        for item in main_plan
        if any(not item.get(field) for field in required_fields)
    ]
    remaining_without_next_step = [
        item.get("technology", "unknown")
        for item in remaining
        if not item.get("missing") or not item.get("next_step")
    ]

    return {
        "artifact_type": "technology_gate_validation_report",
        "source": "heterogeneous-inference-runtime/technology_gate_audit.json",
        "passed": not invalid_main_plan_items and not remaining_without_next_step and bool(main_plan),
        "gate_questions": audit.get("gate_questions", []),
        "main_plan_count": len(main_plan),
        "remaining_count": len(remaining),
        "invalid_main_plan_items": invalid_main_plan_items,
        "remaining_without_next_step": remaining_without_next_step,
        "main_plan": main_plan,
        "remaining_not_in_main_plan": remaining,
    }


def build_gpu_pgo_like_validation(report):
    if not report:
        return None

    gate = report.get("technology_gate", {})
    decisions = report.get("shape_decisions", [])
    representative = report.get("representative_decision") or {}
    impact = report.get("serving_impact") or {}
    required_gate_fields = ["input", "decision", "metric"]
    missing_gate_fields = [field for field in required_gate_fields if not gate.get(field)]

    return {
        "artifact_type": "gpu_pgo_like_validation_report",
        "source": "heterogeneous-inference-runtime/results/cuda_transformer/gpu_pgo_like_rmsnorm_report.json",
        "passed": (
            report.get("artifact_type") == "gpu_pgo_like_kernel_selection_report"
            and gate.get("passes_gate") is True
            and not missing_gate_fields
            and bool(decisions)
            and bool(representative.get("selected_kernel"))
            and bool(impact)
        ),
        "technology_gate": gate,
        "missing_gate_fields": missing_gate_fields,
        "shape_decision_count": len(decisions),
        "representative_decision": representative,
        "serving_impact": impact,
        "remaining_work": report.get("remaining_work", []),
    }


def write_markdown_report(path, payload):
    validation = payload["llm_validation_report"]
    slo = payload["slo_report"]
    scheduler = payload["scheduler_analysis"]
    kv = payload["kv_cache_analysis"]
    backend = payload["backend_validation_report"]
    decision = payload.get("runtime_decision_validation_report")
    inflight = payload.get("inflight_scheduler_validation_report")
    framework = payload.get("serving_framework_validation_report")
    cold_start = payload.get("cold_start_validation_report")
    vllm_adapter = payload.get("vllm_trace_adapter_validation_report")
    sglang_adapter = payload.get("sglang_trace_adapter_validation_report")
    technology_gate = payload.get("technology_gate_validation_report")
    gpu_pgo_like = payload.get("gpu_pgo_like_validation_report")
    page_prefetch = payload.get("page_prefetch_validation_report")
    distributed = payload.get("distributed_serving_validation_report")
    load_balancing = payload.get("load_balancing_validation_report")
    fault_tolerance = payload.get("fault_tolerance_validation_report")
    grpc_contract = payload.get("grpc_contract_validation_report")

    lines = [
        f"# Runtime Artifact Validation Report: {validation['job_id']}",
        "",
        f"**Result:** {'PASS' if validation['passed'] else 'FAIL'}",
        f"**Source runtime:** `{payload['source_runtime']}`",
        f"**Model:** `{validation['model']}`",
        "",
        "## Prefill / Decode",
        "",
        f"- Prefill latency: `{validation['prefill_latency_ms']}` ms",
        f"- p95 decode latency: `{validation['p95_decode_latency_ms']}` ms",
        f"- Tokens/sec: `{validation['tokens_per_second']}`",
        "",
        "## SLO",
        "",
        f"- p95 end-to-end latency: `{slo['e2e_p95_ms']}` ms",
        f"- p95 queue wait: `{slo['queue_wait_p95_ms']}` ms",
        f"- OOM events: `{slo['oom_events']}`",
        f"- Admission rejection rate: `{slo['admission_rejection_rate']}`",
        "",
        "## KV Cache",
        "",
        f"- Peak blocks used: `{kv['peak_blocks_used']}` / `{kv['total_blocks']}`",
        f"- Block utilization: `{kv['block_utilization']}`",
        f"- Fragmentation ratio: `{kv['fragmentation_ratio']}`",
        f"- Peak KV cache: `{kv['peak_kv_cache_mb']}` MB",
        "",
        "## Scheduler",
        "",
        f"- Policy: `{scheduler['policy']}`",
        f"- Decode batch events: `{scheduler['decode_batch_events']}`",
        f"- Avg decode batch size: `{scheduler['avg_decode_batch_size']}`",
        f"- p95 queue wait: `{scheduler['p95_queue_wait_ms']}` ms",
        "",
    ]

    if decision:
        improvement = decision.get("improvement", {})
        optimized = decision.get("optimized_policy", {})
        lines.extend([
            "## Runtime Decision Validation",
            "",
            f"- Selected policy: `{decision['selected_policy']}`",
            f"- Decision validation passed: `{decision['passed']}`",
            f"- Tokens/sec delta: `{improvement.get('tokens_per_second_delta')}`",
            f"- p95 latency delta: `{improvement.get('p95_latency_ms_delta')}` ms",
            f"- Decode batch efficiency delta: `{improvement.get('decode_batch_efficiency_delta')}`",
            f"- Pressure-limited candidates: `{optimized.get('pressure_limited_candidates', 0)}`",
            f"- Regression detected: `{decision['regression_detected']}`",
            "",
        ])

    if inflight:
        checks = inflight.get("checks", {})
        metrics = inflight.get("metrics", {})
        lines.extend([
            "## In-Flight Paged KV Scheduler",
            "",
            f"- Validation passed: `{inflight.get('passed')}`",
            f"- Selected policy: `{inflight.get('selected_policy')}`",
            f"- Gate passed: `{inflight.get('gate', {}).get('passes_gate')}`",
            f"- Lifecycle complete: `{checks.get('lifecycle_complete')}`",
            f"- Page lifecycle balanced: `{checks.get('page_lifecycle_balanced')}`",
            f"- Hard-limit behavior: `{checks.get('hard_limit_forbids_prefill')}`",
            f"- TTFT p95: `{metrics.get('ttft_ms', {}).get('p95')}` ms",
            f"- TPOT p95: `{metrics.get('tpot_ms', {}).get('p95')}` ms",
            f"- Page hit rate: `{metrics.get('page_hit_rate')}`",
            "",
        ])

    if framework:
        metrics = framework.get("metrics", {})
        lines.extend([
            "## Serving Framework Targets",
            "",
            f"- Selected style: `{framework['selected_framework_style']}`",
            f"- Validation passed: `{framework['passed']}`",
            f"- Available styles: `{framework['available_framework_styles']}`",
            f"- TTFT: `{metrics.get('ttft_ms')}` ms",
            f"- TPOT p95: `{metrics.get('tpot_p95_ms')}` ms/token",
            f"- Throughput: `{metrics.get('throughput_tokens_per_s')}` tokens/s",
            f"- Peak KV cache: `{metrics.get('peak_kv_cache_mb')}` MB",
            f"- Selection reason: `{framework.get('selection_reason')}`",
            "",
        ])

    if cold_start:
        lines.extend([
            "## Cold Start / Initialization",
            "",
            f"- Validation passed: `{cold_start['passed']}`",
            f"- Cold TTFT: `{cold_start.get('cold_ttft_ms')}` ms",
            f"- Warm TTFT: `{cold_start.get('warm_ttft_ms')}` ms",
            f"- First request penalty: `{cold_start.get('first_request_penalty_ms')}` ms",
            f"- Steady-state TPOT p95: `{cold_start.get('steady_state_tpot_p95_ms')}` ms/token",
            f"- Available artifacts: `{cold_start.get('available_artifacts')}`",
            f"- TensorRT available: `{cold_start.get('tensorrt_available')}`",
            "",
        ])

    if vllm_adapter or sglang_adapter:
        lines.extend([
            "## Framework Trace Adapters",
            "",
        ])
        for label, adapter in [("vLLM", vllm_adapter), ("SGLang", sglang_adapter)]:
            if not adapter:
                continue
            gate = adapter.get("technology_gate", {})
            metrics = adapter.get("serving_metrics", {})
            lines.extend([
                f"- {label} validation passed: `{adapter.get('passed')}`",
                f"  input: `{gate.get('input')}`",
                f"  decision: `{gate.get('decision')}`",
                f"  metric: `{gate.get('metric')}`",
                f"  throughput: `{metrics.get('throughput_tokens_per_s')}` tokens/s",
            ])
        lines.append("")

    if technology_gate:
        lines.extend([
            "## Technology Gate",
            "",
            f"- Validation passed: `{technology_gate.get('passed')}`",
            f"- Main-plan technologies: `{technology_gate.get('main_plan_count')}`",
            f"- Recorded backlog technologies: `{technology_gate.get('remaining_count')}`",
            f"- Invalid main-plan items: `{technology_gate.get('invalid_main_plan_items')}`",
            "",
        ])

    if page_prefetch:
        metric = page_prefetch.get("metric", {})
        gate = page_prefetch.get("technology_gate", {})
        lines.extend([
            "## vLLM-Style Page Prefetch",
            "",
            f"- Validation passed: `{page_prefetch.get('passed')}`",
            f"- Input: `{gate.get('input')}`",
            f"- Decision: `{gate.get('decision')}`",
            f"- Metric: `{gate.get('metric')}`",
            f"- Selected policy: `{page_prefetch.get('selected_policy')}`",
            f"- Hit rate: `{metric.get('prefetch_hit_rate')}`",
            f"- TPOT p95 delta: `{metric.get('tpot_p95_delta_ms')}` ms/token",
            f"- Tokens/sec delta: `{metric.get('tokens_per_second_delta')}`",
            "",
        ])

    if distributed:
        checks = distributed.get("checks", {})
        lines.extend([
            "## Distributed Serving",
            "",
            f"- Validation passed: `{distributed.get('passed')}`",
            f"- Selected policy: `{distributed.get('selected_policy')}`",
            f"- Cache-aware check: `{checks.get('kv_cache_hit_rate_not_worse_than_least_queue')}`",
            f"- Selection reason: `{distributed.get('selection_reason')}`",
            "",
        ])

    if load_balancing:
        comp = load_balancing.get("comparisons", {})
        lines.extend([
            "## Load Balancing",
            "",
            f"- Validation passed: `{load_balancing.get('passed')}`",
            f"- Selected policy: `{load_balancing.get('selected_policy')}`",
            f"- Cache hit delta: `{comp.get('cache_hit_rate_delta')}`",
            f"- TPOT p95 delta: `{comp.get('tpot_p95_delta_ms')}` ms/token",
            f"- Throughput delta: `{comp.get('throughput_delta_tokens_per_s')}` tokens/s",
            "",
        ])

    if fault_tolerance:
        metrics = fault_tolerance.get("metrics", {})
        reg = fault_tolerance.get("latency_regression", {})
        lines.extend([
            "## Worker Health / Failover",
            "",
            f"- Validation passed: `{fault_tolerance.get('passed')}`",
            f"- Retry count: `{metrics.get('retry_count')}`",
            f"- Failover count: `{metrics.get('failover_count')}`",
            f"- Quarantine count: `{metrics.get('quarantine_count')}`",
            f"- Failed requests: `{metrics.get('failed_requests')}`",
            f"- TTFT p95 regression: `{reg.get('ttft_p95_delta_ms')}` ms",
            "",
        ])

    if grpc_contract:
        lines.extend([
            "## Protobuf Contract",
            "",
            f"- Validation passed: `{grpc_contract.get('passed')}`",
            f"- Service defined: `{grpc_contract.get('service_defined')}`",
            f"- Stub generation: `{grpc_contract.get('stub_generation')}`",
            f"- Claim boundary: `{grpc_contract.get('claim_boundary')}`",
            "",
        ])

    if gpu_pgo_like:
        gate = gpu_pgo_like.get("technology_gate", {})
        decision = gpu_pgo_like.get("representative_decision", {})
        impact = gpu_pgo_like.get("serving_impact", {})
        lines.extend([
            "## GPU PGO-like Feedback",
            "",
            f"- Validation passed: `{gpu_pgo_like.get('passed')}`",
            f"- Input: `{gate.get('input')}`",
            f"- Decision: `{gate.get('decision')}`",
            f"- Metric: `{gate.get('metric')}`",
            f"- Selected kernel: `{decision.get('selected_kernel')}`",
            f"- Representative shape: `{decision.get('shape_bucket')}`",
            f"- TPOT delta: `{impact.get('tpot_delta_ms')}` ms/token",
            "",
        ])

    lines.extend([
        "## Backend Placement",
        "",
        f"- Heterogeneous execution detected: `{backend['heterogeneous_execution_detected']}`",
        f"- Backend counts: `{backend['backend_counts']}`",
        f"- Op counts: `{backend['op_counts']}`",
        "",
        "## Validation Positioning",
        "",
        "This report validates runtime artifacts produced by `heterogeneous-inference-runtime` rather than only simulating worker behavior inside the validation platform.",
        "",
    ])

    path.write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--runtime-artifact-dir",
        default="../heterogeneous-inference-runtime/results/llm_runtime_artifacts",
    )
    parser.add_argument(
        "--output-dir",
        default="reports/runtime_artifact_validation",
    )
    parser.add_argument(
        "--gpu-pgo-report",
        default="../heterogeneous-inference-runtime/results/cuda_transformer/gpu_pgo_like_rmsnorm_report.json",
    )
    parser.add_argument("--job-id", default="runtime-artifact-validation-001")
    parser.add_argument("--decode-latency-budget-ms", type=float, default=20.0)
    parser.add_argument("--e2e-latency-budget-ms", type=float, default=1800.0)
    args = parser.parse_args()

    runtime_dir = Path(args.runtime_artifact_dir).resolve()
    output_dir = Path(args.output_dir).resolve()

    prefill_decode = load_json(runtime_dir / "prefill_decode_benchmark.json")
    kv_cache_trace = load_json(runtime_dir / "kv_cache_trace.json")
    scheduler_trace = load_json(runtime_dir / "scheduler_trace.json")
    backend_trace = load_json(runtime_dir / "backend_trace.json")
    runtime_profile = load_json(runtime_dir / "runtime_profile.json")
    serving_trace = load_json(runtime_dir / "serving_trace.json")
    scheduler_decision_report = load_optional_json(
        runtime_dir / "scheduler_decision_report.json",
        {},
    )
    serving_framework_report = load_optional_json(
        runtime_dir / "serving_framework_report.json",
        {},
    )
    cold_start_report = load_optional_json(
        runtime_dir / "cold_start_report.json",
        {},
    )
    vllm_trace_adapter_report = load_optional_json(
        runtime_dir / "vllm_trace_adapter_report.json",
        {},
    )
    sglang_trace_adapter_report = load_optional_json(
        runtime_dir / "sglang_trace_adapter_report.json",
        {},
    )
    technology_gate_audit = load_optional_json(
        runtime_dir / "technology_gate_audit.json",
        {},
    )
    page_prefetch_report = load_optional_json(
        runtime_dir / "page_prefetch_report.json",
        {},
    )
    distributed_serving_report = load_optional_json(
        runtime_dir / "distributed_serving_report.json",
        {},
    )
    load_balancing_report = load_optional_json(
        runtime_dir / "load_balancing_report.json",
        {},
    )
    worker_health_report = load_optional_json(
        runtime_dir / "worker_health_report.json",
        {},
    )
    fault_tolerance_report = load_optional_json(
        runtime_dir / "fault_tolerance_report.json",
        {},
    )
    grpc_contract_report = load_optional_json(
        runtime_dir / "grpc_contract_report.json",
        {},
    )
    gpu_pgo_like_report = load_optional_json(Path(args.gpu_pgo_report).resolve(), {})

    request_timeline = build_request_timeline(serving_trace)
    scheduler_analysis = build_scheduler_analysis(scheduler_trace, serving_trace)
    kv_cache_analysis = build_kv_cache_analysis(kv_cache_trace)
    backend_validation = build_backend_validation(backend_trace)
    runtime_decision_validation = (
        build_runtime_decision_validation(scheduler_decision_report)
        if scheduler_decision_report
        else None
    )
    inflight_scheduler_validation = build_inflight_scheduler_validation(
        scheduler_trace,
        kv_cache_trace,
        scheduler_decision_report,
    )
    serving_framework_validation = build_serving_framework_validation(serving_framework_report)
    cold_start_validation = build_cold_start_validation(cold_start_report)
    vllm_trace_adapter_validation = build_trace_adapter_validation(
        vllm_trace_adapter_report,
        "vllm_trace_adapter_report",
    )
    sglang_trace_adapter_validation = build_trace_adapter_validation(
        sglang_trace_adapter_report,
        "sglang_trace_adapter_report",
    )
    technology_gate_validation = build_technology_gate_validation(technology_gate_audit)
    page_prefetch_validation = build_page_prefetch_validation(page_prefetch_report)
    distributed_serving_validation = build_distributed_serving_validation(distributed_serving_report)
    load_balancing_validation = build_load_balancing_validation(load_balancing_report)
    fault_tolerance_validation = build_fault_tolerance_validation(
        fault_tolerance_report,
        worker_health_report,
    )
    grpc_contract_validation = build_grpc_contract_validation(grpc_contract_report)
    gpu_pgo_like_validation = build_gpu_pgo_like_validation(gpu_pgo_like_report)

    total_requests = runtime_profile.get("total_requests", 0)
    rejected = runtime_profile.get("rejected_requests", 0)
    p95_decode = prefill_decode.get("p95_decode_latency_ms", 0.0)
    p95_e2e = runtime_profile.get("p95_latency_ms", 0.0)
    correctness_passed = runtime_profile.get("completed_requests", 0) == total_requests

    validation_report = {
        "job_id": args.job_id,
        "source_runtime": "heterogeneous-inference-runtime",
        "model": prefill_decode.get("model"),
        "passed": (
            correctness_passed
            and p95_decode <= args.decode_latency_budget_ms
            and p95_e2e <= args.e2e_latency_budget_ms
            and runtime_profile.get("oom_events", 0) == 0
        ),
        "correctness_passed": correctness_passed,
        "decode_latency_budget_ms": args.decode_latency_budget_ms,
        "e2e_latency_budget_ms": args.e2e_latency_budget_ms,
        "prefill_latency_ms": prefill_decode.get("prefill_latency_ms"),
        "avg_decode_latency_ms": prefill_decode.get("avg_decode_latency_ms"),
        "p95_decode_latency_ms": p95_decode,
        "p99_decode_latency_ms": prefill_decode.get("p99_decode_latency_ms"),
        "p95_latency_ms": p95_e2e,
        "p99_latency_ms": runtime_profile.get("p99_latency_ms"),
        "tokens_per_second": prefill_decode.get("tokens_per_second"),
        "peak_memory_mb": runtime_profile.get("peak_memory_mb"),
        "oom_events": runtime_profile.get("oom_events", 0),
    }

    slo_report = {
        "job_id": args.job_id,
        "passed": validation_report["passed"],
        "ttft_p95_ms": prefill_decode.get("prefill_latency_ms"),
        "tpot_p95_ms": p95_decode,
        "e2e_p95_ms": p95_e2e,
        "queue_wait_p95_ms": scheduler_analysis["p95_queue_wait_ms"],
        "slo_violation_rate": 0.0 if validation_report["passed"] else 1.0,
        "admission_rejection_rate": round(rejected / total_requests, 4) if total_requests else 0.0,
        "tokens_per_second": prefill_decode.get("tokens_per_second"),
        "requests_per_second": round(
            runtime_profile.get("completed_requests", 0) / max(event_times(serving_trace, "tokens_generated")[-1] / 1000.0, 1e-9),
            4,
        ) if event_times(serving_trace, "tokens_generated") else 0.0,
        "oom_events": runtime_profile.get("oom_events", 0),
    }

    payload = {
        "job_id": args.job_id,
        "source_runtime": str(runtime_dir),
        "llm_validation_report": validation_report,
        "slo_report": slo_report,
        "scheduler_analysis": scheduler_analysis,
        "kv_cache_analysis": kv_cache_analysis,
        "backend_validation_report": backend_validation,
        "request_timeline": {"requests": request_timeline},
        "runtime_profile": runtime_profile,
    }
    if runtime_decision_validation:
        payload["runtime_decision_validation_report"] = runtime_decision_validation
    if inflight_scheduler_validation:
        payload["inflight_scheduler_validation_report"] = inflight_scheduler_validation
    if serving_framework_validation:
        payload["serving_framework_validation_report"] = serving_framework_validation
    if cold_start_validation:
        payload["cold_start_validation_report"] = cold_start_validation
    if vllm_trace_adapter_validation:
        payload["vllm_trace_adapter_validation_report"] = vllm_trace_adapter_validation
    if sglang_trace_adapter_validation:
        payload["sglang_trace_adapter_validation_report"] = sglang_trace_adapter_validation
    if technology_gate_validation:
        payload["technology_gate_validation_report"] = technology_gate_validation
    if page_prefetch_validation:
        payload["page_prefetch_validation_report"] = page_prefetch_validation
    if distributed_serving_validation:
        payload["distributed_serving_validation_report"] = distributed_serving_validation
    if load_balancing_validation:
        payload["load_balancing_validation_report"] = load_balancing_validation
    if fault_tolerance_validation:
        payload["fault_tolerance_validation_report"] = fault_tolerance_validation
    if grpc_contract_validation:
        payload["grpc_contract_validation_report"] = grpc_contract_validation
    if gpu_pgo_like_validation:
        payload["gpu_pgo_like_validation_report"] = gpu_pgo_like_validation

    files = {
        "runtime_validation_report.json": payload,
        "llm_validation_report.json": validation_report,
        "slo_report.json": slo_report,
        "scheduler_analysis.json": scheduler_analysis,
        "kv_cache_analysis.json": kv_cache_analysis,
        "backend_validation_report.json": backend_validation,
        "request_timeline.json": {"requests": request_timeline},
        "runtime_profile_imported.json": runtime_profile,
    }
    if runtime_decision_validation:
        files["runtime_decision_validation_report.json"] = runtime_decision_validation
    if inflight_scheduler_validation:
        files["inflight_scheduler_validation_report.json"] = inflight_scheduler_validation
    if serving_framework_validation:
        files["serving_framework_validation_report.json"] = serving_framework_validation
    if cold_start_validation:
        files["cold_start_validation_report.json"] = cold_start_validation
    if vllm_trace_adapter_validation:
        files["vllm_trace_adapter_validation_report.json"] = vllm_trace_adapter_validation
    if sglang_trace_adapter_validation:
        files["sglang_trace_adapter_validation_report.json"] = sglang_trace_adapter_validation
    if technology_gate_validation:
        files["technology_gate_validation_report.json"] = technology_gate_validation
    if page_prefetch_validation:
        files["page_prefetch_validation_report.json"] = page_prefetch_validation
    if distributed_serving_validation:
        files["distributed_serving_validation_report.json"] = distributed_serving_validation
    if load_balancing_validation:
        files["load_balancing_validation_report.json"] = load_balancing_validation
    if fault_tolerance_validation:
        files["fault_tolerance_validation_report.json"] = fault_tolerance_validation
    if grpc_contract_validation:
        files["grpc_contract_validation_report.json"] = grpc_contract_validation
    if gpu_pgo_like_validation:
        files["gpu_pgo_like_validation_report.json"] = gpu_pgo_like_validation

    for filename, file_payload in files.items():
        write_json(output_dir / filename, file_payload)

    write_markdown_report(output_dir / "runtime_validation_report.md", payload)
    write_json(
        output_dir / "manifest.json",
        {
            "artifact_set": "runtime_artifact_validation",
            "source_runtime_artifacts": str(runtime_dir),
            "output_dir": str(output_dir),
            "files": sorted([*files.keys(), "runtime_validation_report.md"]),
        },
    )

    print(output_dir)


if __name__ == "__main__":
    main()
