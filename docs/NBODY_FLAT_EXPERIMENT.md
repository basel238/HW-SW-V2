# Nbody: unrolled kernels with persistent local state

`flat_pow` specializes the five-body reference workload by retaining all 30
position and velocity components in local variables throughout `advance()`.
The ten pair interactions and five position updates are written explicitly in
their original order. It is the default optimized kernel. `flat_sqrt` combines
the same persistent local state and unrolling with the inverse-power rewrite;
`grouped`, `sqrt`, `hoist`, `full`, and the upstream control remain available
independently. The term `flat_unrolled` describes this shared structure;
`flat_pow` and `flat_sqrt` name its two arithmetic choices.

The reference under `upstream/` is unchanged. This experiment changes execution
structure, not the number of timesteps, the force calculation, or the initial
conditions. The latest full target-VM result establishes a 37.53% median runtime reduction (228.249 to 142.578 ms/unit); see report_nbody.txt for the matched runs and limits.

## Hypothesis

One unit has 20,000 timesteps and 200,000 pair interactions. Repeated container
reads, writes, unpacking, and short-loop control can therefore be worthwhile
optimization targets even though each operation is small. The previous grouped
candidate reduced some of these accesses, but retained pair/group traversal and
reloaded state at each group and timestep.

`flat_pow` instead:

1. Validates the supported workload shape once, inside `advance()`.
2. Loads the supplied positions, velocities, and masses once.
3. Executes every pair update and position update for every requested timestep,
   using local state throughout.
4. Writes all positions and velocities back on successful return.

The numerical kernel's source-level component accesses fall from `225 * n`
reads/writes in upstream to 30 initial reads and 30 final writes, excluding the
entry validation and accesses to containers, masses, and object metadata. These
are logical component-access counts, not hardware loads or a runtime forecast.
Validation, initial loading, and final writeback remain inside the measured
`advance()` call.

In `flat_pow`, all floating-point expressions remain, including:

```python
mag = dt * ((dx * dx + dy * dy + dz * dz) ** (-1.5))
```

The combined `flat_sqrt` candidate retains the same data representation and
pair/update order but uses a locally bound square root:

```python
d2 = dx * dx + dy * dy + dz * dz
mag = dt / (d2 * _sqrt(d2))
```

For positive `d2` this uses the same real-number identity, but the operation
sequence and floating-point rounding differ. Comparing `flat_pow` directly with
`flat_sqrt` tests that arithmetic rewrite on top of the same structural changes.

The unchanged calculation has 270 floating-result expressions per timestep,
or 5.4 million per 20,000-step unit. Python locals still hold boxed floats;
flattening does not inherently remove these arithmetic-result objects or turn
the calculation into native unboxed arithmetic. Object creation is also not
equivalent to a fresh heap allocation because the interpreter can reuse storage.

## Supported semantics and correctness

This is a specialization for five bodies, canonical ordered pairs, distinct
ordinary position/velocity lists containing floats, float `dt`, and a
nonnegative integer timestep count. It reads the supplied state and masses;
neither trajectories nor answers are hardcoded. Unsupported shapes are rejected
by validation rather than silently producing results for the wrong system.

The pair order, floating-point expression order, velocity update order, and
placement of position updates after all pairs are preserved. `flat_pow` and
`grouped` require finite, bit-identical energy and all 30 state components in
verify mode. `flat_sqrt` instead uses the existing `1e-9` relative-energy and
norm-relative-state tolerance, with finite values required. The state criterion
is maximum absolute component error divided by the maximum absolute reference
component; it is not a per-component relative-error bound. Existing approximate
candidates retain that same tolerance; `flat_pow` is not accepted through it.

State becomes visible in the supplied lists at the end of `advance()`. This does
not preserve arbitrary intermediate observers or the partial list updates that
upstream might expose when interrupted by an exception or signal. Aliased state,
custom containers, and noncanonical pair orders are outside the specialization.
The benchmark observes successful call boundaries, so those boundaries are the
correctness target.

Correctness checks should cover zero steps, short trajectories, a complete
20,000-step unit, the actual 16-unit measurement batch, and randomized valid
states/masses. Compare all components as well as energy: agreement in total
energy alone can hide state errors. Repeat correctness checks on the target
interpreter before accepting its performance results.

## Ubuntu commands

Run from the repository root after syncing the implementation. First verify the
actual batch size used for timing:

```bash
python3 -B variants/bm_nbody_upstream_opt.py \
  --mode verify --loops 16 --iterations 20000
```

A direct run selects the candidate explicitly. This is useful for checking the
reported kernel and workload; one observation is not the final speedup result:

```bash
python3 -B variants/bm_nbody_upstream_opt.py \
  --mode raw --kernel flat_pow --loops 16 --iterations 20000 --no-gc
```

To explicitly check the combined structural and arithmetic candidate:

```bash
python3 -B variants/bm_nbody_upstream_opt.py \
  --mode raw --kernel flat_sqrt --loops 16 --iterations 20000 --no-gc
```

Compare all available candidates using 15 repetitions and rotating candidate
order. Keep this output with the run artifacts:

```bash
taskset -c 0 python3 -B variants/bm_nbody_upstream_opt.py \
  --mode ablate --loops 16 --iterations 20000 --reps 15 --no-gc \
  --ablation-json nbody_flat_ablation.json
```

The optional JSON artifact records every raw sample, its repetition and run
position, summary statistics, interpreter/platform information, GC setting, and
upstream/variant source hashes. Keep it with the console output and correctness
log. This ablation reuses one Python process and is explicitly exploratory;
confirm a selected candidate with independent-process clean timing on Ubuntu.

Run the normal measurement and profiling pipeline with the same workload. Its
optimized arm now uses the default `flat_pow` candidate:

```bash
USE_UPSTREAM=1 ./script_nbody.sh --variant both --kernel flat_pow --loops 16
```

The shell script now accepts all nbody kernel names. To measure the combined
sqrt candidate or reproduce the intermediate grouped experiment, select it
explicitly; the baseline arm always remains the original upstream kernel:

```bash
USE_UPSTREAM=1 ./script_nbody.sh --variant both --kernel flat_sqrt --loops 16
USE_UPSTREAM=1 ./script_nbody.sh --variant both --kernel grouped --loops 16
```

For the initial runtime decision, add `--time-only`; collect full profiles for
promising candidates afterward. Kernel selection is forwarded consistently to
verification, calibration, timing and profiling of the optimized arm and saved
in its manifest. The default when `--kernel` is omitted is `flat_pow`.

Inspect the saved optimized records to confirm `kernel=flat_pow`. Preserve the
candidate source, commit and any uncommitted diff, interpreter version, complete
raw observations, and correctness output alongside the results. Do not combine
a new optimized run with a baseline from a different machine or interpreter.

## How to judge the result

The project's 7% criterion concerns clean, unprofiled runtime. Use the target
VM's release `python3` for that decision; `python3-dbg` profiles are attribution
evidence. A reduction in cycles, sample count, or bytecode count does not by
itself satisfy the runtime criterion.

For matched baseline and candidate medians, report:

```text
runtime reduction = 100 * (1 - candidate_median / baseline_median)
speedup           = baseline_median / candidate_median
```

Report dispersion and retain every planned observation. Rotating candidate
order reduces a fixed ordering bias; it does not eliminate VM noise or prove
independence. Repeat a close result with balanced/interleaved measurements. Use
the full pipeline's clean results for the final report and the ablation to
compare candidate behavior under the same settings.

The recorded grouped experiment on release Python 3.10.12 in the Ubuntu VM
reduced median runtime from 227.31 to 219.59 ms per unit, or 3.40%. That result
remains an intermediate improvement below 7%. An external analysis reported
approximately 31% for a flat-power candidate on Python 3.14/ARM, but its exact
candidate and raw timing artifacts have not been independently verified here.
That number is a motivation to test this implementation, not its measured
performance and not an Ubuntu result.

## Interpretation limits

`grouped` deliberately retained `pow`; seeing a power function in its profile
was expected. `sqrt` and `grouped` are independent candidates, not consecutive
steps in a cumulative optimization chain. Likewise, compare `flat_pow` against
both upstream and grouped without attributing the entire improvement to one
removed operation: it combines state reuse, unpacking removal, and loop
expansion. Separate structural controls are needed for finer attribution.
`flat_pow` versus `flat_sqrt` is a direct arithmetic comparison on a common
structure; the legacy `full` candidate combines sqrt with per-pair hoisting and
does not retain all state across timesteps.

A static bytecode count cannot assign runtime percentages. In the examined
Python 3.14 listing, 39 `BINARY_OP` instructions included nine subscriptions;
only 30 were arithmetic. Different loop bodies execute different numbers of
times, and bytecodes have different costs. Interpreter self samples also cover
more than dispatch alone. Neither count establishes a hard arithmetic ceiling.

A successful flattening experiment would support reducing Python execution and
container overhead. It would not independently prove that a MAC/reciprocal-square-
root accelerator is the best hardware design. Such a proposal must account for
offload granularity, transfer/setup costs, state residency and numerical
equivalence, and should be compared with a compiled CPU implementation.

## Final integration update - 20 September 2026

The full profile pair nbody_baseline_20260920-031836 /
nbody_optimized_20260920-032819 explicitly selects flat_pow and matches the
current variant source hash. Generic GetItem/SetItem subtree samples fall from
226 to 2; instructions fall about 35%. Arithmetic and boxed-float work remain.
The pipeline now verifies the actual requested batch and run_all.sh selects
flat_pow for nbody and full for raytrace. Separate structural controls are
available in experiments/nbody_controls.py. See the current reports for the
complete decision history and evidence.
