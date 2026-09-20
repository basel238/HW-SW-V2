# Exact nbody structural controls

The production default remains `flat_pow`. These additional implementations test explanations, without changing upstream, the arithmetic, the ten canonical pairs or 20,000 steps. They are not assumed improvements and are not automatically stacked into the final default.

| Control | Change tested |
|---|---|
| unpacked | Original flat pair traversal, bulk velocity unpacking, immediate stores |
| grouped_indexed | Extra group traversal with original indexed updates; estimates traversal penalty |
| unrolled_pairs | Expand ten pairs; retain original per-pair unpacking/indexing and drift loop |
| unrolled_lists | Bind five body references/masses once, expand pairs/drift, retain indexed state |
| velocity_locals | Same fixed body structure, retain velocities for whole advance; positions stay lists |
| flat_pow | Retain both positions and velocities for whole advance; production implementation |

Compare unrolled_pairs to unrolled_lists for several related structure costs, unrolled_lists to velocity_locals for velocity reuse, and velocity_locals to flat_pow for position reuse. Changes are not perfectly independent microbenchmarks; code size, bytecode form and reference lifetimes may also change. Python locals still contain boxed floats. Source access counts are not runtime shares.

```bash
python3 -B experiments/nbody_controls.py --mode verify --loops 16 --iterations 20000
taskset -c 0 python3 -B experiments/nbody_controls.py --mode ablate --loops 16 --iterations 20000 --reps 16 --output nbody_controls.json
```

Every selected candidate passes an exact energy/all-30-state check at the actual batch size before exploratory timing. Order rotates; every repetition and value is saved. The process is reused, so final speedups still require release-Python independent-process measurements. `--kernels` can select a smaller comparison; upstream is always included. No Git commands are executed.

Deferred-state fixed-five controls share flat_pow's successful-call workload contract: distinct ordinary float lists, actual supplied masses/state, canonical pair order, no concurrent observation or reliance on partial mutation on exceptions. They are diagnostic workload specializations, not universal replacements for arbitrary Python containers.
