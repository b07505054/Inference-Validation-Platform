# Data Flow

## Control-Plane Validation Flow

1. Input artifact spec

   A job starts from an `ArtifactSpec`, usually loaded from `configs/*.json` or submitted to `POST /jobs/submit`.

   Important fields:

   - `artifact_id`
   - `artifact_type`
   - `source_repo`
   - `artifact_path`
   - `required_backends`
   - `latency_budget_ms`
   - `correctness_required`
   - `scheduling`

2. Worker registration and heartbeat

   Workers are represented by `Device` records. They can be registered through the API or directly in scripts.

   Heartbeats carry:

   - `device_id`
   - `backend`
   - `healthy`
   - `utilization`
   - `last_latency_ms`
   - `error`

   `HeartbeatMonitor.receive()` applies a heartbeat to `DeviceInventory`. Healthy heartbeats reset missed-heartbeat count and can update average latency. Unhealthy heartbeats quarantine the device. `HeartbeatMonitor.miss()` increments missed-heartbeat count and marks a device offline after three misses.

3. Scheduling

   `ValidationPipeline.run()` calls `Scheduler.select_device()`.

   Candidate filters:

   - Device backend must be in `artifact.required_backends`.
   - Device status must be `healthy`.
   - Device must not be in retry exclusions.
   - Device must not be in `artifact.scheduling.avoid_devices`.
   - Required labels must match.
   - Resource requests must fit available capacity.

   Candidate ranking:

   - Preferred device first.
   - Fewer preferred-label misses.
   - Lower queue depth.
   - Lower known `avg_latency_ms`, or lower static backend prior if no measured latency exists.

4. Validation execution

   The selected device is marked busy. The pipeline chooses a worker:

   - `MockWorker` for normal artifact types such as `execution_plan`.
   - `ExternalRuntimeWorker` for `external_runtime_summary` and `external_runtime_benchmark`.

   `MockWorker` returns simulated latency values and `correctness_passed=True`.

   `ExternalRuntimeWorker` either:

   - Reads `artifact.artifact_path` as an existing backend validation summary.
   - Runs `backend_validation_runner.py` in a sibling runtime repo, then reads `results/backend_validation_summary.json`.

   It selects the result with the best p95 latency, falling back to average latency when p95 is absent.

5. Success or failure

   A result passes when:

   - `correctness_passed` is true.
   - `passed_latency_budget` is true.

   On pass:

   - Inventory marks the device healthy.
   - Average latency is updated.
   - Queue depth is decremented.
   - A `validation.passed` event is recorded.

   On fail:

   - Inventory quarantines the device.
   - Device is excluded from the next attempt.
   - `validation.failed` and `device.quarantined` events are recorded.
   - Pipeline retries until `max_retries` is exhausted.

6. Persistence and reporting

   In API mode:

   - `SQLiteStore.create_job()` writes the submitted job.
   - `EventLog` persists events through `SQLiteStore.record_event()`.
   - `SQLiteStore.complete_job()` stores final result JSON and status.
   - Devices and heartbeats are persisted.

   Reports are written to `reports/{job_id}.json` and `reports/{job_id}.md`.

## Runtime Artifact Validation Flow

`scripts/validate_runtime_artifacts.py` validates a directory of runtime evidence from `heterogeneous-inference-runtime`.

Required inputs:

- `prefill_decode_benchmark.json`
- `kv_cache_trace.json`
- `scheduler_trace.json`
- `backend_trace.json`
- `runtime_profile.json`
- `serving_trace.json`

Optional inputs:

- `scheduler_decision_report.json`
- `serving_framework_report.json`
- `cold_start_report.json`
- `vllm_trace_adapter_report.json`
- `sglang_trace_adapter_report.json`
- `technology_gate_audit.json`
- `page_prefetch_report.json`
- `distributed_serving_report.json`
- `load_balancing_report.json`
- `worker_health_report.json`
- `fault_tolerance_report.json`
- `grpc_contract_report.json`
- GPU PGO-like report, defaulting to `../heterogeneous-inference-runtime/results/cuda_transformer/gpu_pgo_like_rmsnorm_report.json`

Processing steps:

- Build request timelines from serving events.
- Compute scheduler queue and decode batch metrics.
- Compute KV-cache utilization, fragmentation, lifecycle, and paged-attention fields.
- Summarize backend placement and heterogeneous execution.
- Validate runtime decision reports when present.
- Validate in-flight paged-KV scheduler evidence.
- Validate serving-framework, cold-start, trace-adapter, technology-gate, page-prefetch, distributed-serving, load-balancing, fault-tolerance, gRPC contract, and GPU PGO-like artifacts when present.
- Build statistical validation from sample-backed policy traces when available, or mark the report as aggregate-only when sample distributions are absent.
- Emit JSON reports, a Markdown report, and a manifest.

Important boundary: this flow consumes runtime evidence. It does not itself generate real runtime measurements unless upstream artifacts already contain them.

## Outputs

Control-plane outputs:

- `reports/{job_id}.json`
- `reports/{job_id}.md`
- SQLite rows in `data/ivp.sqlite3` when using the API.
- Prometheus text metrics at `/metrics`.

Runtime artifact validation outputs:

- `runtime_validation_report.json`
- `runtime_validation_report.md`
- `llm_validation_report.json`
- `slo_report.json`
- `scheduler_analysis.json`
- `kv_cache_analysis.json`
- `backend_validation_report.json`
- `request_timeline.json`
- `runtime_profile_imported.json`
- Optional validation reports for decision, framework, cold start, trace adapters, technology gates, prefetch, distributed serving, load balancing, fault tolerance, gRPC contract, GPU PGO-like reports, and statistical validation.
- `manifest.json`

## Metrics

Control-plane Prometheus metrics are generated from SQLite snapshots:

- `ivp_jobs_current{status=...}`
- `ivp_devices_current{status=...,backend=...}`
- `ivp_heartbeats_total{backend=...,healthy=...}`
- `ivp_events_total{event_type=...}`
- `ivp_validation_results_total{result=...}`

These metrics are implemented and tested, but they represent platform state. They are not live model-serving FPS, TPOT, TTFT, or hardware utilization metrics.

Runtime report metrics include:

- Prefill latency.
- Decode p95/p99 latency.
- End-to-end p95/p99 latency.
- Queue wait p95.
- Admission rejection rate.
- OOM events.
- Tokens per second.
- Requests per second.
- KV-cache block utilization and fragmentation.
- Backend placement counts.
- Statistical p95 confidence intervals and Mann-Whitney tests when sample-backed data exists.

When metrics come from `MockWorker` or `llm_reports.py`, they are simulated/demo values. When metrics come from runtime artifact files, they are only as real as the upstream artifact source.

## Important Data Structures

### `ArtifactSpec`

Describes what to validate and where it came from. The scheduler uses `required_backends` and `scheduling`; the worker uses `artifact_type` and `artifact_path`; reports include the full artifact metadata.

### `Device`

Represents a worker and its scheduling state. Key fields are `backend`, `status`, `queue_depth`, `avg_latency_ms`, labels, and `resource_capacity`.

### `ValidationResult`

Represents the final outcome for one job attempt sequence. It includes latency statistics, correctness result, budget pass/fail, selected device/backend, and retry count.

### `PlatformEvent`

Records audit trail entries for job submission, scheduling decisions, validation results, quarantine, and heartbeat events.

### Runtime trace dictionaries

`scripts/validate_runtime_artifacts.py` mostly operates on dictionaries loaded from JSON. Important expected shapes include:

- Serving events with `event`, `time_ms`, `request_id`, `queue_wait_ms`, `tokens_generated`, and optional `paged_attention`.
- Scheduler trace `steps`, especially `decode_batch` and candidate traces.
- KV-cache trace fields such as `total_blocks`, `peak_allocated_blocks`, request allocations, page lifecycle, and paged-attention execution.
- Runtime profile summary fields such as total/completed/rejected requests, p95/p99 latency, peak memory, and OOM events.

## Assumptions

- Input JSON files are trusted enough to be loaded directly.
- Missing optional runtime reports mean the corresponding output report is skipped.
- Required runtime files must exist; the validator does not synthesize replacements.
- Latency budgets are evaluated using p95 fields where available.
- Existing generated reports in the repository are examples and may not reflect the current state of sibling repos.
