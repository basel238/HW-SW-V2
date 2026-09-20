# Raytrace experiment: reuse the shadow ray

This is the first isolated change based on the latest upstream baseline, `results/raytrace_baseline_20260919-220048/`. It changes `variants/bm_raytrace_upstream_opt.py`; the reference in `upstream/` remains unchanged. Full baseline analysis is in `report_raytrace.txt`.

## What changes

For one visibility query, the surface point and light position are constant. The original object loop constructs and normalizes `Ray(p, l - p)` separately for each tested object. The `shadow_ray` kernel constructs it once and passes it to each object. The supplied sphere and halfspace methods only read that ray.

Object order, early exit, the strict `t > EPSILON` rule, floating-point expressions, scene, and materials stay the same. Empty scenes still return visible without constructing a ray. Custom intersection methods that mutate their input ray are outside this optimization's contract.

The kernel is installed only around upstream's own benchmark function and restored even on failure. Setup/restoration is outside its internal timer; rendering and scene construction remain inside. Verification checks baseline method identities and baseline pixels again after each candidate, protecting against accidental contamination of the shared upstream module.

| Kernel | Meaning |
|---|---|
| `upstream` | Unmodified reference |
| `shadow_ray` | Shadow-ray reuse only; new default for the optimized pipeline |
| `guards` | Existing exact-class guard specialization, retained as a separate experiment |

The two optimizations are not combined. The guard experiment narrows general behavior for subclasses and custom predicates; fixed-scene pixel equality does not prove general API equivalence.

## How the evidence leads to this change

1. **Clean timing establishes the cost:** the latest VM baseline median is 792.16625 ms per 100×100 frame, recovered from all 11 valid raw observations. A timing tells us the total cost, not its cause.
2. **Native profiling suggests where to investigate:** the debug interpreter's dispatch, frame, lookup, and object-handling symbols are hot. Flame width represents inclusive samples; a tall stack represents nesting. Neither height nor an ancestor's inclusive width measures its own overhead. Native stacks need Python-level profiling and source inspection to identify application operations.
3. **Python call counts reveal repeated work:** 10,666 visibility queries construct 82,838 shadow rays. The source confirms that their inputs are invariant across the object loop and the supplied intersection methods do not mutate them.
4. **A falsifiable prediction follows:** removing duplicates should eliminate 72,172 Ray constructions and normalizations, plus 144,344 Vector constructions per frame. Pixel bytes must remain identical.
5. **Clean A/B timing must determine the gain:** fewer calls need not produce a proportional speedup. Interpreter version, the remaining work, and host noise all matter.

The baseline native profile uses `python3-dbg`, while timing uses release Python. Its sample percentages cannot establish an exact release-time Amdahl bound. Even for a valid runtime fraction `f`, Amdahl's ideal speedup `1 / (1 - f)` assumes that only that fraction changes, it disappears entirely, and the replacement adds no cost. A source rewrite often changes dispatch, allocation, and arithmetic together. Dividing total instructions by total function calls is not a measurement of function-call overhead.

## Correctness and operation counts

Run from the repository root:

```bash
python3 -B -m unittest discover -s tests -v
python3 -B variants/bm_raytrace_upstream_opt.py --mode verify
```

`verify` checks all three kernels, regardless of `--kernel`, at 24×24, the configured size (default 100×100), and 37×23. It repeats candidates and checks a fresh baseline after each. The focused tests also cover empty scenes, EPSILON boundaries, traversal and early exit, dynamic globals, and patch restoration after exceptions.

The work-count prediction at 100×100 is:

| Operation | Baseline | Shadow-ray reuse |
|---|---:|---:|
| `Scene._lightIsVisible` | 10,666 | 10,666 |
| `Ray.__init__` | 98,172 | 26,000 |
| `Vector.normalized` | 109,887 | 37,715 |
| `Vector.__init__` | 452,955 | 308,611 |

Local validation confirmed these reductions. In `docs/shadow_ray_validation.json`, profiling starts after module loading, so its Vector totals are 452,943 → 308,599: both exclude 12 import-time Vector objects included in the historical full-process profile. The difference is still exactly 144,344. Ray and normalization totals match the table. All three kernels and restored baselines match at 24×24, 37×23, 100×100, 101×97, and 128×128; all 11 focused tests pass.

Count the operations in separate cProfile passes; their elapsed times are not performance results:

```bash
python3 -B -m cProfile -o /tmp/raytrace_upstream.pstats variants/bm_raytrace_upstream_opt.py --kernel upstream --mode raw --loops 1 --no-gc
python3 -B -m cProfile -o /tmp/raytrace_shadow.pstats variants/bm_raytrace_upstream_opt.py --kernel shadow_ray --mode raw --loops 1 --no-gc
python3 -m pstats /tmp/raytrace_upstream.pstats
python3 -m pstats /tmp/raytrace_shadow.pstats
```

Do not enable `--checksum` in a call-count pass: it renders an additional frame. CLI/import totals can differ by interpreter; compare the named rendering operations.

## Target-VM measurements still required

The local tests establish correctness and removed work. They do not establish performance on the Ubuntu/CPython 3.10 VM. Collect a fresh baseline and optimized result under the same conditions; do not compare a new optimized run exclusively with an old session.

For the existing six-phase pipeline, the optimized arm now selects `shadow_ray` by default:

```bash
USE_UPSTREAM=1 ./script_raytrace.sh --variant both --loops 4
```

This produces separated verification, clean timing, counters, native profiles, Python profiles, and suite-baseline artifacts. The pipeline's sequential timing blocks and heuristic comparison are initial diagnostics. The official pyperformance phase runs the installed suite baseline; it does not register or evaluate the `shadow_ray` variant.

For a final performance claim, collect interleaved separate-process measurements with equal work. These are the two arm commands for the recorded one-vCPU VM:

```bash
PYTHONHASHSEED=0 taskset -c 0 python3 variants/bm_raytrace_upstream_opt.py --kernel upstream --mode raw --loops 4 --width 100 --height 100 --no-gc
PYTHONHASHSEED=0 taskset -c 0 python3 variants/bm_raytrace_upstream_opt.py --kernel shadow_ray --mode raw --loops 4 --width 100 --height 100 --no-gc
```

Use the same release executable for both, run at least the previous 11 rounds, alternate which arm goes first, and retain raw outputs for every round. Record source hashes, environment, dimensions, loop count, GC setting, affinity, and explicit kernel. Both arms of every planned round must succeed. Analyze complete paired rounds and preserve pairing when bootstrapping uncertainty. A further session helps check repeatability; more samples cannot remove a systematic design error.

The existing `tools/ab_timing.sh` alternates arms, but currently tolerates failed arms and computes its headline interval by resampling the two groups independently. Its PASS label should not be used as final evidence until that behavior is repaired and checked. This experiment does not change that tool.

Report both `speedup = baseline / optimized` and `time reduction = 100 * (1 - optimized / baseline)`. This project uses time reduction for its declared 7% convention. No claim that the threshold is met is made before target-VM measurements.

## Reports and subsequent experiments

`report_raytrace.txt` and `report_nbody.txt` follow the PDF's six-section TXT format. Their baseline analysis is authored; optimized VM comparison and complete hardware design remain open. `docs/PROJECT_REQUIREMENTS.md` maps the PDF to deliverables, including its hardware wording inconsistency.

The old report generator contains prose about the stand-in workloads. Keep these authored reports: its existing protection redirects output to `.generated.txt` when a report contains no unfinished-template markers. Review generated prose before importing any of it.

After measuring this isolated change, evaluate scalar sphere-intersection temporaries, camera invariants, and guard specialization independently. For nbody, the next source-level question is repeated velocity-list access across pairs; this patch does not change nbody. Choose hardware offload scope from the remaining workload, including conversion and communication cost, rather than equating a debug interpreter symbol with a ready accelerator interface.
