# HW/SW Co-design: upstream nbody and raytrace

Course 00460882, Technion. This project profiles the actual pyperformance workloads,
implements exact software specializations and supplies a complete logical FP64
ray-sphere accelerator design with explicitly analytical estimates.

## Current results - 20 September 2026

| Target-VM experiment | Baseline median | Optimized median | Runtime reduction |
|---|---:|---:|---:|
| Raytrace full, newest matched session | 791.215 ms/frame | 452.696 ms/frame | **42.78%** |
| Raytrace shadow-ray reuse, historical | 789.756 ms/frame | 611.023 ms/frame | 22.63% |
| Nbody grouped, 20,000 steps | 227.314 ms/unit | 219.589 ms/unit | 3.40% |
| Nbody flat_pow, previous full run | 228.249 ms/unit | 142.578 ms/unit | 37.53% |
| Nbody flat_pow, newest matched session | 227.196 ms/unit | 143.374 ms/unit | **36.89%** |

Both selected exact improvements exceed the declared 7% runtime target on the
Ubuntu CPython 3.10.12 VM. Clean timing, not profiler elapsed time or cycle counts,
is the criterion. Eleven independent processes per arm were collected in separate
blocks; host drift remains a limitation. The newest pairs are selected by
`results/session_all_20260920-074308_674/`: raytrace 074314_1800 / 075734_1800,
and nbody 080806_16940 / 081744_16940. Captured source hashes match current files.
Both optimized verification logs cover the actual batch (4 frames / 16 units).

**Current defaults:** nbody `flat_pow`, raytrace `full`. Keep the exact full
raytrace bundle: its new VM result supports the combined changes. Individual
VM contributions are not isolated; diagnostic kernels and optional slots remain.
Nbody uses the same source as the preceding full run; this is confirmation.
Canonical reports are the filenames below, without a copied " 2" suffix.

- [Raytrace PDF](docs/reports/report_raytrace.pdf) and [required TXT](report_raytrace.txt)
- [Nbody PDF](docs/reports/report_nbody.pdf) and [required TXT](report_nbody.txt)
- [Assignment mapping](docs/PROJECT_REQUIREMENTS.md)
- [Hardware architecture and limitations](docs/HARDWARE_DESIGN.md)

## Run the complete workflow on Ubuntu

Initial setup, if needed:

```bash
sudo ./setup/01_install_deps.sh
./setup/02_get_flamegraph.sh
sudo ./setup/03_tune_vm.sh
./setup/04_make_venv.sh
./tools/doctor.sh
```

Review the tuning output: CPU governor control may be unavailable in a VM. The
reference sources already exist; `setup/05_get_upstream.sh` is their acquisition
helper. The authenticity phase should be retained with the run output.

```bash
./run_all.sh
```

This selects the upstream workloads, both baseline and optimized arms, the full
workflow, nbody `flat_pow` and raytrace `full`. It uses a common calibrated loop
count within each comparison and verifies that actual batch before measurement.
It creates `results/session_all_<timestamp>_<pid>/` with explicit manifests and
comparison paths. Missing optional profiling tools are recorded in `phases.tsv`;
correctness, clean timing and cProfile workload failures stop the run.

```bash
./run_all.sh --time-only
./run_all.sh --nbody-kernel grouped --raytrace-kernel shadow_ray
./script_nbody.sh --variant both --kernel flat_pow --loops 16
./script_raytrace.sh --variant both --kernel full --loops 4
```

`--time-only` avoids profiler preconditions. `--quick` is a smoke test, not final
measurement evidence. `USE_UPSTREAM=0` explicitly selects older stand-in workloads;
those do not establish improvement over the required upstream reference.

For stronger confirmation with balanced AB/BA independent-process ordering:

```bash
LOOPS=16 ./tools/ab_timing.sh nbody 16 --kernel flat_pow
LOOPS=4 ./tools/ab_timing.sh raytrace 16 --kernel full
```

The second positional number is the number of paired rounds. Raw process logs,
full-batch checks and paired bootstrap results are retained. Statistical
uncertainty still does not account for every systematic VM effect.

## Optimizations and correctness

`upstream/` and `bench/bm_*_upstream.py` were left unchanged. The wrappers call the
upstream bench functions themselves; they are custom timing/profiling harnesses,
not official pyperformance suite runs. The separate official suite baseline
phase is a cross-check, not an optimized-suite measurement.

Nbody `flat_pow` retains all 30 state components in locals across all timesteps,
expands ten pair interactions and five position updates, preserves the original
power expression and arithmetic/update order, and writes back at return. It
specializes canonical five-body, distinct-list float inputs. It preserves exact
successful-call results, not partial updates during exceptions or arbitrary
aliased containers. Locals still contain boxed floats.

`grouped` remains available. `flat_sqrt` has the same flat/unrolled structure with
a different inverse-power calculation; it passes a tolerance contract but is
not bit-identical and is not the final default. `flat_unrolled` describes the
structure, not another kernel. The new [structural controls](docs/NBODY_CONTROL_EXPERIMENTS.md)
separate container and traversal changes without claiming extra default gains.

Raytrace `full` combines shadow reuse, stock-object guard fast paths with generic
fallbacks, scalar sphere arithmetic, camera component reuse, direct nearest-hit
selection and removal of a discarded checkerboard object. It preserves the
reference's arithmetic order and existing rendering quirks. `slots` and
`full_slots` are optional fresh-stock-scene experiments with a narrower object
model. See the [complete raytrace guide](docs/RAYTRACE_FULL_EXPERIMENT.md).

```bash
python3 -B -m unittest discover -s tests -v
python3 -B variants/bm_nbody_upstream_opt.py --mode verify --loops 16 --iterations 20000
python3 -B variants/bm_raytrace_upstream_opt.py --mode verify --loops 4
python3 -B experiments/nbody_controls.py --mode verify --loops 16 --iterations 20000
```

The integrated suite passes 63 tests. Exact nbody checks compare energy and every
state component; raytrace checks every requested frame plus raw colours, geometry,
edge cases and baseline restoration. These are tested contracts, not formal
proofs for all Python inputs. Saved evidence is under `docs/evidence/`.

## Read measurements correctly

| Instrument | Meaning |
|---|---|
| Clean release-Python timer | Quotable runtime; retain all observations |
| perf stat | Separate counting runs, normalized to equal work; inspect multiplexing |
| perf record with python3-dbg | Native sampled mechanisms; not release-time percentages |
| cProfile | Python calls and function attribution; perturbed timing |
| pyperformance | Separate official baseline harness |

A flame graph normalizes width and shows stack ancestry, not a timeline. Similar
shapes can hide large reductions in equal-work samples. Inclusive counts overlap;
self counts are leaf samples. Do not sum overlapping categories, infer a fixed
cost per Python call, or use debug percentages as exact Amdahl ceilings. Negative
top-down fractions and unsupported counters are rejected as evidence.

## Reports, hardware and repository map

| Path | Purpose |
|---|---|
| `upstream/` | Reference sources and historical provenance text |
| `bench/`, `variants/`, `experiments/`, `tests/` | Wrappers, candidates, diagnostic controls and checks |
| `lib/`, `config/`, `setup/`, `tools/` | Full workflow, settings, setup and comparison tools |
| `results/` | Immutable timestamped raw evidence and session manifests |
| `docs/reports/` | PDF/source JSON, evidence registry and readable original SVGs |
| `report_nbody.txt`, `report_raytrace.txt` | Required six-section reports |
| `hardware/` | Complete SystemVerilog core, licensed FP RTL, host helpers and analytical model |
| `docs/HARDWARE_DESIGN.md` | Interface, architecture, software integration plan and trade-offs |
| `prompt.txt` | Actual AI prompts and decision history |

The accelerator is a sequential FP64 ray-sphere core with ready/valid, status,
reset and backpressure. Syntax/elaboration and host-format checks passed. No HDL
simulation, synthesis, achieved clock rate or hardware speedup is claimed.
Renderer batching, driver and transport are proposed integration work. The
analytical model includes a losing case: offload is not automatically faster.

PDF and TXT files share reviewed JSON content. To rebuild them, install ReportLab
in the documentation environment and run:

```bash
python3 tools/build_reports.py
```

The builder does not choose results or invent new analysis. `tools/gen_report.sh`
creates an evidence appendix from explicit directories; it never overwrites an
authored report. Review new measurements before updating the source JSON.

Remaining submission work: measure the new full raytrace kernel on Ubuntu,
prepare the 20-25 minute presentation and working demo, and upload the repository
when the author chooses. No Git operations were performed during this work;
measurement Git metadata is off by default (`CAPTURE_GIT_METADATA=0`).
