# Inference Validation Report: external-runtime-job-001

**Result:** PASS
**Artifact:** `heterogeneous_runtime_backend_summary`
**Artifact type:** `external_runtime_summary`
**Source repo:** `heterogeneous-inference-runtime`
**Latency budget:** p95 <= 5.0000 ms

## Final Validation Result

| Field | Value |
|---|---:|
| Device | `heterogeneous-runtime-worker-1` |
| Backend | `ONNXRuntime (Optimized FP32 CUDA, CUDAExecutionProvider)` |
| Correctness | `True` |
| Avg latency | 2.9487 ms |
| p95 latency | 3.3046 ms |
| p99 latency | 3.7872 ms |
| Passed latency budget | `True` |
| Retry count | 0 |

## Fleet Snapshot

| Device | Backend | Status | Avg latency | Last error | Missed heartbeats |
|---|---|---|---:|---|---:|
| `heterogeneous-runtime-worker-1` | `external_runtime` | `healthy` | 2.9487 ms |  | 0 |

## Event Timeline

| Event | Device | Message |
|---|---|---|
| `job.submitted` |  | submitted external runtime artifact for validation |
| `heartbeat.received` | `heterogeneous-runtime-worker-1` | external runtime worker reported healthy heartbeat |
| `scheduler.selected_device` | `heterogeneous-runtime-worker-1` | selected heterogeneous-runtime-worker-1 for validation attempt 0 |
| `validation.passed` | `heterogeneous-runtime-worker-1` | validation passed correctness and latency budget |
