# Nbody: retain the first body's state across consecutive pairs

The implemented experiment is `grouped` in
`variants/bm_nbody_upstream_opt.py`. It is now the default optimized kernel.
The files under `upstream/` and the baseline wrapper
`bench/bm_nbody_upstream.py` are unchanged. Existing `upstream`, `sqrt`, `hoist`,
and `full` selections remain available; grouping is not combined with the square
root rewrite.

## Why test this change?

The selected baseline is `results/nbody_baseline_20260919-222849/`, with a clean
median of **227.247625 ms per 20,000-step unit** from 11 independent 16-unit
processes. The report explains recovery of the malformed historical CSV from
the intact raw `RESULT` lines.

Three observations motivate the experiment:

1. `cProfile` identifies `advance` as the main Python-level region.
2. Debug-Python native samples contain interpreter execution, float handling,
   and the `PyObject_SetItem -> list_ass_subscript -> list_ass_item` path.
3. The reported L1 data-load miss rate is approximately 0.05%. Cache misses are
   not the strongest demonstrated problem, but cached Python container access
   still needs instructions, indexing, reference handling, and assignment.

This evidence supports reducing Python list operations. It does not establish
that list operations are the only bottleneck, that the full inclusive width of
`PyObject_SetItem` is independently removable, or that a particular fraction of
release runtime will disappear. The native profile uses a debug interpreter;
the virtualized PMU's negative top-down percentages are unusable.

## What changes in the loop?

The upstream ten-pair order has four consecutive groups:

```text
Sun:      Jupiter, Saturn, Uranus, Neptune
Jupiter:  Saturn, Uranus, Neptune
Saturn:   Uranus, Neptune
Uranus:   Neptune
```

In upstream, a first body's position is unpacked again for each partner, and
each velocity component is read and written for each pair. `grouped` loads the
first body's position and velocity once at the beginning of a group. It applies
each velocity increment to the local values sequentially, then writes those
three values back at the group's end. The second body's velocity is updated
immediately for every pair, just as in upstream.

Groups contain references to the current run's body records, not copies of the
state. They are constructed once per `advance` invocation, before its timestep
loop, **inside the upstream benchmark's timed region**. With 16 benchmark loops
there are 16 such constructions; the setup cost is included rather than hidden
in an untimed global cache. State continues across those loops, and each
benchmark invocation starts from a fresh module as before.

This preserves the original displacement expressions, power expression
`dt * ((dx * dx + dy * dy + dz * dz) ** (-1.5))`, mass multiplications, pair order,
and sequential component updates. Positions are still updated only after all
pairs in the timestep have been processed. No force contributions are summed
first, and no floating-point reassociation or approximation is introduced.

Reloading at each group's start matters: when Jupiter becomes the first body,
it already has the contribution received as the Sun's second body. Retaining
one body's state across its consecutive partners is safe for this benchmark's
ordinary lists and distinct body records; it is not a claim about arbitrary
aliased or side-effecting replacement containers.

## How much source-level work is removed?

Count numeric position/velocity component reads and writes, including reads
performed by unpacking. Do not count these as machine instructions or cache
misses.

| Per timestep | Upstream | Grouped | Removed |
|---|---:|---:|---:|
| Pair-phase position reads | 60 | 42 | 18 |
| Pair-phase velocity reads | 60 | 42 | 18 |
| Pair-phase velocity writes | 60 | 42 | 18 |
| Whole-step component reads | 150 | 114 | 36 |
| Whole-step component writes | 75 | 57 | 18 |

The force phase has ten second-body visits and four first-body groups, so the
grouped count is `(10 + 4) * 3 = 42` for each of its three categories. Position
updates still add 30 reads (15 velocity and 15 position) and 15 writes per step.
Over 20,000 steps the total reduction is **720,000 reads and 360,000 writes**.
Over a 16-loop batch, it is 11,520,000 reads and 5,760,000 writes.

The older `hoist` kernel changes how per-pair component accesses are expressed
but still reloads and writes both bodies for every pair. `grouped` actually
removes accesses by carrying values across consecutive partners.

The new outer group loop and group setup have costs. Python float arithmetic,
numeric dispatch, and temporary arithmetic results remain. The 24% reduction
in these whole-step component-access counts is **not a 24% runtime prediction**.

## Correctness and reference isolation

Run from the repository root:

```bash
python3 -B -m unittest discover -s tests -v
python3 -B variants/bm_nbody_upstream_opt.py --mode verify --loops 16 --iterations 20000
```

`verify` runs every registered kernel on its own fresh upstream state at the
requested loop and iteration counts. `grouped` must produce finite outputs and
bit-identical energy and all 30 position/velocity components. Existing legacy
kernels keep their `1e-9` relative tolerance contract; the state metric uses the
largest reference component as its common scale rather than separate
per-component relative tolerances. The square-root variants can change rounding.

Use explicit `--loops 16` before collecting the 16-loop measurement. The pipeline
verification phase currently defaults to one loop and does not inherit its
timing `--loops` option. Testing only a one-loop state would not check the
320,000-step state reached at the end of the intended measured batch.

`tests/test_nbody_grouped.py` covers the grouping mechanism, fresh-state binding,
reference isolation, and numerical comparisons. Independent checks of the new
implementation matched all 30 state components and energy bit-for-bit for
`(loops, steps-per-loop)` equal to `(1, 1)`, `(1, 10)`, `(1, 20000)`,
`(4, 20000)`, and `(16, 20000)`. Instrumented component-list checks confirmed
the per-step access counts above. All 13 focused nbody regression tests pass;
the full suite passes 24 tests including the 11 existing raytrace checks.
The explicit 16-loop CLI verification also passes all kernels: `grouped` is
bit-exact, `hoist` has zero measured error, and `sqrt`/`full` stay within their
legacy tolerances (relative energy error 7.535e-14; norm-relative state error
2.259e-11). The saved local record is
`docs/nbody_grouped_validation.json`. These are local correctness and structural
checks, not new target-VM performance results. Preserve the upstream source hash
alongside subsequent result manifests:

```text
d1385e816d7cfea361b7915e2cf70138cd6b84f40df8bd5152638851f7bcac2b
```

## Measure on the Ubuntu VM

After committing/pushing the change and updating the VM checkout, run the
explicit verification above, followed by:

```bash
USE_UPSTREAM=1 ./script_nbody.sh --variant both --loops 16
```

The baseline arm uses the unmodified reference; the optimized arm now selects
`grouped`. This is an initial sequential collection of before/after timing and
profiles, not a drift-resistant final comparison by itself. Preserve its
manifest, raw observations, correctness output, and source revision.

For direct equal-work controls:

```bash
python3 -B variants/bm_nbody_upstream_opt.py --kernel upstream --mode raw --loops 16 --iterations 20000 --no-gc
python3 -B variants/bm_nbody_upstream_opt.py --kernel grouped --mode raw --loops 16 --iterations 20000 --no-gc
```

Use identical release Python, GC state, hash seed, CPU affinity, work size, timer
boundary, and reset policy. For a final claim, alternate complete A/B and B/A
separate-process rounds (or randomize and record their order). Keep all raw
observations and investigate failed runs rather than selectively retaining one
arm. Record process count, paired order, per-unit values, median, spread, and a
justified uncertainty analysis. A historical baseline on its own is not a
contemporaneous control for the new optimized run.

`--mode ablate` is an exploratory in-process comparison. `--no-gc` now applies
before calibration and ablation as well as raw timing. The existing
`tools/ab_timing.sh` still needs its failed-arm handling and confidence-interval
analysis checked before its PASS verdict is used as evidence.

Collect clean runtime independently of profiling. For the explanatory counter
comparison, start with a small cycles/instructions event group to reduce
multiplexing, then add separately measured events if needed. Expect fewer
source-level container accesses; whether the total executed instruction count
and wall time decrease enough to matter is the measurement question.

Report both `baseline / grouped` speedup and
`100 * (1 - grouped / baseline)` time reduction. Do not claim an official
optimized pyperformance result from this custom wrapper: the installed-suite
run remains a separate baseline cross-check. No VM speedup, 7% outcome, or
completed hardware accelerator is established by this implementation alone.
