# Latest full raytrace: profile and correctness analysis

## Run identity and scope

Matched new baseline: `raytrace_baseline_20260920-074314_1800`; optimized: `raytrace_optimized_20260920-075734_1800`; session: `session_all_20260920-074308_674`.

The optimized manifest explicitly names `--kernel full`. Recorded optimized SHA-256 `5badaf27f0f9519fd0d2779bd37c745feadcf76e31fbde833cd89dfbb5770d55` matches the current optimized source. Upstream SHA-256 is `88ef4d9060d8e8f6ce40f376477aaf89cc808fa44813225a3071a05a1467f017`. This is the exact full implementation already checked locally; it is not `shadow_ray` or `full_slots`.

The VM correctness log passes all eleven kernels at 24×24,100×100 and 37×23, with same-process baseline restoration. It also passes the full requested four-frame 100×100 batch byte-for-byte. The production-resolution checksum prefix is `11f2c36b02044f11`.

Both cProfile artifacts cover one 100×100 frame. Both native captures cover one frame under `python3-dbg` 3.10.12, fixed 5,000,000-cycle sampling and DWARF 8 KiB stacks. Thus counts/samples compare equal work. Clean timing is separate: root analysis reports 791.2145→452.69625 ms/frame (42.78% reduction); none of the traced or sampled elapsed times replaces it.

Historical shadow evidence is from 012836/014248. Its call counts are useful for mechanism comparisons, but its native samples and timing are a different run block, not a controlled extra ablation in this session.

## What work disappeared

| Event, per profiled frame | New upstream baseline | Earlier shadow-only | New full |
|---|---:|---:|---:|
| Sphere queries | 179,457 | 179,457 | 179,457 |
| Plane queries | 25,501 | 25,501 | 25,501 |
| Ray construction | 98,172 | 26,000 | 26,000 |
| Vector construction (includes 12 startup) | 452,955 | 308,611 | 105,497 |
| Point subtraction | 277,865 | 205,693 | 26,236 |
| Dot calls (includes 2 startup) | 509,873 | 437,701 | 78,787 |
| Vector.scale | 149,747 | 77,575 | 53,918 |
| Normalization | 109,887 | 37,715 | 37,715 |
| mustBeVector | 520,543 | 448,371 | 4 |
| Point.isPoint | 277,865 | 205,693 | 0 |
| Vector.isPoint | 20,000 | 20,000 | 0 |
| Intersection list comprehensions | 15,265 | 15,265 | 0 |
| firstIntersection | 15,265 | 15,265 | 0 |
| rayColour | 15,333 | 15,333 | 15,333 |
| Visibility queries | 10,666 | 10,666 | 10,666 |
| Pixel plots | 10,000 | 10,000 | 10,000 |

The raw constructor/method counts include a few import-time calls; their reductions cancel these common startup events. There are 12 startup Vector constructions and 2 startup original dot calls. In full, the four remaining `mustBeVector` calls occur during upstream module import/assertions, not the optimized render.

The count deltas match the source mechanisms exactly:

- **Shadow reuse:** 72,172 fewer Rays, normalizations and light-minus-point subtractions; 144,344 fewer Vectors. The full kernel retains precisely the earlier shadow reduction.
- **Scalar spheres:** 179,457 centre-minus-origin Vector creations and 358,914 dot calls disappear. Every sphere test still executes. There is no BVH, approximation or skipped scene geometry.
- **Camera reuse:** 20,000 per-pixel `scale` calls become 100 horizontal plus 100 vertical scales, removing 19,800 Vector allocations and scale calls per frame.
- **Checkerboard:** 3,857 discarded scale allocations/calls disappear. Reciprocal and multiplication operations still execute; the upstream ignored-scale behavior and zero-size exception are preserved.
- **Total Vector reduction:** 144,344+179,457+19,800+3,857 =347,458, exactly 452,955−105,497. This is 76.71% fewer Vector constructor calls, not 76.71% less runtime or float-result allocation.
- **Nearest scan:** 15,265 complete intersection-list constructions and 15,265 `firstIntersection` calls disappear. The replacement still tests every object, retains strict EPSILON and first-tie behavior, and creates only current-best tuples.
- **Guards:** the per-render polymorphic predicate/guard calls vanish for stock operands; type checks and fallback machinery replace them. This is not removal of every type-related cost.

Sphere/plane evaluations, visibility queries, recursive ray-colour calls and pixel count are unchanged. These invariants plus exact images support “same workload, less representational and control overhead.”

Whole-process cProfile recorded 3,092,309→881,684 call events (71.49% fewer). These totals include Python/C calls and startup work; they are not a 71.49% runtime forecast or a fixed cost per Python function call. The full implementation adds 26,000 `stock_scene` calls and 26,002 `id` calls to preserve its specialization boundary. Most scene checks hit the render-local eligibility cache, but they still cost work.

## Native evidence and why the flames retain their shape

Folded weights total 1,061→552 samples, a 47.97% decrease in the debug sampling runs. The former baseline 1073 and shadow 823 samples offer historical context; direct full-versus-shadow native percentage comparisons are not controlled runtime evidence.

Selected native **self** counts below sum repeated native symbol leaves across all stacks. `.lto_priv` suffixes are normalized for grouping; no inclusive percentages are added together.

| Symbol | New baseline samples (self share) | Full samples (self share) |
|---|---:|---:|
| `_PyEval_EvalFrameDefault` | 263 (24.79%) | 174 (31.52%) |
| `call_function` | 45 (4.24%) | 22 (3.99%) |
| `frame_dealloc` | 34 (3.20%) | 14 (2.54%) |
| `_PyEval_MakeFrameVector` | 33 (3.11%) | 13 (2.36%) |
| `_PyType_Lookup` | 29 (2.73%) | 6 (1.09%) |
| `_PyObject_GetMethod` | 22 (2.07%) | 4 (0.72%) |
| `_PyDict_GetItemHint` | 26 (2.45%) | 24 (4.35%) |
| `PyFloat_FromDouble` | 8 (0.75%) | 7 (1.27%) |

Frame creation/destruction symbols as a disclosed heuristic group fall 89→33 samples; dictionary/attribute-support symbols fall 184→87 samples. These are finite sparse observations under a debug interpreter, not exact release-time components or Amdahl fractions. The JSON includes the actual symbol membership, so the grouping is auditable.

The evaluator takes fewer samples (263→174) while its share increases 24.79%→31.52% because the overall program became shorter. `_PyDict_GetItemHint` shows a similar relative rise without an absolute increase. A larger percentage after optimization does not establish a regression. Nor does `PyFloat_FromDouble` 8→7 prove float allocation stayed precisely constant: these counts are too small, and constructor elimination does not by itself eliminate scalar float results.

The renderer continues to run in CPython and to recurse for reflections. Therefore its native stack still contains evaluator/vectorcall/frame routines. Removing many calls changes how often their paths execute; it does not replace all paths with a different stack vocabulary. The average observed stack depth changes 68.08→64.86, not to a shallow native numerical loop. Flame widths normalize each run to 100%; `difffolded -n` also compares normalized stack shares. These plots cannot directly show total time saved without the clean-timing and equal-work sample totals beside them.

Both native reports state zero lost samples, but `[unknown]` occurs somewhere in 240/1061 baseline and 88/552 full stacks. That does not mean every such sample is unusable—the resolved leaf can still be known—but complete ancestry is unavailable for those stacks. Kernel relocation/BPF synthesis warnings also appear; do not present these as complete kernel/Python-language call graphs. The `_python.folded` view is a filtered native-stack view, not Python function attribution.

## Remaining software costs and the attribution trap

The optimized scalar `sphere` is now the largest cProfile self-time entry: 179,457 calls, 0.295462207 s self, 0.296459364 s inclusive. The old sphere method was 0.230929015 s self but 0.781395130 s inclusive. **Its increased self time is expected:** subtraction/dot operations moved into its own body, so work formerly attributed to child methods is now charged to `sphere`. Inclusive cost decreases strongly in this tracing run. That is evidence of the inlining/scalarization mechanism, not a regression.

The full traced process totals 0.912307464 s. Sphere self/inclusive time is about 32.4/32.5% of that traced total; this fraction must not be inserted as the removed fraction in a release-runtime hardware forecast. cProfile penalizes call-heavy code differently, and the timed process includes setup outside the workload timer.

Other remaining traced entries include:

- `ray_colour`: 15,333 calls, 0.080029218 s self, 0.754412863 s cumulative.
- `visibility`: 10,666 calls, 0.052290114 s self, 0.244801634 s cumulative.
- `SimpleSurface.colourAt`: 5,333 calls, 0.045071521 s self, 0.546454879 s cumulative.
- Vector construction 105,497 events, remaining dot 78,787 events, scale 53,918 events and normalization 37,715 events.

These cumulative totals overlap because shading recursively calls ray colouring and visibility. They cannot be summed into independent workload percentages. The current evidence suggests remaining sphere arithmetic/attribute access plus ray traversal/shading/normalization are useful code regions to study. It does not identify one proven limiting CPU execution resource. The evaluator encompasses bytecode arithmetic, references, branches and other operations; it is not solely a dispatch toll.

## Hardware: a measured query mix, but still an estimated offload gain

The caller map for `math.sqrt` resolves an important modeling assumption:

- 6,934 calls originate from scalar `sphere`.
- 37,715 originate from `magnitude`.
- One originates from importing `random`.

Therefore the current sphere workload has **6,934/179,457 =0.03863878254958012 (3.8639%) nonnegative discriminants**, and 172,523 misses. The full, shadow-only and baseline profiles agree on these counts. Do not mistake the total 44,650 square roots for root-bearing sphere queries or report 6,935 by forgetting the import call.

Sphere calls split 106,855 from nearest-hit ray colouring and 72,602 from visibility. These are the actual current CPU query counts. A future batching design may evaluate queries which the current visibility early exit avoids, changing both N and the root-bearing fraction. Preserve object-order reduction and report the new batch work explicitly.

Using this measured query mix, the existing analytical 20 cycles/miss and 80 cycles/root budgets average 22.318326953 cycles/query. At an assumed 50 MHz this is 80.1036 ms/core time per frame. With the existing assumed transfer/launch/native-packing costs 38.369228 ms, offload totals 118.472828 ms. Against the new 452.69625 ms full software, modeled break-even requires removing 26.17049% of release runtime. This is still a sensitivity model, not a measured gain: no device timing, transport or integrated renderer exists; 100 ns native packing/query and the 50 MHz target are assumptions. The traced sphere fraction does not establish the required release-time fraction.

The low root fraction strengthens the case for a cheap early discriminant rejection and weakens a proposal centered only on a faster square root. Of 179,457 sphere queries, 96.136% already skip sqrt. Arithmetic should be offloaded as a whole primitive/batch boundary to avoid per-operation Python/device calls. Compare against a compiled CPU implementation using the same batch boundary before attributing benefits to hardware.

## What this full run cannot rank

The full run proves the combined implementation is faster and exact for the recorded gates. Counts independently demonstrate the intended removals. It does not quantify separate marginal runtime contributions from guards, scalar sphere work, camera caching, nearest scanning and checkerboard changes. Their interactions overlap. The earlier shadow-only target run and local Mac ablation provide context, but they do not replace target same-session ablation. Keep `full` as the exact original-class bundle and `full_slots` optional; no new target evidence ranks slots here.
