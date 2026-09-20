# Raytrace: exact combined optimization experiment

## Decision and evidence status

The optimized wrapper now defaults to **`full`**, combining the compatible pure-Python changes described below. The upstream file and baseline wrapper remain unchanged. Historical kernels remain available for reproducing earlier experiments and separating causes.

The newest target-VM session, `session_all_20260920-074308_674`, now measures
**full**: 791.2145 -> 452.69625 ms/frame, **42.7846% lower runtime** (1.7478x).
The pair is `raytrace_baseline_20260920-074314_1800` /
`raytrace_optimized_20260920-075734_1800`. Eleven processes per arm run four
frames each. All 22 raw timing values match their CSV entries; saved full-batch
verification is bit-identical, and captured source hashes match this code.
Keep full as a bundle. A new VM ablation is still needed to rank its components.

The earlier evidence sets remain useful history:

- **Target Ubuntu VM, shadow-only:** the recorded baseline and optimized runs reduced median runtime from 789.7555 to 611.02275 ms/frame: **22.6314% less runtime**, with bit-identical images. Those runs were `raytrace_baseline_20260920-012836` and `raytrace_optimized_20260920-014248`; the comparison is `comparison_raytrace_20260920-015451`. This result establishes the benefit of shadow-ray reuse, not the new `full` kernel.
- **Local Mac, new candidates:** the exploratory ablation below supports further testing. It is not a VM measurement, does not update the target result, and cannot substitute for the target's clean timing or native profiles.

The repository's [local ablation samples](evidence/raytrace_full_local_ablation.json) and [correctness evidence](evidence/raytrace_full_correctness.json) preserve the source hashes, test commands, results and assumptions. New `full` target evidence is recorded in `docs/reports/evidence/session_074308_raytrace_analysis.json`. `full_slots` has no new target runtime result.

## What the latest profiles establish

The geometry workload is preserved: sphere tests 179,457; plane tests 25,501;
visibility queries 10,666; ray-colour calls 15,333; and 10,000 output pixels.
Vector constructions fall from 452,955 to 105,497. The 347,458 removed objects
are exactly accounted for by shadow reuse (144,344), scalar sphere calculations
(179,457), camera reuse (19,800), and the discarded checkerboard result (3,857).
Dot calls fall 509,873 -> 78,787; total traced calls fall 3,092,309 -> 881,684.
These are exact work counts, not isolated timing contributions.

Release perf counting corroborates less executed work: instructions -43.70%,
cycles -41.87%, L1 data loads -44.18% in the TXT batch; the independent CSV
batch agrees in direction and scale. Native debug samples fall 1,061 -> 552
for one frame. Evaluator self samples fall 263 -> 174 while its share rises
24.79% -> 31.52%. The same interpreter frames remain in normalized-width flame
graphs, explaining similar shapes despite less work. Debug percentages are not
release-runtime Amdahl fractions; cProfile self time moves into inlined sphere
code while its cumulative time decreases.

The current full median is 25.91% below the historical shadow-only median.
That is a cross-session comparison, not an isolated same-session ablation.
Guards and checkerboard had small negative isolated local results; this new
bundle result does not overturn those observations or prove all components win.
Optional slots remains outside the default contract.

Only 6,934 sphere calls reach sqrt: 3.8639% of all sphere tests. This now informs
the hardware estimate. It does not imply that a sqrt-only accelerator would
remove the remaining interpreter work. See HARDWARE_DESIGN.md.

## What each kernel changes

| Kernel | Work removed or reused | Numerical/behavioral constraint |
|---|---|---|
| `upstream` | None; reference workload | Original implementation |
| `guards` | Redundant polymorphic predicates for exact stock operands | Same arithmetic; subclasses and custom operands call the original method |
| `shadow_ray` | Repeated construction and normalization of the same shadow ray for each object in a visibility query | Historical contract assumes read-only intersection methods; preserves object order, early exit and strict `t > EPSILON` |
| `combined` | `guards` plus `shadow_ray` | Both contracts apply |
| `sphere_scalar` | Temporary centre-to-origin Vector and its dot-product calls | Same subtraction, multiplication, addition, discriminant and square-root order; non-stock types fall back |
| `camera` | Identical horizontal camera-vector work across rows and identical vertical work across columns | Horizontal components are computed once per column; vertical component once per row; `(eye + xcomp) + ycomp` and Ray normalization remain unchanged |
| `nearest_hit` | Complete intermediate intersection list, most result tuples and a second traversal | Every primitive is evaluated; strict eligibility `t > -EPSILON`; first equal-distance hit wins; recursion bookkeeping unchanged |
| `checkerboard` | Unused Vector allocation and `scale()` call | Retains reciprocal and component multiplications, including exceptions; does not apply the discarded result |
| **`full`** | Safe guard paths, safe shadow reuse, scalar spheres, camera reuse, nearest-hit scan and checkerboard change | Original Point/Vector/Ray classes retained; all stock benchmark image/state checks exact |
| `slots` | Instance dictionaries on newly constructed Point/Vector/Ray objects | Optional replacement classes with fixed fields; restricted to freshly constructed stock scenes |
| `full_slots` | `full` plus `slots` | Same optional fresh-scene class-replacement restriction |

The scalar sphere expression retains upstream's exact evaluation structure:

```python
v = (cp_x * rv.x) + (cp_y * rv.y) + (cp_z * rv.z)
discriminant = (radius * radius) - (
    ((cp_x * cp_x) + (cp_y * cp_y) + (cp_z * cp_z)) - v * v)
# Same negative-discriminant branch, then:
t = v - math.sqrt(discriminant)
```

This removes Python vector objects and helper calls, **not** the floating-point calculations themselves. Python arithmetic continues to produce boxed float results. Neither arithmetic reassociation nor approximate square roots are used.

The nearest-hit implementation keeps the current best candidate instead of creating all `(object, t, surface)` tuples. It still evaluates objects that cannot win. Skipping those evaluations could change side effects or exception behavior. Custom primitive/surface classes use the original scene method rather than the stock fast path.

The `full` visibility implementation similarly falls back to upstream for custom scenes, including a primitive that mutates its incoming ray. For stock scenes, eligibility is established during rendering and shared by the scene operations; that avoids repeating the complete class check for every visibility and colour query. Camera caches and eligibility bookkeeping are inside the timed render.

## Exactness contract and retained upstream behavior

The required default contract is exact results for the supplied benchmark workload, including every frame of the requested measurement batch. Additional tests exercise varied stock scenes, primitive results and fallback behavior. These tests provide evidence; they are not a proof of equivalence for arbitrary Python objects.

The stock fast paths assume ordinary upstream numeric fields and no concurrent or monkey-patched scene mutation. Custom subclasses/operands take original methods where their semantics would otherwise be bypassed. Arbitrary instance-level monkey-patching of stock classes is not covered by the specialization contract.

Several tempting changes are deliberately excluded:

- The upstream checkerboard calls `v.scale(...)` but discards its returned vector. Applying the scaled coordinates would change the reference image. The optimized version preserves the ignored result and still raises for a zero check size.
- The shadow test accepts any intersection beyond its strict EPSILON threshold; it does not limit the blocker distance to the light. That physical-model issue is preserved.
- The original Halfspace intersection formula is preserved.
- No floating-point expression reassociation, approximate arithmetic, changed recursion depth, reduced resolution, or reduced scene complexity is used.
- No compiled numerical library was introduced; the agreed software track remains pure Python.
- A bounding-volume hierarchy was not added. With eight supplied primitives, its management overhead and ordering contract require a separate measured design; there is no evidence here that it would win.

`slots` and `full_slots` remain optional even though their measured images match. Replacing classes changes class identity; instances lose `__dict__` and weak-reference support, and existing instances/subclasses still belong to the old classes. Therefore they are appropriate fresh-scene storage experiments, not the default public-class contract. `full` keeps the original classes.

Patches are installed only around the upstream benchmark function and restored in reverse order, even on exceptions. Patch construction/restoration is outside upstream's internal timer. Original scene construction, rendering, camera precomputation, allocations and all per-frame work remain inside it. No rendered images are cached across frames.

## Correctness evidence

The recorded run passed **24 targeted tests** in `tests/test_raytrace_full.py` and `tests/test_raytrace_shadow.py`, plus the explicit verification command below. Pipeline tests are separate and are not included in this count.

Coverage includes:

- All eleven kernels at 24×24, 100×100 and 37×23, compared with a baseline rendered before patching and again after restoration.
- All four frame buffers of a `full` 100×100 batch, compared byte-for-byte with both upstream batches; checking only the last image would not establish this.
- 1,000 deterministic randomized sphere cases and 36 geometric edge cases, comparing packed IEEE-754 distance-result bits, including misses, tangent cases, origins inside/behind spheres and signed-zero inputs.
- Ten varied scenes across all kernels: empty/no-light scenes, different sphere counts, reflective coefficients, checker sizes and nonsquare images.
- Raw pixel-colour component bits before 8-bit quantization, for `full` and `full_slots` in four varied scenes. Image hashing alone could conceal small floating-point differences.
- Primary camera-ray position/direction component bits.
- Equal-distance ties, strict EPSILON behavior, all object visits and recursion-depth restoration.
- Custom guard/predicate and point subclasses; mutating custom shadow primitives; zero checker-size exceptions.
- Restoration of every patched method/class after success and exceptions, including baseline integrity in the same process.

Recorded source SHA-256:

```text
upstream/bm_raytrace_upstream.py
88ef4d9060d8e8f6ce40f376477aaf89cc808fa44813225a3071a05a1467f017

variants/bm_raytrace_upstream_opt.py
5badaf27f0f9519fd0d2779bd37c745feadcf76e31fbde833cd89dfbb5770d55
```

These hashes identify the tested revision; future edits require fresh verification.

## Exploratory local ablation — not the target VM

Environment: macOS 26.5.2, ARM64, release Python 3.14.6. Each sample contains two 100×100 frames, with garbage collection disabled. Eleven repetitions rotate the order of all eleven kernels, so each kernel occupies every order position once. These are within-process exploratory measurements, not the clean separate-process VM pipeline. No profiler is active.

| Kernel | Median seconds per two frames | Runtime reduction versus local upstream |
|---|---:|---:|
| upstream | 0.238014 | — |
| guards | 0.241141 | −1.31% |
| shadow_ray | 0.186469 | 21.66% |
| combined | 0.188221 | 20.92% |
| sphere_scalar | 0.203174 | 14.64% |
| camera | 0.235474 | 1.07% |
| nearest_hit | 0.232920 | 2.14% |
| checkerboard | 0.240981 | −1.25% |
| **full** | **0.146256** | **38.55%** |
| slots | 0.230276 | 3.25% |
| full_slots | 0.143267 | 39.81% |

Positive reduction means faster; a negative value means slower. Reductions are `1 − candidate_median / upstream_median`. The full combination must be measured directly: individual effects overlap and cannot be added.

The small isolated changes are comparable to measurement variability: sample coefficients of variation are roughly 1.6–2.1% for most candidates and 5.5% for checkerboard. Thus the small regressions/gains do not establish a universal ranking. Safe guard fallback checks themselves cost work, explaining why removing method calls need not improve every interpreter/workload. The full-versus-full_slots difference also deserves a target comparison before deciding to accept the storage contract change.

The combined result supports the hypothesis that vector temporaries, repeated camera work, calls and container traversal are worthwhile targets. It does not establish the remaining VM hardware bottleneck, the contribution of each component within `full`, or an accelerator's achievable speedup. The new optimized profiles and revised transfer/latency model narrow those questions; a measured release offload boundary and isolated VM ablations remain necessary.

## Reproduction on Ubuntu

Run from the repository root after transferring the updated source. These commands do not modify upstream.

```bash
# Exact tests, including fallback and restoration checks.
python3 -B -m unittest discover -s tests -p 'test_raytrace_full.py' -v
python3 -B -m unittest discover -s tests -p 'test_raytrace_shadow.py' -v

# All independent image gates plus every selected production-batch frame.
python3 -B variants/bm_raytrace_upstream_opt.py \
  --mode verify --kernel full --loops 4 --width 100 --height 100

# First obtain clean target runtime without profiling overhead.
USE_UPSTREAM=1 ./script_raytrace.sh \
  --variant both --kernel full --loops 4 --time-only

# Then collect the full baseline/optimized workflow and explanatory profiles.
USE_UPSTREAM=1 ./script_raytrace.sh \
  --variant both --kernel full --loops 4

# Independent candidate comparison; retain raw samples and source hashes.
python3 -B variants/bm_raytrace_upstream_opt.py \
  --mode ablate --loops 2 --reps 11 --width 100 --height 100 --no-gc \
  --json raytrace_full_ablation.json
```

`--mode ablate` does not replace the correctness gate or clean pipeline. Use the release interpreter for quotable timing. Debug-interpreter native profiles support attribution only and their sampled percentages should not be treated as exact release-time fractions.

To evaluate optional storage changes, first run verification with `--kernel full_slots`, then select that kernel explicitly in the timing/profiling script. Keep its result directory and manifest separate from `full` and the historical `shadow_ray` result. Inspect the recorded kernel, workload size, Python version and hashes before comparing runs; do not infer the implementation from the word “optimized” alone.
