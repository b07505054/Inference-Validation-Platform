# Inference Validation Report: api-job-k8s-001

**Result:** PASS
**Artifact:** `cv_execution_plan_k8s_demo`
**Artifact type:** `execution_plan`
**Source repo:** `ml-graph-compiler-runtime`
**Latency budget:** p95 <= 5.0000 ms

## Final Validation Result

| Field | Value |
|---|---:|
| Device | `mock-asic-worker-k8s` |
| Backend | `mock_gpu` |
| Correctness | `True` |
| Avg latency | 2.9929 ms |
| p95 latency | 3.7411 ms |
| p99 latency | 4.3397 ms |
| Passed latency budget | `True` |
| Retry count | 0 |

## Fleet Snapshot

| Device | Backend | Status | Avg latency | Last error | Missed heartbeats |
|---|---|---|---:|---|---:|
| `cpu-worker-k8s` | `cpu` | `healthy` | 1.0000 ms |  | 0 |
| `mock-asic-worker-k8s` | `mock_gpu` | `healthy` | 2.9929 ms |  | 0 |

## Event Timeline

| Event | Device | Message |
|---|---|---|
| `job.submitted` |  | submitted compiler-produced artifact for validation |
| `scheduler.selected_device` | `mock-asic-worker-k8s` | selected mock-asic-worker-k8s for validation attempt 0 |
| `validation.passed` | `mock-asic-worker-k8s` | validation passed correctness and latency budget |
