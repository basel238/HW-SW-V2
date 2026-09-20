# HW/SW Co-design: upstream nbody and raytrace

Course **00460882**, Technion. This repository profiles two approved
`pyperformance` workloads, tests software changes, and keeps the evidence for
their analysis and a subsequent hardware proposal.

## Current status — 20 September 2026

The current reference workloads are the files under `upstream/`, invoked through
`bench/bm_*_upstream.py`. The independently written `bench/bm_nbody.py` and
`bench/bm_raytrace.py` are older stand-ins. Their historical speedups do not
establish improvement over the required upstream benchmarks.

The latest baseline analysis uses these two result sets only:

| Benchmark | Selected baseline | Median clean time | Process observations |
|---|---|---:|---:|
| nbody, 20,000 steps | `nbody_baseline_20260919-222849` | 227.247625 ms/unit | 11 × 16 units |
| raytrace, 100×100 | `raytrace_baseline_20260919-220048` | 792.16625 ms/frame | 11 × 4 frames |

Both were recorded on the Ubuntu 22.04 KVM guest with CPython 3.10.12. The old
CSV fields contain trailing text and their summaries report no samples. The
reports recover every observation from valid raw `RESULT` records; they do not
discard failed parses selectively. Current parser repairs do not change those
historical artifacts.

The upstream raytrace variant now defaults to **`shadow_ray`**, which reuses one
shadow ray per visibility query. `guards` remains an independent experiment;
`upstream` is the control. Local verification passes at five resolutions. The
new kernel removes 72,172 duplicate Ray constructions/normalizations and 144,344
Vector constructions per 100×100 frame. These are work reductions, not measured
VM speedups. A matching target-VM optimized result is still needed.

Nbody has existing separately selectable arithmetic/indexing experiments. This
change does not modify them. Neither the current baseline analysis nor the
new raytrace correctness checks establish that both upstream workloads meet
the course's sufficient 7% improvement outcome.

- [Raytrace report](report_raytrace.txt): baseline evidence, implemented change,
  validation, performance experiment, and hardware status.
- [Nbody report](report_nbody.txt): actual algorithm, baseline evidence, existing
  candidate status, and remaining measurements.
- [Experiment instructions](docs/SHADOW_RAY_EXPERIMENT.md): explicit kernels,
  correctness checks, profile interpretation, and VM measurement protocol.
- [Project requirements](docs/PROJECT_REQUIREMENTS.md): PDF page references and
  remaining deliverables, including a complete hardware design.
- [Local validation evidence](docs/shadow_ray_validation.json): operation counts
  and pixel hashes; not a target-VM timing record.

## Quick start on the Ubuntu VM

```bash
sudo ./setup/01_install_deps.sh
./setup/02_get_flamegraph.sh
sudo ./setup/03_tune_vm.sh
./setup/04_make_venv.sh
./tools/doctor.sh
```

The upstream files are already present. The pipeline checks their provenance;
`setup/05_get_upstream.sh` is the acquisition helper if they are missing. Inspect
the actual manifest to confirm which VM tuning settings took effect.

Verify and run the new raytrace experiment:

```bash
python3 -B -m unittest discover -s tests -v
python3 -B variants/bm_raytrace_upstream_opt.py --mode verify
USE_UPSTREAM=1 ./script_raytrace.sh --variant both --loops 4
```

The optimized arm selects `shadow_ray` by default. To choose a kernel directly:

```bash
python3 variants/bm_raytrace_upstream_opt.py --kernel upstream --mode raw --loops 4 --no-gc
python3 variants/bm_raytrace_upstream_opt.py --kernel shadow_ray --mode raw --loops 4 --no-gc
python3 variants/bm_raytrace_upstream_opt.py --kernel guards --mode raw --loops 4 --no-gc
```

Use `--mode ablate` for a quick in-process exploratory comparison. Final claims
need interleaved separate-process runs with identical work and complete paired
observations, as described in the experiment instructions. The existing
`tools/ab_timing.sh` needs its failed-arm handling and confidence-interval
analysis checked before its PASS verdict is used as evidence.

Other entry points:

```bash
./script_nbody.sh --help
./script_raytrace.sh --help
./run_all.sh --quick
./run_all.sh --time-only
```

`USE_UPSTREAM=1` is the default. Setting it to zero deliberately selects the
older stand-ins and changes what is being measured.

## What each measurement establishes

| Phase | Purpose | Interpretation |
|---|---|---|
| Verification | Reference state/pixel comparison | Check correctness before timing |
| Clean release-Python timing | Unprofiled runtime | Before/after performance evidence |
| Release `perf stat` | Counts of instructions, cycles and supported events | Explain changes in executed work; inspect multiplexing |
| `perf record` with `python3-dbg` | Native sampled stacks and flame graphs | Locate interpreter mechanisms; percentages are not release-time fractions |
| `cProfile` | Python functions and call counts | Test specific work-reduction predictions; timing is instrumented |
| `pyperformance` | Installed suite's baseline harness | Independent baseline check; does not evaluate the custom optimized variant |

This is an upstream workload in a profiling wrapper, plus a separate official
suite baseline run. The wrapper itself is not an official pyperformance suite
result. That distinction identifies the harness and measurement conditions;
it does not invalidate an equal-work wrapper comparison.

Keep speedup (`baseline / optimized`) separate from time reduction
(`100 * (1 - optimized / baseline)`). This project declares time reduction as
its convention for the 7% target. The old comparison script's noise heuristic
is not a confidence interval.

In the selected baseline manifests, affinity is guest CPU 0, hash seed is zero,
and cyclic GC is disabled. ASLR is **enabled**, and a CPU governor is unavailable.
Native profiles contain usable stacks but do not supply precise release-time
Amdahl bounds. Several PMU events are multiplexed; LLC events are unsupported
and negative top-down percentages make that decomposition invalid. Read the
reports before interpreting those fields as bottleneck evidence.

## Repository map and deliverables

| Path | Purpose |
|---|---|
| `upstream/` | Unmodified reference benchmark sources and provenance |
| `bench/bm_*_upstream.py` | Raw timing, calibration and correctness wrappers |
| `variants/bm_*_upstream_opt.py` | Independently selectable software experiments |
| `tests/test_raytrace_shadow.py` | Shadow-ray correctness and baseline-isolation checks |
| `script_nbody.sh`, `script_raytrace.sh` | Required per-benchmark execution scripts |
| `lib/`, `config/`, `setup/` | Measurement phases, settings, dependencies and VM setup |
| `results/` | Timestamped logs, raw timings, profiles, graphs and manifests |
| `report_nbody.txt`, `report_raytrace.txt` | Required six-section reports; comparison/hardware work remains open |
| `docs/PROJECT_REQUIREMENTS.md` | Assignment mapping and completion plan |
| `docs/SHADOW_RAY_EXPERIMENT.md` | New optimization rationale and measurement instructions |
| `prompt.txt` | AI usage history, including this implementation/report stage |

For each selected result directory, begin with `manifest.txt`,
`timing/clean_baseline.txt`, `raw/cprofile_baseline.txt`,
`perf/report_baseline_self.txt`, `perf/stat_baseline.txt`, and
`flame/baseline.svg`. Exact evidence paths appear in the reports.

The authored reports take precedence over legacy template prose.
`tools/gen_report.sh` still contains stand-in descriptions; its existing guard
redirects output to `.generated.txt` when an authored report has no unfinished
template markers. Review any generated document before using it. Older script
comments and `docs/HW_PROPOSAL_NOTES.md` also need reconciliation before final
submission; they are not proof of the current upstream behavior or a completed
hardware design.

Remaining project work includes target-VM comparisons, subsequent justified
optimizations, the specified hardware design/interface/diagram/trade-offs, and
the presentation. The TXT reports explicitly distinguish evidence already
collected from proposed work.
