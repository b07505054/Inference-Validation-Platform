# Runtime Artifact Validation Report: runtime-artifact-validation-001

**Result:** PASS
**Source runtime:** `/Users/allen/Documents/Codex/project/heterogeneous-inference-runtime/results/llm_runtime_artifacts`
**Model:** `tiny-gpt`

## Prefill / Decode

- Prefill latency: `38.316` ms
- p95 decode latency: `3.244` ms
- Tokens/sec: `1236.142`

## SLO

- p95 end-to-end latency: `1716.077` ms
- p95 queue wait: `1381.098` ms
- OOM events: `0`
- Admission rejection rate: `0.0`

## KV Cache

- Peak blocks used: `278` / `512`
- Block utilization: `0.543`
- Fragmentation ratio: `0.05`
- Peak KV cache: `868.75` MB

## Scheduler

- Policy: `cost_aware_memory_pressure`
- Decode batch events: `5`
- Avg decode batch size: `6.4`
- p95 queue wait: `1381.098` ms

## Runtime Decision Validation

- Selected policy: `cost_aware_memory_pressure`
- Decision validation passed: `True`
- Tokens/sec delta: `938.095`
- p95 latency delta: `-5869.755` ms
- Decode batch efficiency delta: `0.675`
- Pressure-limited candidates: `20`
- Regression detected: `False`

## Serving Framework Targets

- Selected style: `vllm_sglang_style`
- Validation passed: `True`
- Available styles: `['baseline_fcfs', 'tensorrt_style', 'triton_server_style', 'vllm_sglang_style']`
- TTFT: `38.316` ms
- TPOT p95: `3.244` ms/token
- Throughput: `1236.142` tokens/s
- Peak KV cache: `868.75` MB
- Selection reason: `cost-aware policy improved tokens/sec while staying within KV memory capacity`

## Backend Placement

- Heterogeneous execution detected: `True`
- Backend counts: `{'gpu': 5, 'cpu': 5}`
- Op counts: `{'attention_prefill': 5, 'kv_cache_update': 5}`

## Validation Positioning

This report validates runtime artifacts produced by `heterogeneous-inference-runtime` rather than only simulating worker behavior inside the validation platform.
