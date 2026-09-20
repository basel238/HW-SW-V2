# Raytrace: latest shadow-only experiment

The latest raytrace measurements show a **22.63% reduction in median clean runtime**, from **789.756 ms/frame to 611.023 ms/frame**. That exceeds the specified **7% runtime-reduction target for this benchmark** by 15.63 percentage points. Correctness, call counts and performance counters support shadow-ray reuse as the explanation. This is a result for raytrace, not evidence that nbody or all project deliverables are complete.

Only these runs are compared:

- Baseline: `raytrace_baseline_20260920-012836`
- Optimized: `raytrace_optimized_20260920-014248`
- Generated comparison: `comparison_raytrace_20260920-015451`

Earlier runs are excluded. Selection uses timestamps in directory names and agrees with the latest benchmark symlinks; copied filesystem modification times are not used. The comparison symlink points to an absolute Ubuntu path, so its timestamped directory was read directly on Mac.

## 1. Runtime is the deciding metric

Both arms run four 100×100 frames per process, with 11 independent clean processes per arm. The CSV records agree exactly with all 22 raw `RESULT` records. Every optimized timing record says `kernel=shadow_ray`. Both use release Python 3.10.12, GC disabled, `PYTHONHASHSEED=0` and CPU 0 pinning in the same one-vCPU KVM VM.

| Clean statistic | Baseline | Shadow-only |
|---|---:|---:|
| Processes | 11 | 11 |
| Frames per process | 4 | 4 |
| Median total/process | 3.159022 s | 2.444091 s |
| Median/frame | 789.7555 ms | 611.02275 ms |
| Mean/frame | 791.4159 ms | 611.7573 ms |
| Sample standard deviation | 7.3435 ms | 3.7455 ms |
| Coefficient of variation | 0.9279% | 0.6123% |
| Range/frame | 782.292–806.839 ms | 607.521–621.115 ms |

`time reduction = (1 − 2.444091 / 3.159022) × 100 = 22.6314%`

This saves 178.733 ms/frame. Speedup is 1.2925×, corresponding to 29.25% greater throughput; that is a different percentage from the runtime reduction. A 7% reduction would require at most 734.473 ms/frame relative to the observed baseline median.

Even the slowest optimized observation is 20.60% below the fastest baseline observation. This cross-combination is a descriptive separation check, not a formal confidence bound. A reproducible independent bootstrap of process medians gives a descriptive 95% percentile interval of 22.19–23.23% reduction. It resamples within the two observed blocks and cannot capture VM host drift between blocks. Baseline and optimized were collected sequentially, rather than in randomized/interleaved order.

The generated summary's headline arithmetic is correct. Its “2× noise” heuristic is not a statistical hypothesis test, and its “least-noise” label for minimum-versus-minimum should not be treated as a statistical guarantee. The observed effect is large relative to measured variation regardless of those labels.

![Runtime and work](runtime_and_work.png)

## 2. Correctness and what was actually changed

The optimized verification log passes upstream, guards, shadow_ray and combined at 24×24, 100×100 and 37×23, with bit-identical output and baseline method restoration. The subsequent clean/perf workload logs specifically select shadow_ray. Verification of multiple candidates does not mean the timed run used combined.

The original visibility helper constructs `Ray(p, l - p)` inside its loop over scene objects. For a fixed point and light, that expression is unchanged from one object test to the next. The shadow variant constructs it once before the object loop and reuses it. The empty-scene behavior, object order, early return, strict EPSILON comparison and supplied intersection methods' calculations are retained. The supplied Sphere/Halfspace methods read the ray; general custom primitives that mutate it are outside this specialization's contract.

Expected result: fewer Point/Vector operations, Ray constructions and normalizations, while retaining the same intersection tests and output pixels. That exact pattern appears in the VM profile.

## 3. Exact call-count evidence

Both cProfile runs render one frame. The following are whole-process counts; Vector construction includes 12 module-initialization objects in each arm, and dot includes two import-time calls. Their differences therefore measure the workload reduction exactly.

| Operation | Baseline | Shadow-only | Removed |
|---|---:|---:|---:|
| Ray construction | 98,172 | 26,000 | 72,172 |
| Vector construction | 452,955 | 308,611 | 144,344 |
| Vector.normalized | 109,887 | 37,715 | 72,172 |
| Vector.magnitude | 109,887 | 37,715 | 72,172 |
| Vector.scale | 149,747 | 77,575 | 72,172 |
| Vector.dot | 509,873 | 437,701 | 72,172 |
| Vector.mustBeVector | 520,543 | 448,371 | 72,172 |
| Point.__sub__ | 277,865 | 205,693 | 72,172 |
| Point.isPoint | 277,865 | 205,693 | 72,172 |
| Sphere.intersectionTime | 179,457 | 179,457 | 0 |
| Halfspace.intersectionTime | 25,501 | 25,501 | 0 |
| Visibility helper | 10,666 | 10,666 | 0 |
| Scene.rayColour | 15,333 | 15,333 | 0 |
| Canvas.plot | 10,000 | 10,000 | 0 |

The caller edge from visibility checking to Ray construction is especially decisive: **82,838 → 10,666 calls**, removing 87.12% of shadow-ray constructions. Other Ray callers are unchanged: rendering creates 10,001 rays and colourAt creates 5,333. Thus total Ray construction falls 73.52%, while geometry test counts are unchanged.

Whole-process cProfile calls fall from 3,092,298 to 2,299,196 (25.65%). Those include Python and C builtin calls. The render path removes 793,892 calls: 72,172 repetitions × ten Python calls and one sqrt call. Small differences in wrapper/import/setup account for the difference from the net whole-process reduction. This does not imply a fixed cost per call or a 25.65% runtime prediction.

cProfile tracing changes timing. Its cumulative visibility time drops approximately 0.904→0.430 s, which is qualitatively consistent with removing redundant setup, but neither number is a release-runtime result or a precise remaining optimization ceiling.

## 4. Hardware counters support less executed work

Primary values below are from the human-readable TXT perf-stat measurements, means over five processes, divided by four frames. They include process startup/import overhead, unlike the clean timer's internal benchmark interval.

| Counter per frame | Baseline | Shadow-only | Change |
|---|---:|---:|---:|
| Instructions | 5.068 billion | 3.892 billion | −23.20% |
| Cycles | 1.915 billion | 1.487 billion | −22.38% |
| Branches | 652.96 million | 497.21 million | −23.85% |
| L1 data loads | 1.639 billion | 1.263 billion | −22.92% |
| L1 data-load misses | 43.42 million | 37.61 million | −13.38% |
| Branch misses | 2.404 million | 2.215 million | −7.86% |
| dTLB load accesses | 816.93 million | 628.91 million | −23.02% |

Printed IPC is nearly unchanged, 2.63→2.62. Ratios calculated from the reported mean instruction/cycle counts are 2.646→2.618; these aggregates are not numerically identical to perf's printed metric aggregation. Both support the same broad conclusion: the optimization reduces the instruction workload, without a substantial increase in instructions executed per cycle.

The machine-readable CSV files are separate five-process perf-stat runs, not a reformatting of the TXT files. They corroborate instructions −22.96%, cycles −20.86%, branches −23.20% and L1 loads −23.05%. Numerators and denominators from different runs must not be mixed.

## 5. Flame-graph interpretation

The complete native folded profiles contain **1,073 baseline samples and 823 optimized samples**, both for one frame, using the same fixed 5,000,000-cycle sample period and Python debug interpreter. The 23.30% lower sample count is broadly consistent with reduced debug-interpreter cycle work. It is not a substitute for release runtime.

Selected self samples, aggregated across all calling stacks:

| Symbol | Baseline count / share | Optimized count / share |
|---|---:|---:|
| _PyEval_EvalFrameDefault | 320 / 29.82% | 227 / 27.58% |
| call_function | 47 / 4.38% | 22 / 2.67% |
| frame_dealloc | 33 / 3.08% | 27 / 3.28% |
| _PyEval_MakeFrameVector | 29 / 2.70% | 22 / 2.67% |
| PyFloat_FromDouble | 13 / 1.21% | 6 / 0.73% |
| _PyObject_GetMethod | 15 / 1.40% | 17 / 2.07% |

Frame teardown illustrates the denominator issue: its share rises from 3.08% to 3.28%, even though its self samples decrease 33→27. This is compatible with an absolute reduction. Method lookup rises 15→17 samples, too small a difference to establish a regression. The inclusive frame_dealloc samples are 76→77, another reminder that sparse self/inclusive attribution should not be forced into a claim that every runtime component improved.

![Native self samples](native_self_samples.png)

The top-30 files cover only 297/1,073 (27.68%) and 244/823 (29.65%) samples. Many rows end in the same evaluator symbol but have different ancestors. Twenty-three baseline top-30 rows end in the evaluator (264 samples); seventeen optimized rows do (195 samples). They are not thirty independent bottlenecks. The repeated C evaluator/call layers remain because the optimized render still executes about 2.16 million Python function calls in the profiled process.

Stack height is nesting depth, not total calls. Mean recorded depth rises 67.30→69.25 despite fewer calls and lower runtime. Wrapper nesting and which stacks remain affect depth. Therefore a taller tower does not establish more work.

**The supplied differential flame graph needs cautious interpretation.** `tools/compare.sh` uses `difffolded.pl -n`, which equalizes total sample weights. Its colors describe changes in normalized stack share, not saved milliseconds or per-frame absolute cycle cost. A red stack can represent an unchanged cost that occupies more of a smaller total. The extra optimized wrapper also changes ancestry, so identical interpreter work can be separated into different complete stacks. Normalization by total sample count is not equivalent to normalization by completed frames.

The files named `*_python.folded` retain all native samples; they filter native stacks and do not recover names such as dot or intersectionTime. They are not an independent Python-level py-spy measurement. The native data supports C-runtime attribution; cProfile supplies Python function names and exact call counts.

There are no reported lost samples, but 227 baseline samples (21.16%) and 179 optimized samples (21.75%) contain an unknown frame. Only 7/8 samples have an unknown leaf. This weakens caller-path attribution more than leaf attribution; it does not mean 21% of execution is entirely unidentified. Debug-interpreter percentages must not be presented as release-runtime fractions or Amdahl limits.

## 6. What was not uniformly improved

- L1 miss fraction increases from 2.649% to 2.977%, while misses per frame decrease 13.38%. Loads fall more quickly than misses, so the fraction rises.
- Branch-miss fraction rises 0.368%→0.445%. Absolute misses decline 7.86% in TXT but only 0.68% in the separate CSV measurements. This does not establish improved branch prediction.
- dTLB misses increase 32.7% in TXT and 131.2% in CSV even as dTLB accesses decline. The events are small and variable; improved address-translation locality is not demonstrated.
- Generic cache misses increase, with very high reported variability. They are not evidence that the optimization improved cache locality.
- Top-down output is invalid: bad-speculation percentages are −61.2% and −60.6%. Reject the associated frontend/backend shares, including the apparent ~86% backend-bound result.
- LLC-load counters are unsupported, not zero. Hardware counters are multiplexed, typically active for only 40–60% of the accounting interval in this VM. Large consistent instruction reductions are useful evidence; precise memory-stall attribution is not supported.

None of these observations conflicts with the main mechanism: execute fewer instructions and fewer object/helper operations to render the same image.

## 7. Confidence, provenance and next actions

The 7% runtime target is exceeded in this observed experiment with a wide margin. Both arms have the same workload settings and upstream hash; clean observations are well separated and counter/call-count changes are consistent. A final interleaved baseline/optimized repetition would strengthen protection against VM host drift, but the present result is already a strong measured effect.

Manifests record commit `d54e98c` with 6 and 8 dirty files. They hash upstream but do not record the optimized file's hash or the dirty diff. Logs and cProfile clearly identify shadow-only behavior; the precise full working-tree source snapshot cannot be reconstructed solely from these manifests. Future runs should save candidate/harness hashes and relevant source differences. The `pyperformance: UNVERIFIED` extraction metadata is also a provenance gap, not evidence of incorrect rendered work. These are custom wrapper comparisons; only the baseline has a separate official pyperformance suite run.

Keep this experiment as the measured shadow-only result. Further candidates should use separate labels and preserve its artifacts. The residual profile makes scalar sphere intersection a useful next hypothesis: 179,457 sphere tests remain, invoking two dot products each—358,914 calls, about 82% of the remaining 437,699 workload dot calls. Computing those expressions directly from local coordinates could also avoid one temporary Vector per sphere test. Preserve arithmetic order and correctness checks, then measure its incremental benefit against shadow-only as well as total benefit against upstream. It is not yet a measured improvement in this experiment.

The evidence supports this report claim: **“Reusing one shadow ray per visibility query removed 72,172 redundant ray constructions and normalizations per 100×100 frame, while retaining intersection counts and bit-identical output. Median clean runtime decreased 22.63%, accompanied by approximately 23% fewer retired instructions.”**

## Evidence and reproducibility

- [Computed runtime data, native sample totals and input hashes](analysis.json)
- [Detailed counter audit](counter_review.md)
- [Detailed profile audit](profile_review.md)
- [Baseline native flame graph](evidence/raytrace_baseline_20260920-012836/flame/baseline.svg)
- [Shadow-only native flame graph](evidence/raytrace_optimized_20260920-014248/flame/optimized.svg)

The accompanying evidence archive contains the selected timing logs, manifests, verification logs, profiles, counters, original flame graphs, computed evidence and the analysis used to generate the figures. Repository source and result files were not modified.
