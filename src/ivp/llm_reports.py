import json
import math
from pathlib import Path

from .models import (
    KVCacheAnalysis,
    LLMRequestTimelineEntry,
    LLMValidationReport,
    SLOReport,
    SchedulerAnalysis,
)


def percentile(values: list[float], p: float) -> float:
    if not values:
        raise ValueError("percentile requires at least one value")

    sorted_values = sorted(values)
    rank = math.ceil((p / 100.0) * len(sorted_values)) - 1
    rank = max(0, min(rank, len(sorted_values) - 1))
    return sorted_values[rank]


def demo_request_timeline() -> list[LLMRequestTimelineEntry]:
    return [
        LLMRequestTimelineEntry(
            request_id="req-001",
            arrival_ms=0,
            prefill_start_ms=2,
            decode_start_ms=190,
            finish_ms=820,
            status="completed",
        ),
        LLMRequestTimelineEntry(
            request_id="req-002",
            arrival_ms=6,
            prefill_start_ms=10,
            decode_start_ms=198,
            finish_ms=835,
            status="completed",
        ),
        LLMRequestTimelineEntry(
            request_id="req-003",
            arrival_ms=10,
            prefill_start_ms=16,
            decode_start_ms=205,
            finish_ms=850,
            status="completed",
        ),
        LLMRequestTimelineEntry(
            request_id="req-004",
            arrival_ms=18,
            prefill_start_ms=26,
            decode_start_ms=211,
            finish_ms=862,
            status="completed",
        ),
        LLMRequestTimelineEntry(
            request_id="req-005",
            arrival_ms=24,
            prefill_start_ms=34,
            decode_start_ms=219,
            finish_ms=879,
            status="completed",
        ),
        LLMRequestTimelineEntry(
            request_id="req-006",
            arrival_ms=31,
            prefill_start_ms=43,
            decode_start_ms=227,
            finish_ms=891,
            status="completed",
        ),
        LLMRequestTimelineEntry(
            request_id="req-007",
            arrival_ms=40,
            prefill_start_ms=59.1,
            decode_start_ms=238,
            finish_ms=910,
            status="completed",
        ),
        LLMRequestTimelineEntry(
            request_id="req-008",
            arrival_ms=52,
            prefill_start_ms=90.1,
            decode_start_ms=252,
            finish_ms=928,
            status="completed",
        ),
    ]


def demo_decode_latencies_ms() -> list[float]:
    return [12.4, 12.9, 13.8, 14.2, 14.7, 15.1, 15.4, 15.9]


def build_llm_validation_report(
    job_id: str,
    latency_budget_ms: float,
    decode_latencies_ms: list[float],
) -> LLMValidationReport:
    p95_decode_latency_ms = round(percentile(decode_latencies_ms, 95), 4)
    correctness_passed = True
    max_logit_diff = 0.0008
    peak_memory_mb = 1240

    return LLMValidationReport(
        job_id=job_id,
        passed=correctness_passed and p95_decode_latency_ms <= latency_budget_ms,
        latency_budget_ms=latency_budget_ms,
        p95_decode_latency_ms=p95_decode_latency_ms,
        correctness_passed=correctness_passed,
        max_logit_diff=max_logit_diff,
        peak_memory_mb=peak_memory_mb,
    )


def build_scheduler_analysis(
    requests: list[LLMRequestTimelineEntry],
) -> SchedulerAnalysis:
    queue_waits = [
        req.prefill_start_ms - req.arrival_ms
        for req in requests
    ]

    return SchedulerAnalysis(
        avg_queue_wait_ms=round(sum(queue_waits) / len(queue_waits), 4),
        p95_queue_wait_ms=round(percentile(queue_waits, 95), 4),
        max_active_requests=len([
            req for req in requests
            if req.status == "completed"
        ]),
        decode_batch_efficiency=0.82,
    )


def build_kv_cache_analysis() -> KVCacheAnalysis:
    return KVCacheAnalysis(
        peak_blocks_used=812,
        block_utilization=0.79,
        fragmentation_ratio=0.08,
        evictions=0,
        failed_allocations=0,
    )


def build_slo_report(
    job_id: str,
    latency_budget_ms: float,
    validation: LLMValidationReport,
    scheduler: SchedulerAnalysis,
) -> SLOReport:
    ttft_p95_ms = 412.8
    tpot_p95_ms = validation.p95_decode_latency_ms
    e2e_p95_ms = 1170.2
    slo_violation_rate = 0.047
    admission_rejection_rate = 0.047

    return SLOReport(
        job_id=job_id,
        passed=(
            validation.passed
            and ttft_p95_ms <= 500.0
            and tpot_p95_ms <= latency_budget_ms
            and e2e_p95_ms <= 1200.0
            and slo_violation_rate <= 0.05
        ),
        ttft_p95_ms=ttft_p95_ms,
        tpot_p95_ms=tpot_p95_ms,
        e2e_p95_ms=e2e_p95_ms,
        queue_wait_p95_ms=scheduler.p95_queue_wait_ms,
        slo_violation_rate=slo_violation_rate,
        admission_rejection_rate=admission_rejection_rate,
        tokens_per_second=84.7,
        requests_per_second=2.8,
        latency_budget_ms=latency_budget_ms,
    )


def build_plan_selection_report(job_id: str) -> dict:
    plans = [
        {
            "plan_id": "plan_metal",
            "backend": "Metal",
            "latency_ms": 1.95,
            "p95_latency_ms": 2.21,
            "peak_memory_mb": 986.75,
            "throughput_tokens_per_s": 512.8,
        },
        {
            "plan_id": "plan_cpu",
            "backend": "CPU",
            "latency_ms": 5.1,
            "p95_latency_ms": 5.8,
            "peak_memory_mb": 826.75,
            "throughput_tokens_per_s": 196.1,
        },
        {
            "plan_id": "plan_hybrid",
            "backend": "Hybrid",
            "latency_ms": 2.7,
            "p95_latency_ms": 3.05,
            "peak_memory_mb": 890.75,
            "throughput_tokens_per_s": 370.4,
        },
    ]
    return {
        "artifact_type": "plan_selection_report",
        "job_id": job_id,
        "selected_plan_id": "plan_metal",
        "selection_reason": "lowest p95 latency while staying within memory budget",
        "memory_budget_mb": 8192,
        "plans": plans,
        "regression_detected": False,
    }


def build_memory_validation_report(job_id: str) -> dict:
    return {
        "artifact_type": "memory_validation_report",
        "job_id": job_id,
        "passed": True,
        "peak_memory_mb": 673,
        "memory_budget_mb": 8192,
        "budget_utilization": round(673 / 8192, 4),
        "reuse_events": 1,
        "allocations": 4,
        "frees": 3,
        "issues": [],
    }


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_llm_markdown_report(
    path: Path,
    validation: LLMValidationReport,
    slo: SLOReport,
    scheduler: SchedulerAnalysis,
    kv_cache: KVCacheAnalysis,
    requests: list[LLMRequestTimelineEntry],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    status = "PASS" if validation.passed else "FAIL"

    lines = [
        f"# LLM Runtime Validation Report: {validation.job_id}",
        "",
        f"**Result:** {status}",
        f"**Latency budget:** p95 decode <= {validation.latency_budget_ms:.4f} ms",
        f"**p95 decode latency:** {validation.p95_decode_latency_ms:.4f} ms",
        f"**Correctness passed:** `{validation.correctness_passed}`",
        f"**Max logit diff:** {validation.max_logit_diff:.6f}",
        f"**Peak memory:** {validation.peak_memory_mb:.1f} MB",
        "",
        "## SLO Report",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| SLO passed | `{slo.passed}` |",
        f"| TTFT p95 | {slo.ttft_p95_ms:.4f} ms |",
        f"| TPOT p95 | {slo.tpot_p95_ms:.4f} ms |",
        f"| E2E p95 | {slo.e2e_p95_ms:.4f} ms |",
        f"| Queue wait p95 | {slo.queue_wait_p95_ms:.4f} ms |",
        f"| SLO violation rate | {slo.slo_violation_rate:.4f} |",
        f"| Admission rejection rate | {slo.admission_rejection_rate:.4f} |",
        f"| Tokens/sec | {slo.tokens_per_second:.4f} |",
        f"| Requests/sec | {slo.requests_per_second:.4f} |",
        "",
        "## Scheduler Analysis",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Avg queue wait | {scheduler.avg_queue_wait_ms:.4f} ms |",
        f"| p95 queue wait | {scheduler.p95_queue_wait_ms:.4f} ms |",
        f"| Max active requests | {scheduler.max_active_requests} |",
        f"| Decode batch efficiency | {scheduler.decode_batch_efficiency:.4f} |",
        "",
        "## KV Cache Analysis",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Peak blocks used | {kv_cache.peak_blocks_used} |",
        f"| Block utilization | {kv_cache.block_utilization:.4f} |",
        f"| Fragmentation ratio | {kv_cache.fragmentation_ratio:.4f} |",
        f"| Evictions | {kv_cache.evictions} |",
        f"| Failed allocations | {kv_cache.failed_allocations} |",
        "",
        "## Request Timeline",
        "",
        "| Request | Arrival | Prefill start | Decode start | Finish | Status |",
        "|---|---:|---:|---:|---:|---|",
    ]

    for request in requests:
        lines.append(
            f"| `{request.request_id}` | {request.arrival_ms:.1f} ms | "
            f"{request.prefill_start_ms:.1f} ms | "
            f"{request.decode_start_ms:.1f} ms | "
            f"{request.finish_ms:.1f} ms | `{request.status}` |"
        )

    lines.extend([
        "",
        "## Summary",
        "",
        "Validation platform turns runtime traces into correctness, latency, memory, and scheduling reports.",
        "",
    ])

    path.write_text("\n".join(lines), encoding="utf-8")


def generate_llm_demo_artifacts(
    output_dir: Path,
    job_id: str = "llm-runtime-demo-001",
    latency_budget_ms: float = 20.0,
) -> dict[str, Path]:
    requests = demo_request_timeline()
    decode_latencies = demo_decode_latencies_ms()
    validation = build_llm_validation_report(
        job_id=job_id,
        latency_budget_ms=latency_budget_ms,
        decode_latencies_ms=decode_latencies,
    )
    scheduler = build_scheduler_analysis(requests)
    kv_cache = build_kv_cache_analysis()
    slo = build_slo_report(
        job_id=job_id,
        latency_budget_ms=latency_budget_ms,
        validation=validation,
        scheduler=scheduler,
    )

    paths = {
        "llm_validation_report_json": output_dir / "llm_validation_report.json",
        "slo_report_json": output_dir / "slo_report.json",
        "request_timeline_json": output_dir / "request_timeline.json",
        "scheduler_analysis_json": output_dir / "scheduler_analysis.json",
        "kv_cache_analysis_json": output_dir / "kv_cache_analysis.json",
        "plan_selection_report_json": output_dir / "plan_selection_report.json",
        "memory_validation_report_json": output_dir / "memory_validation_report.json",
        "llm_validation_report_md": output_dir / "llm_validation_report.md",
    }

    write_json(paths["llm_validation_report_json"], validation.model_dump())
    write_json(paths["slo_report_json"], slo.model_dump())
    write_json(
        paths["request_timeline_json"],
        {
            "requests": [
                request.model_dump()
                for request in requests
            ]
        },
    )
    write_json(paths["scheduler_analysis_json"], scheduler.model_dump())
    write_json(paths["kv_cache_analysis_json"], kv_cache.model_dump())
    write_json(paths["plan_selection_report_json"], build_plan_selection_report(job_id))
    write_json(paths["memory_validation_report_json"], build_memory_validation_report(job_id))
    write_llm_markdown_report(
        paths["llm_validation_report_md"],
        validation=validation,
        slo=slo,
        scheduler=scheduler,
        kv_cache=kv_cache,
        requests=requests,
    )

    return paths
