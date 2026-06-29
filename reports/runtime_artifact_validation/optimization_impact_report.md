## Optimization Impact Report: distributed_runtime_plan

**Model**:   
**Policy**:   
**Overall Status**: warn  
**Truth Boundary**: optimization_impact_validation_simulated_not_measured_cluster_performance

---

### prefix_cache — miss

**Evidence Status**: warn  
**Explanation**: Cache miss: no prefill time saved, TTFT and TPOT unchanged. Warnings: truth_boundary is missing or empty; all optimization claims must carry an explicit truth boundary | missing before/after metric fields: baseline_ttft_ms, optimized_ttft_ms, baseline_tpot_ms, optimized_tpot_ms; optimization claims require explicit before and after values

**Affected Metrics**: none

**Tradeoff Metrics**: none

**Truth Boundary**: 
