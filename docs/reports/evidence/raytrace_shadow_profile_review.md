# Latest raytrace shadow-only profile review

Inputs: `raytrace_baseline_20260920-012836` and `raytrace_optimized_20260920-014248`. Both cProfile logs and native record logs say 100 × 100 and loops=1. Optimized logs explicitly say kernel=shadow_ray. Native profiler uses python3-dbg, cycles, fixed period 5,000,000; cProfile uses release interpreter tracing. Neither instrument's elapsed time is the grading runtime.

## Exact call-count evidence

Raw whole-process cProfile counts below; since both runs render one frame, render-related changes are directly per-frame changes. Import activity remains included. All observed changes match shadow reuse exactly.

| Function | Baseline | Shadow | Removed |
|---|---:|---:|---:|
| Scene light visibility query | 10,666 | 10,666 | 0 |
| Ray.__init__ | 98,172 | 26,000 | 72,172 |
| Ray.__init__, called from light visibility only | 82,838 | 10,666 | 72,172 |
| Vector.normalized | 109,887 | 37,715 | 72,172 |
| Vector.magnitude | 109,887 | 37,715 | 72,172 |
| Vector.scale | 149,747 | 77,575 | 72,172 |
| Vector.dot | 509,873 | 437,701 | 72,172 |
| Vector.mustBeVector | 520,543 | 448,371 | 72,172 |
| Point.__sub__ | 277,865 | 205,693 | 72,172 |
| Point.isPoint | 277,865 | 205,693 | 72,172 |
| Vector.__init__ | 452,955 | 308,611 | 144,344 |
| math.sqrt | 116,822 | 44,650 | 72,172 |
| Sphere.intersectionTime | 179,457 | 179,457 | 0 |
| Halfspace.intersectionTime | 25,501 | 25,501 | 0 |
| Scene.rayColour | 15,333 | 15,333 | 0 |
| firstIntersection / intersection list comprehension | 15,265 | 15,265 | 0 |
| colourAt / visibleLights | 5,333 | 5,333 | 0 |

Vector constructor includes 12 import-time constructions in each profile: actual frame workload is 452,943 → 308,599. The two module-level reflection assertions also account for 2 dot calls, 4 scale calls and 4 mustBeVector calls in each profile. math.sqrt includes one random-module import call. These fixed additions cancel in differences.

The geometry workload is unchanged, as expected. Each visibility query formerly visited 7.7665 objects on average (82,838 / 10,666), constructing an identical normalized shadow ray for each. Now it constructs one per query, while still performing the same object intersection tests and early exits. This removes 87.1% of shadow-ray constructions, 73.5% of all Ray constructions, and 65.7% of normalizations. The two Vector objects per redundant ray are the light-minus-point vector and the scaled normalized vector.

Each eliminated redundant ray removes ten Python calls (counting two Vector constructors) plus one C math.sqrt call: 721,720 Python calls and 72,172 sqrt calls, 793,892 total render-related calls. Whole-process total falls 3,092,298 → 2,299,196 (793,102 fewer, 25.65%); total Python calls fall 2,885,140 → 2,163,807 (25.00%). The difference of 790 calls from the render prediction is small extra wrapper/import/setup work, not a mismatch in ray reuse. A percentage of call counts is not a percentage of runtime.

The optimized pstats identifies the replacement as `_shadow_light_is_visible` at variant line108, while baseline identifies `_lightIsVisible` at upstream line283. Compare those as equivalent functions, not as unrelated added/deleted work. Profiling moved the visibility helper but did not remove its 10,666 invocations. Visibility cumulative cProfile time is 0.904444577s → 0.430299468s; self is 0.122555378s → 0.053669843s. This is qualitative tracing attribution only, not release-runtime savings or an Amdahl bound.

## Native samples: broad corroboration, not exact cost accounting

There are 1,073 baseline and 823 optimized samples. Both sampled one frame with fixed 5M-cycle period, so the optimized record has 23.30% fewer cycle samples per frame. Whole-process debug interpreter cycle estimate is 5.365b → 4.115b. This broadly corroborates less CPU work, but is not an independent release-runtime speedup measurement.

| Native symbol, self samples | Baseline count (%) | Optimized count (%) |
|---|---:|---:|
| _PyEval_EvalFrameDefault | 320 (29.82%) | 227 (27.58%) |
| call_function.lto_priv.0 | 47 (4.38%) | 22 (2.67%) |
| frame_dealloc.lto_priv.0 | 33 (3.08%) | 27 (3.28%) |
| _PyEval_MakeFrameVector | 29 (2.70%) | 22 (2.67%) |
| _PyObject_GetMethod | 15 (1.40%) | 17 (2.07%) |
| _PyType_Lookup | 22 (2.05%) | 8 (0.97%) |
| PyFloat_FromDouble | 13 (1.21%) | 6 (0.73%) |
| _PyMem_DebugCheckAddress | 23 (2.14%) | 12 (1.46%) |

A larger percentage need not mean more total work: frame_dealloc share increases while its sample count decreases. _PyObject_GetMethod's 15 → 17 samples is a two-sample fluctuation, not convincing evidence of an actual regression. Also frame_dealloc inclusive samples are 76 → 77, despite fewer known calls; this illustrates sampling variability, descendants' costs and weak precision for small individual categories. No hard Amdahl limits should be inferred from these single debug profiles.

Interpreter dispatch remains the largest self symbol because unchanged geometry is still Python code. This optimization avoids dispatch, method lookup, allocation/refcount operations and normalization arithmetic together; it does not accelerate any native symbol in isolation.

## How to read the flamegraphs and top30

- Top30 baseline covers 297/1,073=27.68% of samples; optimized covers244/823=29.65%. It is not a complete profile. Baseline has 23 distinct top30 stacks ending at eval, totaling264 samples; optimized has17 such stacks totaling195. The full eval leaf totals are320 and227. Repeating eval/call sequences identify interpreter call chains at different depths, not separate categories to add.
- Raw native stacks contain[unknown] somewhere in227/1,073=21.16% baseline samples and179/823=21.75% optimized samples. Only7 and8 respectively end at[unknown]. Most affected stacks still resolve their leaf but have incomplete/unresolved ancestors. Zero lost samples does not mean perfect unwind/symbol quality.
- Average folded native stack depth is67.30→69.25 and mean active eval frames9.704→10.135. This does not mean the optimization made more function calls: stack depth describes simultaneous nesting, not total calls. The optimized path includes an extra `_bench_shadow_ray` wrapper, and startup/patch setup is in process profiles though outside the internal benchmark timer. Smaller total work and a changed mixture of stacks also change average depth.
- `*_python.folded` is produced by grepping entire native stack lines for Python-related symbols. All1,073 baseline and823 optimized lines' sample weights survive. Thus the “Python frames only” SVG is actually the same native profile, not a Python-source-named flamegraph and not an independent py-spy measurement. No py-spy output artifact exists in this selected pair.
- tools/compare.sh invokes `difffolded.pl -n`, normalizing total sample counts to equal size. This compares relative shares, not absolute cycles/frame. Both runs already contain one frame, so this normalization removes the overall23.3% reduction from the visual scale. Red regions can mean increased share or an exact stack appearing only on the optimized path; they do not by themselves establish a slowdown. Wrapper stack changes, partial unwind and low counts also make exact-stack matching fragile. The title “red = more time in optimized” is too strong for this normalized diff.
- Both full SVGs fill a fixed horizontal canvas; 100% baseline and100% optimized are different totals. Consult raw sample counts and release timings alongside widths.

## Residual targets

Sphere intersection remains179,457 calls per frame and calls dot twice per intersection:358,914 dot calls, around82.0% of the remaining437,699 workload dot calls. It also still creates179,457 centre-minus-ray-point Vectors. This is the next strong source-level optimization hypothesis (scalar coordinate arithmetic preserving expression order), independently of the present runtime result. Camera scaling and visible-light normalization likewise remain. None is yet demonstrated by this run.

Machine-readable evidence: profile_evidence.json (full cProfile records/callers, native self and set-based inclusive counts), top30_evidence.json (all top30 rows, leaf/depth metadata). Inclusive native counts count a sample once per symbol even if recursive; do not add them to self or other inclusive categories.
