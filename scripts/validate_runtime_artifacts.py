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
    improvement = decision_report.get("improvement", {})

    tokens_delta = improvement.get("tokens_per_second_delta", 0.0)
    p95_delta = improvement.get("p95_latency_ms_delta", 0.0)
    batch_eff_delta = improvement.get("decode_batch_efficiency_delta", 0.0)
    selected_policy = decision_report.get("selected_policy")
    pressure_limited = optimized.get("pressure_limited_candidates", 0)

    throughput_improved = tokens_delta > 0
    latency_not_regressed = p95_delta <= 0
    batching_improved = batch_eff_delta >= 0
    selected_optimized = selected_policy == "cost_aware_memory_pressure"
    pressure_policy_exercised = pressure_limited > 0

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


def build_serving_framework_validation(serving_framework_report):
    if not serving_framework_report:
        return None

    comparisons = serving_framework_report.get("comparisons", [])
    styles = {row.get("framework_style") for row in comparisons}
    metrics = serving_framework_report.get("metrics", {})
    required_styles = {
        "baseline_fcfs",
        "vllm_sglang_style",
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


def write_markdown_report(path, payload):
    validation = payload["llm_validation_report"]
    slo = payload["slo_report"]
    scheduler = payload["scheduler_analysis"]
    kv = payload["kv_cache_analysis"]
    backend = payload["backend_validation_report"]
    decision = payload.get("runtime_decision_validation_report")
    framework = payload.get("serving_framework_validation_report")
    cold_start = payload.get("cold_start_validation_report")

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

    request_timeline = build_request_timeline(serving_trace)
    scheduler_analysis = build_scheduler_analysis(scheduler_trace, serving_trace)
    kv_cache_analysis = build_kv_cache_analysis(kv_cache_trace)
    backend_validation = build_backend_validation(backend_trace)
    runtime_decision_validation = (
        build_runtime_decision_validation(scheduler_decision_report)
        if scheduler_decision_report
        else None
    )
    serving_framework_validation = build_serving_framework_validation(serving_framework_report)
    cold_start_validation = build_cold_start_validation(cold_start_report)

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
    if serving_framework_validation:
        payload["serving_framework_validation_report"] = serving_framework_validation
    if cold_start_validation:
        payload["cold_start_validation_report"] = cold_start_validation

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
    if serving_framework_validation:
        files["serving_framework_validation_report.json"] = serving_framework_validation
    if cold_start_validation:
        files["cold_start_validation_report.json"] = cold_start_validation

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
