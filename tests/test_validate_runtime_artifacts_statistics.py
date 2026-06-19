from scripts.validate_runtime_artifacts import (
    build_statistical_validation,
    extract_policy_sample_distributions,
)


def _trace(policy: str, base_time: float) -> dict:
    return {
        "scheduler_policy": policy,
        "events": [
            {
                "time_ms": base_time,
                "event": "request_admitted",
                "request_id": "req-001",
                "queue_wait_ms": 1.0,
            },
            {
                "time_ms": base_time + 10.0,
                "event": "tokens_generated",
                "request_id": "req-001",
                "tokens_generated": 5,
                "decode_latency_ms": 20.0,
            },
            {
                "time_ms": base_time + 10.0,
                "event": "decode_step",
                "request_id": "req-001",
                "paged_attention": {"latency_ms": 0.25},
            },
            {
                "time_ms": base_time + 20.0,
                "event": "request_admitted",
                "request_id": "req-002",
                "queue_wait_ms": 2.0,
            },
            {
                "time_ms": base_time + 35.0,
                "event": "tokens_generated",
                "request_id": "req-002",
                "tokens_generated": 5,
                "decode_latency_ms": 25.0,
            },
            {
                "time_ms": base_time + 35.0,
                "event": "decode_step",
                "request_id": "req-002",
                "paged_attention": {"latency_ms": 0.35},
            },
        ],
    }


def test_extract_policy_samples_from_serving_trace():
    samples = extract_policy_sample_distributions(_trace("candidate", 0.0))

    assert samples["candidate"]["e2e_latency_ms"] == [10.0, 15.0]
    assert samples["candidate"]["queue_wait_ms"] == [1.0, 2.0]
    assert samples["candidate"]["decode_tpot_ms"] == [4.0, 5.0]
    assert samples["candidate"]["paged_attention_latency_ms"] == [0.25, 0.35]


def test_statistical_validation_sample_backed_policy_traces():
    serving_trace = {
        "scheduler_policy": "selected",
        "policy_traces": {
            "fcfs_fixed_batch": _trace("fcfs_fixed_batch", 0.0),
            "selected": _trace("selected", 100.0),
        },
    }
    report = build_statistical_validation(
        serving_trace,
        {"selected_policy": "selected"},
        bootstrap_resamples=100,
    )

    assert report["sample_backed"] is True
    assert report["mann_whitney_available"] is True
    assert "e2e_latency_ms" in report["metrics"]
    assert report["metrics"]["e2e_latency_ms"]["baseline"]["p95_ci"]
    assert report["metrics"]["e2e_latency_ms"]["mann_whitney"]["available"] is True


def test_statistical_validation_aggregate_only_boundary():
    serving_trace = _trace("selected", 0.0)
    report = build_statistical_validation(
        serving_trace,
        {
            "selected_policy": "selected",
            "policies": [
                {"policy": "fcfs_fixed_batch", "p95_latency_ms": 100.0},
                {"policy": "selected", "p95_latency_ms": 80.0},
            ],
        },
    )

    assert report["passed"] is True
    assert report["sample_backed"] is False
    assert report["mann_whitney_available"] is False
    assert report["reason"] == "aggregate_only_metrics"
    assert report["aggregate_policy_summaries"]["fcfs_fixed_batch"]["p95_latency_ms"] == 100.0
