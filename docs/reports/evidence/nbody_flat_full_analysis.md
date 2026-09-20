# Nbody flat_pow: latest full Ubuntu run

## Evidence selected

Only this matched full-workflow pair is used:

- Baseline: `results/nbody_baseline_20260920-031836`
- Optimized: `results/nbody_optimized_20260920-032819`
- Generated comparison: `results/comparison_nbody_20260920-033626`

The selected optimized kernel is **flat_pow**, consistently recorded in clean timing, counter workloads, native sampling and cProfile. Its logged SHA-256 is `5b0dbb3b3f9d7d74331679d208e4a721c04f219f13a0740cf3ab4369f406bbcb`, which matches the current optimized source exactly at review time. This is not the grouped or sqrt kernel.

## Runtime outcome: passes the 7% requirement

Each independent clean process executes 16 consecutive units of 20,000 steps: 320,000 timesteps and 3.2 million unordered pair interactions. Both arms use the release Python 3.10.12 interpreter, CPU 0, disabled cyclic GC and hash seed 0 on the same one-vCPU KVM Ubuntu 22.04.5 VM. There are 11 independent processes per arm. All 22 raw RESULT timings exactly match their CSV rows.

| Clean measurement | Baseline | flat_pow |
|---|---:|---:|
| Median per 16-unit process | 3.651988 s | 2.281254 s |
| Median per 20,000 steps | 228.249250 ms | 142.578375 ms |
| Mean per 20,000 steps | 228.128432 ms | 144.193222 ms |
| Standard deviation per unit | 1.491353 ms | 3.706734 ms |
| Relative standard deviation | 0.6537% | 2.5707% |
| Minimum–maximum per unit | 226.3601–231.0803 ms | 142.2534–153.8870 ms |

**Median runtime reduction = 37.533913%; speedup = 1.600869×.** The saving is 85.670875 ms per unit. Mean reduction is 36.792963%. Even the slowest optimized observation beats the fastest baseline by 32.016718%.

This strongly supports a passing runtime result for the measured VM. The measurements were collected in sequential blocks, so they do not eliminate slow environmental drift. The generated report's “improvement > 2× noise” rule is not a statistical significance test. Its warning that raw medians are not directly comparable is also wrong for this pair: the batch sizes match. Quote the recalculated values above, not either heuristic.

The result closely reproduces the earlier time-only flat_pow result (~37.77% reduction); do not combine the samples or substitute a baseline from that older experiment.

## What the hardware counters support

TXT and CSV are **separate five-run perf-stat experiments**, not two representations of one experiment. Each reported event count is a per-process mean. Divide by **16**, not 16×5, to obtain events per 20,000-step unit.

| Event per unit (TXT means) | Baseline | flat_pow | Change | Independent CSV change |
|---|---:|---:|---:|---:|
| Instructions | 1,691,908,480.50 | 1,100,052,938.06 | −34.98% | −34.87% |
| Cycles | 544,894,940.75 | 347,710,616.25 | −36.19% | −36.43% |
| Branches | 193,798,479.81 | 125,845,098.31 | −35.06% | −34.85% |
| Branch misses | 683,655.69 | 585,429.00 | −14.37% | −22.80% |
| L1-data loads | 535,486,803.25 | 351,028,704.19 | −34.45% | −34.58% |
| L1-data load misses | 269,893.00 | 284,681.69 | +5.48% | +9.26% |
| dTLB loads | 266,726,638.31 | 174,726,496.94 | −34.49% | −34.20% |

Both independent batches consistently show substantially less executed work and fewer loads. Instruction savings, cycle savings and clean runtime savings agree in direction and approximate magnitude. This supports avoiding repeated Python container operations and interpreter work.

It does **not** establish a cache-miss optimization. L1 load misses rise slightly while total loads fall. The TXT L1 miss fraction rises from 0.0504% to 0.0811%; it is still small. Likewise branch-miss counts fall less than total branches, so branch-miss rate rises from 0.3528% to 0.4652%. A larger rate is not evidence of a slower program when the denominator and absolute work have shrunk.

IPC computed from the TXT aggregate means rises modestly, 3.1050→3.1637. The dominant effect is fewer instructions, not an extraordinary IPC change. Multiplexing coverage is approximately 40–60%, generic cache-miss measurements are extremely noisy, and LLC events are unsupported. The topdown outputs contain **negative bad speculation** (−73.0% and −75.3%); reject those partitions entirely. They cannot justify calling this “90–94% backend-bound,” memory-bound, or identifying a specific CPU resource as saturated.

Counter and sampling processes include startup/imports and cleanup outside the internal clean timer. Thus counter percentages are supporting evidence, not interchangeable runtime measurements.

## Native profiles: the intended cost largely disappears

Both native profiles use **python3-dbg**, five units (100,000 timesteps), fixed sampling period of 5,000,000 cycles and DWARF unwinding. Folded weights sum to the perf SAMPLE counts exactly: **1,174→726**, a 38.16% decline. Logs do not report lost sample events. Kernel-relocation/BPF synthesis warnings remain; these qualify kernel-symbol interpretation, rather than proving loss of user-space Python samples.

The following counts use *all* folded stacks, normalize `.lto_priv.*` suffixes, and count each sample once for inclusive unions:

| Native path | Baseline samples | flat_pow samples | Interpretation |
|---|---:|---:|---|
| PyObject_GetItem, inclusive | 103 | 1 | Repeated indexed reads largely absent |
| PyObject_SetItem, inclusive | 123 | 1 | Repeated indexed writes largely absent |
| Union of the above | 226 (19.25%) | 2 (0.28%) | −99.12% observed samples in these paths |
| _PyEval_EvalFrameDefault, **self** | 511 (43.53%) | 278 (38.29%) | Less work inside interpreter execution |
| PyFloat_FromDouble, inclusive | 60 | 57 | Float-object creation remains |
| float_dealloc, inclusive | 47 | 52 | Float-object lifetime work remains |
| binary_op1, inclusive | 242 | 219 | Generic arithmetic dispatch remains |
| __ieee754_pow_fma, self | 19 | 20 | Native power calculation remains |

The strongest conclusion is that flattening eliminated most recurring item-access machinery and reduced evaluator work. Self-evaluator samples fall 45.6%; this is not a measurement of function-call overhead alone. The sum of the two item-access paths falls by 224 samples, and evaluator self by 233; these observations should not be converted into an exact release-build causal allocation of saved time.

Float boxing and libm power samples remain roughly similar in absolute count, within sampling uncertainty. Their *relative shares* consequently grow in the shorter profile. This is expected: flat_pow preserves the arithmetic, rather than removing its intermediate floating-point results. Do not claim fewer arithmetic PyFloat allocations merely because state moved to local variables. An allocation counter would be needed to quantify actual object allocation/freelist behavior.

## Why flame graphs can still look similar

Both executions still pass through CPython's evaluator, numeric dispatch and float functions. The graph width is normalized to that profile's total; 726 samples therefore fill the same width as 1,174. Structural similarity can coexist with a substantial reduction in work. In fact the mean native stack depth grows from 41.49 to 52.63 frames because wrapper/import call ancestry changes; it is not evidence that each pair calculation now makes more Python calls.

The legacy `_python.folded` view retains whole native stacks containing interpreter symbols. It keeps 1,174/1,174 baseline samples and 725/726 optimized samples; it is not a Python-function-only flame graph. Differential graphs generated with `difffolded -n` compare relative stack shares after equalizing total weights, not absolute elapsed time.

## cProfile and the remaining bottleneck

Each cProfile run executes one unit and contains exactly one numerical advance call:

- Baseline `advance`: 0.331892 s traced self time.
- Optimized `advance_flat_pow`: 0.205406 s traced self time.

These times are instrumentation-affected and must not replace clean timing. Total process function calls rise 4,911→25,256, mostly from the optimized wrapper's imports/startup and validation. The hot timestep loop still makes one outer Python advance call, so whole-process call counts do not indicate a regression in the numerical kernel.

The remaining cost is a combination of interpreter execution, Python arithmetic dispatch, float-object lifetime handling and native arithmetic. “Pure function-call overhead” is not an adequate diagnosis. Eliminating item access does not imply those remaining categories can be eliminated independently. A hardware proposal should identify an offload boundary that removes enough surrounding interpreter work, and account for data conversion/transfer, rather than promise a system speedup from the native pow self percentage.

## Correctness and provenance limits

All clean processes in both arms report energy `−0.1690801979358367`. The saved optimized correctness gate checks all 30 state components and energy bit-for-bit for **one** 20,000-step unit. Earlier user-provided output verifies the full 16-unit batch, but that manual output is not part of this run's saved gate log. The updated pipeline now verifies its actual selected batch. Energy agreement alone must not be presented as the complete state gate.

The source hash in every optimized raw log matches the reviewed current file. Both manifests record upstream SHA `d1385e816d7cfea361b7915e2cf70138cd6b84f40df8bd5152638851f7bcac2b`. The manifests record revision text `b6f093d` with 13/14 dirty files, and their upstream provenance fields still say UNVERIFIED / not yet extracted. These are saved metadata reads, not new Git commands. The source hash gives stronger kernel identification than the dirty revision, but the run does not preserve a full authenticity-gate transcript or every harness file hash.

The official baseline-only pyperformance artifact separately records pyperformance 1.14.0, pyperf 2.10.0, 20 value-producing workers and 60 values. Its reported mean is 230±3 ms and median 229 ms, close to the clean baseline's 228.25 ms. It warns that stability below 1% has not been established. It supports baseline workload scale; there is no official optimized pyperformance run and no official-harness speedup claim.

## Decision

Use **37.53% clean runtime reduction with bit-exact flat_pow** as the latest full-run nbody result. Retain the grouped result as the earlier limited step in the experiment history. The native profiles now validate the structural explanation, while also correcting prior claims about eliminating float arithmetic/boxing. Keep flat_sqrt as a separate tolerance-based experiment; its timing from another run must not be mixed into this matched pair. The next targeted measurement for small gains is balanced interleaved timing, not another unqualified claim about a single hardware bottleneck.
