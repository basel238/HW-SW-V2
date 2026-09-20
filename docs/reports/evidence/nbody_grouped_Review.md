# Latest nbody experiment: grouped state reuse

**The grouped variant improves median clean runtime by 3.40%, below the required 7% runtime reduction.** It performs less work in the intended list-access paths and retires about 6.4% fewer instructions. The effect is modest because most arithmetic/object work remains, and grouping introduces extra iteration machinery. Branch misses also increase, although their precise runtime cost is not established.

Only the newest nbody pair is used:

- `nbody_baseline_20260920-015849`
- `nbody_optimized_20260920-020900`
- `comparison_nbody_20260920-021902`

The timestamped directories agree with the latest benchmark symlinks. The comparison symlink is an absolute Ubuntu path, so its directory was accessed directly on Mac. No earlier candidate results are substituted or mixed into this comparison.

## Runtime verdict

The clean logs confirm five bodies, ten pairs, 20,000 timesteps per unit, 16 units per process, and 11 processes per arm. Every optimized record says `kernel=grouped`. Both arms use release Python 3.10.12, GC disabled, CPU 0 pinning and hash seed 0 on the same one-vCPU KVM VM. All 22 CSV values match their corresponding raw RESULT records.

| Statistic | Baseline | Grouped |
|---|---:|---:|
| Median process runtime | 3.637018 s | 3.513416 s |
| Median / 20,000 steps | 227.313625 ms | 219.588500 ms |
| Mean / 20,000 steps | 230.955210 ms | 219.837727 ms |
| Standard deviation | 7.919916 ms | 1.799431 ms |
| Relative standard deviation | 3.4292% | 0.8185% |
| Observed range | 226.487250–253.155938 ms | 217.542125–223.004813 ms |

Runtime reduction: `(1 − 3.513416 / 3.637018) × 100 = 3.39844%`.

The speedup is 1.03518×, saving 7.725125 ms per 20,000-step unit. A 7% reduction against this baseline median requires **211.401671 ms/unit**, or 3.38242674 seconds for 16 units. Grouped would need approximately **another 3.73% reduction from its own runtime** to reach that observed threshold. These are arithmetic targets, not predictions or guaranteed future baselines.

![Clean runtime and counters](runtime_and_work.png)

The mean-based reduction is 4.81%, also below the target. It is larger because baseline repetition 5 took 253.156 ms/unit, 11.37% above its median; other slow baseline observations also increase the mean and standard deviation. All observations are retained. Selecting a favorable statistic or deleting slow samples to claim 7% would be inappropriate.

Every optimized clean observation is below every baseline observation: slowest optimized 223.005 ms versus fastest baseline 226.487 ms. This supports an improvement within the observed blocks. The generated summary's rule “improvement < 2× relative standard deviation” is a noise heuristic, not a formal statistical test. Its “NOT statistically solid” wording should not be interpreted as proof that the optimization has no effect.

A descriptive independent bootstrap of process medians gives a 95% percentile interval of approximately 2.76–5.71% reduction (100,000 resamples, seed 20260920). It assumes observations within the recorded blocks can be resampled; it cannot account for VM drift between the sequential baseline and optimized blocks. A balanced/interleaved clean timing experiment would strengthen causal confidence. The recorded primary result remains 3.40%, below the bar.

## What was expected to change

The original pair loop repeatedly reads and writes each body's three velocity components. Grouped retains the first body's velocity and position in locals across consecutive pairs sharing that body. The canonical pair sequence has four groups of lengths 4, 3, 2 and 1. It preserves pair order and arithmetic, including the original inverse-power expression. Second-body velocity writes and the complete-body position-update pass remain.

Prior logical component counting found:

| Component operations per timestep | Baseline | Grouped | Reduction |
|---|---:|---:|---:|
| Reads, including unpacking | 150 | 114 | 24% |
| Writes | 75 | 57 | 24% |
| Combined | 225 | 171 | 24% |

These counts include position and velocity components only. They are not hardware load counts or time fractions. Both local-variable handling and unchanged arithmetic still execute machine instructions and access Python objects.

A useful refinement separates explicit indexed reads from unpacking:

| Access form per timestep | Baseline | Grouped |
|---|---:|---:|
| Explicit `list[index]` component reads | 75 | 45 |
| Components read by unpacking | 75 | 69 |
| Indexed component writes | 75 | 57 |

Baseline indexed reads consist of 60 velocity reads in the pair phase and 15 position reads in the drift phase. Grouped keeps only 30 second-body velocity reads plus the same 15 drift reads; the first body's velocity is unpacked once per group. Thus explicit GetItem-style reads drop **40%**, while writes drop **24%**. This distinction is important when interpreting native item-access stacks.

## What the full native profile actually shows

Both perf-record runs use the debug interpreter for **five units of 20,000 steps**, with the same fixed five-million-cycle sample period. They contain 1,178 and 1,120 samples, a 4.92% reduction. This is diagnostic debug-profile evidence, not the release-runtime result.

| Function/path | Baseline samples | Grouped samples | Interpretation |
|---|---:|---:|---|
| PyObject_GetItem and descendants | 84 | 54 | 35.7% fewer samples in the targeted read path |
| PyObject_SetItem and descendants | 118 | 91 | 22.9% fewer samples in the targeted write path |
| Union of those item-access paths | 202 | 145 | 28.2% fewer samples; no double counting |
| _PyEval_EvalFrameDefault, self | 531 | 482 | Broad interpreter work remains dominant |
| PyFloat_FromDouble, self | 38 | 38 | No observed reduction in this float-creation sample count |
| listiter_next, self | 6 | 10 | Direction consistent with more iteration work, but sparse |

Item-access paths shrink from 17.15% to 12.95% of their respective native profiles. The read-path drop is larger than the write-path drop, in the direction predicted by the explicit-access counts (40% versus 24%). This is a convincing qualitative check of the intended mechanism; sparse debug samples cannot establish exact release cost fractions.

In this particular recording, samples outside those item-access paths are 976→975. The item-access paths decrease by 57 samples, accounting arithmetically for 57 of the overall 58-sample decline. That is a useful description of this recording, not proof that exactly all runtime savings are caused by that region or that all other costs are unchanged.

![Selected native paths](native_samples.png)

The evaluator remains the largest self symbol: 45.08%→43.04%. Arithmetic dispatch, multiplication/addition, float allocation/refcounting and the original power operation still occur. Python locals retain Python object references; they do not automatically become unboxed floating-point CPU registers.

Some remaining symbols rise: binary_op1 self samples 64→71, float deallocation 31→37, and libm power 17→24. Their arithmetic operations have not been intentionally increased by grouped. These small sample changes may reflect sampling variation and execution conditions; they do not establish a newly dominant power bottleneck or justify a hard Amdahl limit.

## Why the flame graphs can still look similar—or split differently

Both versions execute a numerical loop inside one advance function. Grouped changes the operations inside that function rather than removing hundreds of thousands of Python-level helper calls as shadow-ray reuse did. cProfile sees one advance call in each one-unit profile. Its whole-process call totals actually increase 4,911→5,926 due largely to wrapper/import/setup differences; those totals do not measure bytecode-level list-access work.

The optimized evaluator samples are split between different calling-stack ancestry. In the top-30 files, the major baseline evaluator stack has 528 samples; optimized has major evaluator stacks of 378 and 102 samples. Comparing only 528 with 378 would exaggerate the change. Aggregating all evaluator leaves gives the correct 531→482 comparison.

Fixed-width flame graphs show each profile as 100% of its own samples. A region's percentage can rise even when its absolute sample count stays constant: PyFloat_FromDouble is 38 samples in both, but its share rises 3.23%→3.39%. Stack height describes nesting, not total repeated operations. The additional optimized partial/wrapper path can alter ancestry and differential stack matching without representing a new hot mathematical operation.

The generated differential graph uses normalized total sample weights, so red/blue show changes in relative stack share/composition, not directly saved or added milliseconds per unit. The “Python-only” native filtering does not produce Python function names or an independent py-spy profile. Native symbol attribution and cProfile provide different complementary views.

## Why fewer list accesses did not yield a large speedup

First, only part of the workload was reduced. Grouped still performs 76% of the counted component accesses, all pair interactions, the original power calculation, essentially the same floating arithmetic, and the unchanged drift pass. A 24% reduction in one category is not a 24% reduction in total interpreter work.

Second, grouped introduces extra iteration machinery. Including the unchanged body-update pass, the original code sets up two list iterators per timestep (pairs and bodies), while grouped sets up six (groups, four partner lists, and bodies). That is 80,000 additional iterator setups per 20,000-step unit. Sampled list-iterator creation and destruction paths rise, though their counts are too small for a precise cost claim.

The one-time grouping construction is not a convincing main culprit: cProfile records one grouping call and ten append calls per 20,000-step unit, about eight microseconds in the traced recording. The repeatedly executed short loops and interpreter work matter more as an optimization hypothesis than building the tiny grouping structure once.

Third, branch misses increase. This could offset some savings, but the counters do not locate the missed branches or quantify their cycle cost. The short nested loops and changed bytecode sequence are plausible explanations to test, not established causes of a particular missing percentage.

## Hardware counters: gains and tradeoffs

Primary TXT values are mean process counts over five runs, divided by 16 units. They include startup and shutdown as well as the timed kernel.

| Counter per 20,000 steps | Baseline | Grouped | Change |
|---|---:|---:|---:|
| Instructions | 1.690 billion | 1.582 billion | −6.36% |
| Cycles | 564.03 million | 523.06 million | −7.26% |
| Branches | 192.95 million | 180.16 million | −6.63% |
| Branch misses | 0.679 million | 1.087 million | +60.18% |
| L1 data loads | 536.67 million | 501.39 million | −6.57% |

The independent CSV counter batch corroborates instructions −6.45%, L1 loads −6.72%, branches −6.48%, and increased branch misses (+37.05%). L1 load-miss direction differs: TXT −30.54%, CSV +23.50%. Improved cache-miss behavior is not established. L1 loads encompass interpreter/object/stack accesses; they are not identical to the counted Python state accesses.

**The 7.26% cycle reduction is not a 7% runtime pass.** The counter runs are separate batches from clean timing. Their logged internal benchmark medians are 236.905→221.667 ms/unit (6.43% reduction), while clean medians are 227.314→219.589 ms (3.40%). The counter-batch baseline was relatively slower. Different batches, means versus medians, process versus internal scope, VM variability and PMU multiplexing prevent an exact identity across those values. The favorable counter batch must not replace the specified clean result.

IPC remains around three. Calculated ratios of TXT mean counts are 2.996→3.025; the separate CSV ratios are 3.048→3.028. Perf's printed annotated TXT IPC is 3.03→3.01. These small differences depend on batch/aggregation conventions. There is no strong evidence that a particular IPC regression explains the entire clean-runtime gap.

## Measurement limitations and correctness

- Both clean arms finish with energy −0.1690801979358367. The saved automated verify log proves bit-identical energy and all 30 components after one unit; it does not forward the 16-unit timing setting. The earlier manual Ubuntu verification supplied in this conversation separately passed the full 16×20,000-step check. That console output should be preserved alongside final run artifacts.
- Manifests record the same commit 2d5f5e5 with 6/8 dirty files, but no optimized-source hash or dirty diff. The logs and profile identify grouped; exact immutable candidate provenance is incomplete.
- Native profiling uses Python debug, clean timing uses release. Debug percentages are not release-runtime fractions or hard optimization ceilings.
- PMU events are multiplexed, usually active for 40–60% of their measurement interval. That is coverage, not a statistical confidence interval.
- Top-down percentages are invalid: bad speculation is −74.1%/−70.7%. Reject associated 93.1%/91.0% backend-bound diagnoses. LLC counters are unsupported; generic cache-miss counts are extremely noisy.
- Baseline and optimized timing were collected in separate blocks. An interleaved confirmation is useful, particularly for a modest gain.

## Recommended next candidate

Keep grouped as a measured intermediate experiment rather than claiming it passes. The direction of the original bottleneck hypothesis is supported: generic state accesses fell and runtime improved. Its magnitude is insufficient in the target VM measurement.

The next candidate should retain more of the five-body state in locals across timesteps and remove the repeatedly traversed pair/group structure. A fixed-five-body implementation can load the 30 position/velocity components once, execute the ten pairs in their original order with the original power expression, update positions after all pairs each step, and write state back at the advance boundary. That attacks remaining list access, unpacking and short-loop machinery together, without changing the physics calculation.

This is a specialization for the benchmark's ordinary distinct state lists and canonical five-body pair order. It must still read the provided state/masses and perform every timestep; it cannot hardcode results. Local Python arithmetic remains boxed. Delayed writeback changes intermediate state visibility for arbitrary observers/exception paths, so general API equivalence should not be claimed. The existing scratch prototype's local correctness checks are encouraging, but **no new target-VM speedup is established here**.

Evaluate it as a separate variant against both upstream and grouped, retain exact state/energy checks at the measured work count, and use clean timing for the 7% judgment. To avoid a narrow margin, aim comfortably beyond the arithmetic minimum of another 3.73% improvement over grouped.

## Supporting artifacts

- [Recomputed values and input hashes](analysis.json)
- [Detailed counter audit](counter_review.md)
- [Detailed profile audit](profile_review.md)
- [Baseline native flame graph](evidence/nbody_baseline_20260920-015849/flame/baseline.svg)
- [Grouped native flame graph](evidence/nbody_optimized_20260920-020900/flame/optimized.svg)

The evidence archive contains the selected raw timing logs, counter outputs, folded profiles, native graphs, profile records, manifests and analysis. Repository files were not changed.
