# Latest nbody grouped: counter audit

Selected directories: `nbody_baseline_20260920-015849` and `nbody_optimized_20260920-020900`, with `comparison_nbody_20260920-021902`.

The release-interpreter workload logs explicitly confirm `kernel=grouped`, five bodies, ten pairs, 20,000 steps per unit, and 16 units per process. Both log the same ending energy, -0.1690801979358367. Hash seed 0, GC disabled, CPU 0 pinned; Ubuntu 22.04.5, Python 3.10.12, one KVM vCPU reporting Intel Xeon E5-2630 v3. Perf TXT and CSV are **separate five-run batches**: `lib/common.sh` calls `perf stat` twice, rather than converting one output. Counts are the reported five-run averages, so divide by **16, not 80**. Counters cover complete processes, including startup/imports; clean timing measures the benchmark's internal timed region.

## Primary TXT counters, per 20,000-step unit

| Event | Baseline | Grouped | Change |
|---|---:|---:|---:|
| Instructions | 1,689,701,677.25 | 1,582,274,311.19 | -6.3578% |
| Cycles | 564,025,616.81 | 523,062,106.38 | -7.2627% |
| Branches | 192,946,062.81 | 180,158,360.06 | -6.6276% |
| Branch misses | 678,663.38 | 1,087,053.13 | +60.1756% |
| L1 data loads | 536,665,888.56 | 501,386,883.75 | -6.5737% |
| L1 data-load misses | 305,418.63 | 212,150.38 | -30.5378% |
| dTLB loads | 265,994,035.94 | 248,390,407.13 | -6.6181% |
| dTLB misses | 57,826.63 | 10,552.69 | -81.7512% |

Ratios calculated from the displayed average totals: IPC 2.99579 -> 3.02502; branch miss rate 0.35174% -> 0.60339%; L1 data-load miss rate 0.05691% -> 0.04231%. Perf's own annotated IPC is 3.03 -> 3.01 and is not equal to the ratio of these printed totals; do not mix those reporting conventions or infer a precise IPC mechanism from their small discrepancy.

## Independent CSV cross-check

| Event | Change |
|---|---:|
| Instructions | -6.4484% |
| Cycles | -5.8322% |
| Branches | -6.4814% |
| Branch misses | +37.0453% |
| L1 data loads | -6.7193% |
| L1 data-load misses | +23.4997% |
| dTLB loads | -7.0487% |
| dTLB misses | -79.0475% |

CSV calculated IPC 3.04844 -> 3.02849; branch miss rate 0.40553% -> 0.59427%; L1 miss rate 0.04156% -> 0.05503%.

The repeatable signature is fewer instructions, branches, and loads, with more branch misses. L1 miss count changes direction, so improved cache-miss behavior is **not established**. IPC remains near 3 and its small direction changes across conventions/batches; there is **no solid measured IPC explanation** for the gap between instruction savings and clean timing savings. Both sets show lower dTLB misses, but baseline variability is substantial and optimized CSV reports 120.49% variation; these sparse virtualized/multiplexed events do not justify precise causal attribution.

## Why -7.26% cycles is not a 7% project pass

The headline is clean internal benchmark timing: median 227.313625 -> 219.588500 ms/unit, **3.398443% runtime reduction**. Cycle counts cannot replace the required runtime metric.

The counter batch is also a different execution period from clean timing. Its five logged `RESULT total_sec` values have:

| Statistic from TXT stat workload log | Baseline | Grouped | Reduction |
|---|---:|---:|---:|
| Mean internal time/unit | 236.373963 ms | 222.502238 ms | 5.86855% |
| Median internal time/unit | 236.904625 ms | 221.666813 ms | 6.43205% |

The corresponding perf process elapsed means are 3.8268 -> 3.6063 seconds (5.76200% lower), including startup and shutdown. These diagnostic times describe why the counter ratio need not match clean median timing. Baseline counter-batch internal median is 4.22% slower than the clean baseline median, while optimized is 0.95% slower than its clean median. Different batches, mean-versus-median statistics, process-versus-internal measurement scope, PMU multiplex scaling and VM variability prevent one exact instruction/cycle/runtime identity across these files. Do not select the more favorable batch as the performance result.

## Limits and interpretation

- Instructions run about 60%, cycles 50%, and load counters 40% of their measurement intervals; displayed counts are scaled estimates. The repeated instruction/load reduction across independent batches is useful evidence, but the running percentage is not a statistical confidence interval.
- LLC events are unsupported, not zero. Generic cache misses have very high reported variation (TXT 211%-315%, CSV 149%-179%); do not build a cache conclusion from them.
- Top-down bad speculation is negative (-74.1%, -70.7%): reject the associated frontend/backend partition. The reported 93.1%/91.0% backend values are not a defensible bottleneck diagnosis.
- Hardware L1 loads are not Python list reads. Many include interpreter state, object metadata and stack accesses. Source-level counted component accesses fall 24%, but total machine loads fall only ~6.6%; this is consistent with a targeted saving in a larger workload.
- Extra branch misses are a plausible offsetting cost, potentially related to changed bytecode/control-flow patterns and nested grouping loops. The data do not locate the misses or assign their cycle cost, so this is a hypothesis, not an established explanation for a precise lost percentage.
- Arithmetic order, power operations and the number of floating arithmetic results are unchanged. Local Python variables still hold Python float references; the change does not unbox arithmetic or eliminate float allocation.
- Manifests name the same Git commit `2d5f5e5` but dirty counts 6/8 and no optimized-source hash. Workload logs identify grouped, yet exact candidate-source provenance remains incomplete. The saved pipeline verify log checks one unit; prior user-provided manual output separately verified 16 units bit-identically.

Machine-readable details and all original normalized values are in `counter_evidence.json` next to this note. No repository files were changed.
