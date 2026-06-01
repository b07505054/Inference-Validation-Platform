# Runtime Artifact Validation Report: runtime-artifact-validation-001

**Result:** PASS
**Source runtime:** `/Users/allen/Desktop/project/heterogeneous-inference-runtime/results/llm_runtime_artifacts`
**Model:** `tiny-gpt`

## Prefill / Decode

- Prefill latency: `185.464` ms
- p95 decode latency: `15.63` ms
- Tokens/sec: `76.254`

## SLO

- p95 end-to-end latency: `1628.828` ms
- p95 queue wait: `17.87` ms
- OOM events: `0`
- Admission rejection rate: `0.0`

## KV Cache

- Peak blocks used: `70` / `512`
- Block utilization: `0.1367`
- Fragmentation ratio: `0.095`
- Peak KV cache: `218.75` MB

## Scheduler

- Policy: `prefill-first-with-batched-decode`
- Decode batch events: `130`
- Avg decode batch size: `1.0`
- p95 queue wait: `17.87` ms

## Backend Placement

- Heterogeneous execution detected: `True`
- Backend counts: `{'gpu': 32, 'cpu': 32}`
- Op counts: `{'attention_prefill': 32, 'kv_cache_update': 32}`

## Validation Positioning

This report validates runtime artifacts produced by `heterogeneous-inference-runtime` rather than only simulating worker behavior inside the validation platform.
