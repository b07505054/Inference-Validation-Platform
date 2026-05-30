# Inference Validation Platform

A mini ML systems platform that schedules compiler-produced inference artifacts across heterogeneous accelerator workers, validates correctness and latency budgets, tracks device health, quarantines unhealthy workers, reschedules failed jobs, and emits auditable validation reports.

This project simulates the infrastructure layer between an ML compiler/runtime stack and real hardware execution.

In one sentence:

```text
Validation platform turns runtime traces into correctness, latency, memory, and scheduling reports.
```

## Why This Exists

Modern AI hardware teams need more than model benchmarks. They need infrastructure that can answer:

- Which device should run this compiler artifact?
- Is the selected hardware healthy?
- Did the artifact meet correctness and latency budgets?
- What happens if a device becomes slow, stale, or unhealthy?
- Can the system quarantine bad workers and reschedule automatically?
- Can developers inspect why a scheduling decision happened?

This repo implements a small but complete version of that workflow.

## Connected Repos

This platform is designed to sit above two existing systems projects:

- `ml-graph-compiler-runtime`
  - Produces compiler/runtime artifacts such as lowered graphs, execution plans, static schedules, runtime traces, and cost reports.

- `heterogeneous-inference-runtime`
  - Provides inference benchmarking and runtime analysis across ONNX Runtime, TensorRT, ExecuTorch, CUDA, TFLite, and CPU backends.

Together, the three repos form this pipeline:

```text
ML graph / model
    ↓
Compiler-runtime artifact
    ↓
Inference Validation Platform
    ↓
CPU / CUDA / Metal / Mock accelerator workers
    ↓
Validation result + fleet health + event timeline
```

## Architecture

```text
configs/*.json
    ↓
ArtifactSpec
    ↓
Scheduler
    ↓
DeviceInventory ─── HeartbeatMonitor
    ↓
Worker
    ↓
ValidationPipeline
    ↓
JSON report + Markdown report
```

## Core Features

- Artifact contract for compiler-produced execution plans
- Device inventory for heterogeneous workers
- Worker heartbeat monitoring
- Missed-heartbeat offline detection
- Health-aware scheduling
- Latency-budget validation using p95 latency
- Correctness validation hook
- Worker quarantine on validation failure
- Automatic retry and rescheduling
- Fleet snapshot reporting
- Event timeline for debugging scheduling decisions
- Human-readable Markdown validation report
- FastAPI control plane for worker registration, heartbeat, job submission, and report lookup
- SQLite persistence for jobs, devices, heartbeats, and event timelines
- Firmware version, hardware generation, labels, and resource capacity tracking
- Kubernetes-style scheduling constraints including required labels, preferred labels, resource requests, preferred devices, avoided devices, priority, and preemption metadata

## Control Plane API

Run the API server:

```bash
uvicorn src.ivp.api:app --reload
```

Supported endpoints:

```text
POST /workers/register
POST /workers/heartbeat
POST /jobs/submit
GET  /reports/{job_id}
GET  /devices
```

Example worker registration:

```bash
curl -X POST http://127.0.0.1:8000/workers/register \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "mock-asic-worker-1",
    "backend": "mock_gpu",
    "firmware_version": "fw-mockasic-1.0",
    "hardware_generation": "mock-asic-v1",
    "labels": {
      "region": "local",
      "accelerator": "mock_asic"
    },
    "resource_capacity": {
      "slots": 4
    }
  }'
```

Example constrained job submission:

```json
{
  "job_id": "api-job-k8s-001",
  "max_retries": 1,
  "artifact": {
    "artifact_id": "cv_execution_plan_k8s_demo",
    "artifact_type": "execution_plan",
    "source_repo": "ml-graph-compiler-runtime",
    "artifact_path": "../ml-graph-compiler-runtime/trace/cv_execution_plan_v2.json",
    "required_backends": ["cpu", "mock_gpu"],
    "latency_budget_ms": 5.0,
    "correctness_required": true,
    "scheduling": {
      "required_labels": {
        "accelerator": "mock_asic"
      },
      "preferred_labels": {
        "tier": "validation"
      },
      "resource_requests": {
        "slots": 1
      },
      "preferred_devices": ["mock-asic-worker-1"],
      "avoid_devices": [],
      "allow_preemption": false,
      "priority": 10
    }
  }
}
```

## Demo: Happy Path

Run:

```bash
python3 scripts/run_demo.py
```

Expected behavior:

```text
job submitted
healthy workers report heartbeat
stale CUDA worker is marked offline
scheduler selects mock accelerator worker
validation passes latency budget
JSON and Markdown reports are generated
```

Generated files:

```text
reports/job-001.json
reports/job-001.md
```

## Demo: Failure, Quarantine, And Retry

Run:

```bash
python3 scripts/run_demo.py --artifact configs/retry_artifact.json --prefer-cpu-first
```

This intentionally makes the scheduler try the CPU worker first.

Expected behavior:

```text
attempt 0: cpu-worker-1 selected
attempt 0: CPU p95 latency exceeds budget
cpu-worker-1 quarantined
attempt 1: mock-asic-worker-1 selected
attempt 1: validation passes
```

Example final result:

```text
Result: PASS
Final backend: mock_gpu
Retry count: 1
cpu-worker-1: quarantined
stale-cuda-worker-1: offline
mock-asic-worker-1: healthy
```

## Example Report

The Markdown report records the full validation story:

```text
# Inference Validation Report: job-001

Result: PASS
Artifact: cv_execution_plan_retry_demo
Latency budget: p95 <= 5.0000 ms

Final device: mock-asic-worker-1
Backend: mock_gpu
p95 latency: 3.1765 ms
Retry count: 1

Fleet Snapshot:
cpu-worker-1         quarantined
mock-asic-worker-1   healthy
stale-cuda-worker-1  offline

Event Timeline:
job.submitted
heartbeat.received
heartbeat.missed_threshold
scheduler.selected_device
validation.failed
device.quarantined
scheduler.selected_device
validation.passed
```

## What This Simulates

This project models infrastructure patterns used in production AI hardware and inference systems:

- Hardware-in-the-loop style validation
- Compiler artifact deployment
- Accelerator worker scheduling
- Device health monitoring
- Fleet self-healing
- Latency regression detection
- Runtime validation reporting
- Developer-facing debug traces
- Control-plane APIs for accelerator fleet validation
- Persistent job/device/event state
- Kubernetes-style scheduling concepts for heterogeneous inference workers

It is intentionally small, but the control-plane shape mirrors real systems used by AI infrastructure, accelerator runtime, robotics, and on-device ML teams.

## Project Structure

```text
inference-validation-platform/
├── configs/
│   ├── sample_artifact.json
│   └── retry_artifact.json
├── reports/
│   ├── job-001.json
│   └── job-001.md
├── scripts/
│   └── run_demo.py
└── src/
    └── ivp/
        ├── event_log.py
        ├── api.py
        ├── api_models.py
        ├── heartbeat.py
        ├── inventory.py
        ├── models.py
        ├── report.py
        ├── scheduler.py
        ├── store.py
        ├── validation.py
        └── worker.py
```

## Key Design Ideas

### Artifact Contract

Compiler/runtime outputs are represented as explicit artifact specs:

```json
{
  "artifact_id": "cv_execution_plan_retry_demo",
  "artifact_type": "execution_plan",
  "source_repo": "ml-graph-compiler-runtime",
  "artifact_path": "../ml-graph-compiler-runtime/trace/cv_execution_plan_v2.json",
  "required_backends": ["cpu", "mock_gpu"],
  "latency_budget_ms": 5.0,
  "correctness_required": true
}
```

Artifact specs can also carry scheduler constraints:

```json
{
  "scheduling": {
    "required_labels": {
      "accelerator": "mock_asic"
    },
    "preferred_labels": {
      "tier": "validation"
    },
    "resource_requests": {
      "slots": 1
    },
    "preferred_devices": ["mock-asic-worker-1"],
    "avoid_devices": [],
    "allow_preemption": false,
    "priority": 10
  }
}
```

### Health-Aware Scheduling

The scheduler filters out unhealthy devices and ranks candidates by:

```text
queue depth
historical latency
backend suitability
excluded devices from failed attempts
required labels
preferred labels
resource capacity
preferred / avoided devices
```

### Self-Healing Behavior

If a worker fails validation:

```text
validation failed
    ↓
worker quarantined
    ↓
worker excluded from retry
    ↓
job rescheduled to another healthy worker
```

If a worker misses heartbeats:

```text
heartbeat missed 3 times
    ↓
device marked offline
    ↓
scheduler excludes device
```

## Resume-Ready Summary

Built a heterogeneous inference validation platform that schedules compiler-produced execution artifacts across CPU and mock accelerator workers, validates correctness and p95 latency budgets, tracks worker health via heartbeat, marks stale devices offline, quarantines unstable workers, automatically reschedules failed jobs, and emits JSON/Markdown reports with fleet snapshots and event timelines.

## LLM Runtime Demo Artifacts

The next integration target is an LLM runtime validation demo. This project is responsible for proving that the runtime is correct, stable, and measurable.

Expected outputs:

```text
reports/llm_validation_report.json
reports/slo_report.json
reports/request_timeline.json
reports/scheduler_analysis.json
reports/kv_cache_analysis.json
reports/llm_validation_report.md
```

### `llm_validation_report.json`

```json
{
  "job_id": "llm-runtime-demo-001",
  "passed": true,
  "latency_budget_ms": 20,
  "p95_decode_latency_ms": 15.9,
  "correctness_passed": true,
  "max_logit_diff": 0.0008,
  "peak_memory_mb": 1240
}
```

### `slo_report.json`

```json
{
  "job_id": "llm-runtime-demo-001",
  "passed": true,
  "ttft_p95_ms": 412.8,
  "tpot_p95_ms": 15.9,
  "e2e_p95_ms": 1170.2,
  "queue_wait_p95_ms": 38.1,
  "slo_violation_rate": 0.047,
  "admission_rejection_rate": 0.047,
  "tokens_per_second": 84.7,
  "requests_per_second": 2.8,
  "latency_budget_ms": 20.0
}
```

### `request_timeline.json`

```json
{
  "requests": [
    {
      "request_id": "req-001",
      "arrival_ms": 0,
      "prefill_start_ms": 2,
      "decode_start_ms": 190,
      "finish_ms": 820,
      "status": "completed"
    }
  ]
}
```

### `scheduler_analysis.json`

```json
{
  "avg_queue_wait_ms": 12.4,
  "p95_queue_wait_ms": 38.1,
  "max_active_requests": 8,
  "decode_batch_efficiency": 0.82
}
```

### `kv_cache_analysis.json`

```json
{
  "peak_blocks_used": 812,
  "block_utilization": 0.79,
  "fragmentation_ratio": 0.08,
  "evictions": 0,
  "failed_allocations": 0
}
```

### `llm_validation_report.md`

Human-readable report for interviews and demos. It summarizes correctness, latency, memory, request scheduling, and KV-cache behavior.

## Next Extensions

- Add a real ONNX Runtime worker using `heterogeneous-inference-runtime/scripts/benchmark.py`
- Add SQLite persistence for jobs, devices, and events
- Add a FastAPI control plane for job submission
- Add GitHub Actions for mock hardware-in-the-loop validation
- Add dashboard visualizations for fleet status and validation history
- Add Kubernetes-style worker labels and scheduling constraints
