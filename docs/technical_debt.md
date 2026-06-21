# Technical Debt

## Likely Runtime Artifact Validator Ordering Bug

`scripts/validate_runtime_artifacts.py` computes `statistical_regression_failed` and then attempts to mutate `validation_report` and `slo_report` before those dictionaries are defined.

Risk:

- A sample-backed statistical regression path may raise an error before reports are written.

Suggested fix:

- Build `validation_report` and `slo_report` before applying the statistical regression override, or defer the override until after both dictionaries exist.
- Add a regression test for the sample-backed failure path.

## Large Script With Many Responsibilities

`scripts/validate_runtime_artifacts.py` handles loading, validation logic, derived metrics, optional artifact checks, report writing, and Markdown formatting in one file.

Risk:

- Harder to review and extend.
- Easy to introduce ordering issues.
- Optional report behavior is difficult to test exhaustively.

Suggested direction:

- Move reusable builders into package modules.
- Keep the script as CLI orchestration.
- Add focused tests for each report builder.

## Mock Correctness Always Passes

`MockWorker.run_validation()` always sets `correctness_passed=True`.

Risk:

- Control-plane demos can imply correctness validation exists for mock execution plans when it is only a placeholder.

Suggested direction:

- Rename or document the field as simulated in mock paths.
- Add a real correctness hook once there is a concrete artifact output to compare.

## Mock Latency Is Random

`MockWorker` uses random jitter without a seed.

Risk:

- Demo results and tests that depend on mock latency can be flaky.
- Generated reports may vary run to run.

Suggested direction:

- Inject a random generator or deterministic latency profile for demos/tests.
- Keep any stochastic mode clearly marked as simulation.

## Scheduler Model Has Unused Fields

`SchedulingConstraints` includes `allow_preemption` and `priority`, but scheduler selection does not use them.

Risk:

- API users may think priority/preemption semantics are implemented.

Suggested direction:

- Either implement priority/preemption behavior or document these as reserved fields.
- Add scheduler tests around all implemented constraints.

## API Uses Module-Level Global State

`src/ivp/api.py` creates global `inventory`, `store`, and `heartbeat_monitor`.

Risk:

- Multi-worker ASGI deployments can diverge in memory.
- Tests need monkeypatch reset helpers.
- Restart behavior depends on SQLite for history but not for reconstructing active inventory at import time.

Suggested direction:

- Introduce an application state factory for tests and deployment.
- Consider loading device state from SQLite on startup if persistence should be authoritative.

## Synchronous API Job Execution

`POST /jobs/submit` runs the validation pipeline inline.

Risk:

- Long external-runtime benchmarks can block request handling.
- Failed or interrupted external processes do not have a durable in-progress lifecycle.

Suggested direction:

- Add queued job states for long-running validation.
- Consider background tasks or a separate worker process.

## Failure Attribution Is Coarse

Validation failure quarantines the selected device, whether the root cause is device health, artifact behavior, missing input, or an external runtime error.

Risk:

- Healthy devices can be quarantined due to invalid artifacts or infrastructure errors.

Suggested direction:

- Distinguish device failure, artifact failure, runtime infrastructure failure, and validation threshold failure.
- Store failure categories in events and reports.

## Missing Tests

Current tests cover:

- Control-plane metrics endpoint rendering.
- Statistical helper functions.
- Statistical artifact extraction and aggregate-only boundaries.

Important missing coverage:

- Scheduler filtering and ranking.
- Required/preferred labels.
- Resource request capacity logic.
- Preferred and avoided devices.
- Inventory heartbeat transitions.
- Retry and quarantine behavior in `ValidationPipeline`.
- ExternalRuntimeWorker summary selection and error handling.
- Report writer output structure.
- API error paths.
- Runtime validator optional report builders.
- The statistical regression failure override path.

## Duplicate or Parallel Logic

There are multiple percentile helpers:

- `src/ivp/statistics.py::percentile`
- `src/ivp/llm_reports.py::percentile`

Risk:

- Behavior can drift between report paths.

Suggested direction:

- Use the shared statistics helper where practical.

## Generated Artifacts Are Checked In

`reports/`, `integration_artifacts/`, and `data/ivp.sqlite3` contain generated or local state.

Risk:

- Stale artifacts can obscure what is source versus output.
- SQLite state can cause confusion if reused across local runs.

Suggested direction:

- Document generated artifacts clearly.
- Consider moving example reports under a fixtures/examples directory.
- Consider ignoring local SQLite state unless it is intentionally part of the demo.

## Unclear Naming Around External Runtime Workers

`ExternalRuntimeWorker` reports `device_id` as the IVP worker but formats `backend` with selected runtime backend, precision, and device from the summary row.

Risk:

- Consumers may confuse IVP scheduling device identity with runtime benchmark device identity.

Suggested direction:

- Add separate fields for IVP worker, runtime backend, runtime precision, and runtime device in future result schemas.

## Minimal Error Recovery Around External Processes

`ExternalRuntimeWorker` runs `backend_validation_runner.py` and raises on nonzero exit.

Risk:

- API caller gets a failure, but there is no structured event/report for external process stdout/stderr except the raised message path.

Suggested direction:

- Capture external benchmark failure as a structured validation result or event.
- Include bounded stdout/stderr in failure reports.

## Security and Trust Boundaries Are Not Defined

Input artifact paths and runtime directories are loaded directly from local JSON/configs.

Risk:

- Fine for local trusted demos, but not safe for untrusted API clients.

Suggested direction:

- Add path allowlists, artifact storage boundaries, and input validation before exposing beyond local development.

## Formatting and Style Nits

`src/ivp/inventory.py` has adjacent method definitions without a blank line between `mark_healthy()` and `apply_heartbeat()`.

Risk:

- Low; readability only.

Suggested direction:

- Clean up style during a normal code-change pass, not as part of documentation-only handoff.
