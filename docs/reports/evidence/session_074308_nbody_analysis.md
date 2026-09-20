# Latest matched nbody session: 36.89% runtime reduction reproduced

## Exact session and correctness

Session `results/session_all_20260920-074308_674/nbody.tsv` selects baseline `nbody_baseline_20260920-080806_16940`, optimized `nbody_optimized_20260920-081744_16940`, and its own `comparison_nbody`. These exact paths agree with comparison `inputs.tsv`; no latest-pointer mixing was used. The VM absolute paths were mapped to the same repository-relative paths after transfer to Mac.

The optimized workload is **flat_pow**, not grouped, flat_sqrt, or a new kernel. Its SHA-256 is `5b0dbb3b3f9d7d74331679d208e4a721c04f219f13a0740cf3ab4369f406bbcb`: identical to the previous full run and current source. Every recorded source hash—optimized kernel, baseline wrapper, original upstream, common/pipeline scripts and configuration—matches the current local file. Git metadata is explicitly disabled. Full hash maps and artifact hashes are in the accompanying JSON.

The saved optimized verification now explicitly covers **16 consecutive units × 20,000 steps**, with bit-identical energy and all 30 state components versus upstream. This closes the previous run's missing saved batch-validation evidence. The standalone baseline verification still checks only one unit despite the phase ledger saying loops=16; this is a bookkeeping/implementation discrepancy, but the optimized verifier independently runs the complete reference and candidate batch. All timed samples report energy `−0.1690801979358367`.

## Clean runtime

Same one-vCPU KVM Ubuntu 22.04.5 environment, release Python 3.10.12, CPU 0, cyclic GC disabled and hash seed 0. Each process performs 16 units (320,000 timesteps, 3.2 million pair interactions). All 22 raw RESULT timings match the 11+11 CSV observations exactly.

| Clean measurement | Baseline | flat_pow |
|---|---:|---:|
| Median per 16-unit process | 3.635132 s | 2.293979 s |
| Median per 20,000 steps | 227.195750 ms | 143.373688 ms |
| Mean per unit | 227.906477 ms | 143.807307 ms |
| Standard deviation per unit | 1.989985 ms | 1.441189 ms |
| Relative standard deviation | 0.8732% | 1.0022% |
| Minimum–maximum per unit | 226.2221–232.0217 ms | 142.4807–146.2320 ms |

**Median reduction: 36.894204%. Speedup: 1.584640×.** Mean reduction is 36.900737%. The median saving is 83.822063 ms per unit. Even the slowest optimized observation beats the fastest baseline by 35.3591%.

The previous full pair (`031836`/`032819`) gave 37.533913%. The difference is −0.639709 percentage points: the new baseline median is 0.4616% faster and the new optimized median 0.5578% slower. The implementation hash is unchanged. This is a consistent repeat of the same large gain, not evidence of another optimization or meaningful regression. Keep both matched pairs separate; use this latest result as the current headline.

Measurements remain sequential blocks. The generated “improvement >2× noise” statement is a heuristic, not a confidence interval. Nevertheless, the large observed separation comfortably clears the 7% runtime bar. Do not cherry-pick the older 37.53% merely because it is larger.

## Hardware counters: less work, not demonstrated cache-miss relief

Each TXT count is the mean of five whole processes. Divide by **16**, not 80. The CSV is an independent five-process experiment, not a reformatted TXT output.

| Event per 20,000 steps (TXT) | Baseline | flat_pow | TXT change | CSV change |
|---|---:|---:|---:|---:|
| Instructions | 1,691,785,765 | 1,101,148,149 | −34.91% | −34.82% |
| Cycles | 549,829,066 | 347,973,553 | −36.71% | −37.03% |
| Branches | 193,593,056 | 125,500,009 | −35.17% | −35.11% |
| Branch misses | 670,158 | 584,812 | −12.74% | −27.49% |
| L1-data loads | 535,845,543 | 351,722,247 | −34.36% | −34.50% |
| L1-data load misses | 212,154 | 233,439 | +10.03% | −10.35% |
| dTLB loads | 267,026,864 | 174,310,539 | −34.72% | −34.22% |

Instruction, branch and load reductions reproduce the earlier full run closely. This supports less Python container/interpreter work. It does not prove improved memory-cache locality: L1 miss counts disagree in direction between independent batches. Generic cache misses decline 58.13% in TXT but only 1.61% in CSV; dTLB misses decline 10.46% in TXT but rise 14.45% in CSV. These are not stable optimization mechanisms.

TXT aggregate IPC is 3.0769→3.1645, a modest change alongside the large instruction reduction. Branch-miss rate rises 0.3462%→0.4660% while absolute misses fall, because branch count shrinks more. Hardware events are multiplexed around 40–60%; LLC events remain unsupported. Topdown has impossible negative speculation values (−73.6%, −75.2%): reject that partition and any inferred “backend-bound percentage.”

Counters include interpreter startup/imports outside the clean internal timer. Count deltas support the runtime mechanism; they are not the passing runtime metric.

## Native profiles and remaining work

Both native profiles use debug Python 3.10.12, five units, DWARF and a fixed period of five million cycles. Folded totals equal perf SAMPLE totals: **1,175→725**, down 38.2979%. No lost events are reported. Kernel relocation and BPF synthesis warnings qualify kernel-symbol analysis; they do not establish that user-space samples were lost.

Counts below use every folded stack; inclusive unions count each sample only once.

| Native path | Baseline | flat_pow |
|---|---:|---:|
| PyObject_GetItem inclusive | 83 | 0 |
| PyObject_SetItem inclusive | 123 | 2 |
| Combined item-access union | 206 (17.53%) | 2 (0.28%) |
| Evaluator **self** | 526 (44.77%) | 285 (39.31%) |
| PyFloat_FromDouble inclusive | 71 | 73 |
| float_dealloc inclusive | 41 | 42 |
| binary_op1 inclusive | 243 | 228 |
| libm `__ieee754_pow_fma` self | 20 | 19 |

Item-access samples again almost disappear (−99.03%). Evaluator self samples fall 45.82%. Float boxing/freeing and native pow remain approximately unchanged in absolute sample count. This strongly reproduces the earlier explanation: retaining state in locals and removing inner traversal eliminates recurring container access and reduces evaluator execution; it does not remove the original arithmetic or Python float-result creation.

Remaining costs span evaluator execution, generic arithmetic dispatch, float-object handling and native arithmetic. A large evaluator percentage is not exclusively function-call overhead, and debug shares are not release Amdahl fractions. Isolating individual contributions would require ablation measurements.

Both flame graphs retain CPython's stack structure, and both expand to the same width despite different sample totals. Relative shares of remaining work therefore grow. Mean native depth is 41.56→52.59 because wrapper/import ancestry differs, not because every pair calculation gained extra helper calls. The legacy `_python.folded` selection retains 1,175/1,175 and 724/725 samples: whole native stacks containing interpreter symbols, not Python-only frames. Normalized differential colors indicate relative share, not absolute saved time.

## cProfile, official baseline and integrity caveats

cProfile contains one numerical advance call per arm. Traced self time is 0.311599 s for upstream and 0.208254 s for flat_pow; use these only for attribution. Whole-process calls remain 4,911→25,256, exactly the previous run's counts, mostly reflecting different import/startup paths rather than timestep helper calls.

The official baseline-only pyperformance artifact has 60 values from 20 value-producing workers: exact mean **229.410745 ms**, median **228.635822 ms**, sample SD **3.439029 ms**. This agrees with the baseline scale. Unlike the prior artifact, its stats output contains no instability warning. There is no official optimized-harness result.

Session/phase evidence is improved, but not perfect:

- `perf_stat` and `cache_profile` remain at “requested” in the append-only phase ledger even though result artifacts exist; inspect their files rather than infer failure or success from an absent terminal marker.
- py-spy was explicitly disabled. Its absence is not a failed phase.
- Upstream provenance still contains the old UNVERIFIED placeholder, and there is no saved phase-0 package-hash transcript in this session. Current hashes identify the files, but do not reconstruct that historical authenticity check.
- The ledger's baseline loops=16 verification claim exceeds what the standalone baseline log demonstrates; the optimized gate does demonstrate the complete batch.

**Decision:** update the nbody report headline to **36.89% runtime reduction**, retain the prior 37.53% as a separate repeat in the history, and retain grouped as the earlier limited improvement. The latest full session reproduces the expected mechanism and now preserves the exact full-batch correctness evidence.
