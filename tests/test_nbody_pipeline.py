"""Shell kernel selection and phase forwarding; no Linux perf installation needed."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class NbodyPipelineTests(unittest.TestCase):
    def environment(self, results):
        return dict(os.environ, RESULTS_DIR=str(results), USE_UPSTREAM="1",
                    SKIP_WORKLOAD_VERIFY="1", USE_TASKSET="0", CLEAN_REPS="1",
                    PY_REL=sys.executable, PY_DBG=sys.executable,
                    PYTHONDONTWRITEBYTECODE="1", ENABLE_VERIFY="1")

    def test_time_only_compares_reference_to_selected_kernel(self):
        for kernel in (None, "grouped", "flat_sqrt", "upstream"):
            with self.subTest(kernel=kernel), tempfile.TemporaryDirectory() as tmp:
                results = Path(tmp) / "results"
                args = ["bash", str(ROOT / "script_nbody.sh"),
                        "--variant", "both", "--loops", "1", "--time-only"]
                if kernel is not None:
                    args += ["--kernel", kernel]
                proc = subprocess.run(args, cwd=ROOT, env=self.environment(results),
                                      capture_output=True, text=True, timeout=60)
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                selected = kernel or "flat_pow"
                baseline = results / "latest_nbody_baseline"
                optimized = results / "latest_nbody_optimized"
                base_raw = (baseline / "timing/clean_baseline.txt").read_text()
                opt_raw = (optimized / "timing/clean_optimized.txt").read_text()
                self.assertIn("UPSTREAM pyperformance nbody kernel (unmodified)", base_raw)
                self.assertNotIn("kernel=", base_raw)
                self.assertIn(f"kernel={selected}", opt_raw)
                self.assertIn("--kernel " + selected,
                              (optimized / "manifest.txt").read_text())
                self.assertNotIn("--kernel", (baseline / "manifest.txt").read_text())
                summary = results / "latest_comparison_nbody/summary.txt"
                self.assertIn("SPEEDUP", summary.read_text())

    def test_invalid_or_unsupported_kernel_is_rejected_before_measurement(self):
        cases = [("script_nbody.sh", "1", ["--kernel"]),
                 ("script_nbody.sh", "1", ["--kernel", "missing"]),
                 ("script_nbody.sh", "0", ["--kernel", "flat_pow"]),
                 ("script_nbody.sh", "1", ["--kernel", "guards"])]
        for script, upstream, extra in cases:
            with self.subTest(script=script, upstream=upstream, extra=extra):
                with tempfile.TemporaryDirectory() as tmp:
                    results = Path(tmp) / "results"
                    env = self.environment(results)
                    env["USE_UPSTREAM"] = upstream
                    proc = subprocess.run(["bash", str(ROOT / script)] + extra,
                                          cwd=ROOT, env=env, capture_output=True,
                                          text=True, timeout=10)
                    self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
                    self.assertIn("--kernel", proc.stderr)
                    self.assertFalse(results.exists())

    def test_all_nbody_kernel_names_are_accepted_without_starting_measurement(self):
        for kernel in ("upstream", "grouped", "flat_pow", "flat_sqrt", "sqrt", "hoist", "full"):
            with self.subTest(kernel=kernel), tempfile.TemporaryDirectory() as tmp:
                results = Path(tmp) / "results"
                proc = subprocess.run(
                    ["bash", str(ROOT / "script_nbody.sh"), "--kernel", kernel, "--list-phases"],
                    cwd=ROOT, env=self.environment(results), capture_output=True,
                    text=True, timeout=10)
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                self.assertIn("default: flat_pow", proc.stdout)
                self.assertFalse(results.exists())

    def test_kernel_reaches_every_workload_phase_without_leaking_to_baseline(self):
        # Execute the real pipeline and phase helpers, replacing only external
        # profiler/interpreter commands with argument recorders. Failed optional
        # profilers stop before report generation, after capturing their argv.
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            recorder = directory / "record.py"
            calls = directory / "calls.jsonl"
            recorder.write_text('''import json, os, sys
tool, args = sys.argv[1], sys.argv[2:]
with open(os.environ["TEST_CALLS"], "a") as out:
    out.write(json.dumps([os.environ.get("VARIANT"), tool, args]) + "\\n")
if tool == "python" and "--mode" in args:
    mode = args[args.index("--mode") + 1]
    if mode == "calibrate":
        print(2)
    elif mode == "raw":
        print("RESULT total_sec=0.05 loops=2")
    else:
        print("verify: OK")
elif tool == "python" and args[:2] == ["-m", "cProfile"]:
    sys.exit(1)
''')
            env = self.environment(directory / "results")
            env.update(TEST_ROOT=str(ROOT), TEST_PYTHON=sys.executable,
                       TEST_RECORDER=str(recorder), TEST_CALLS=str(calls),
                       LOOPS="", ENABLE_PERF_STAT="1", ENABLE_PERF_RECORD="1",
                       ENABLE_CACHE_PROFILE="1", ENABLE_CPROFILE="1",
                       ENABLE_PYSPY="1", ENABLE_TOPDOWN="1",
                       ENABLE_CLEAN_TIMING="1", ENABLE_PYPERFORMANCE="1")
            script = r'''
source "$TEST_ROOT/lib/common.sh"
source "$TEST_ROOT/lib/pipeline.sh"
record_tool() { "$TEST_PYTHON" "$TEST_RECORDER" "$@"; }
python_probe() { record_tool python "$@"; }
perf() { record_tool perf "$@"; return 1; }
py-spy() { record_tool py-spy "$@"; return 1; }
require_perf() { :; }
require_python_dbg() { :; }
probe_pmu() { PMU_OK=1; PERF_EVENTS=cycles; export PMU_OK PERF_EVENTS; }
run_pyperformance() { record_tool pyperformance "$@"; }
PY_REL=python_probe
PY_DBG=python_probe
run_variant nbody baseline "$TEST_ROOT/bench/bm_nbody_upstream.py"
run_variant nbody optimized "$TEST_ROOT/variants/bm_nbody_upstream_opt.py" --kernel flat_sqrt
'''
            proc = subprocess.run(["bash", "-c", script], cwd=ROOT, env=env,
                                  capture_output=True, text=True, timeout=30)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            seen = {"baseline": set(), "optimized": set()}
            suite_calls = []
            for variant, tool, args in map(json.loads, calls.read_text().splitlines()):
                if tool == "pyperformance":
                    suite_calls.append((variant, args))
                    continue
                if not any(arg.endswith("_upstream.py") or
                           arg.endswith("_upstream_opt.py") for arg in args):
                    continue
                if variant == "baseline":
                    self.assertNotIn("--kernel", args)
                else:
                    self.assertEqual(args.count("--kernel"), 1)
                    self.assertEqual(args[args.index("--kernel") + 1], "flat_sqrt")
                if tool == "perf":
                    phase = "cache" if "cache-misses" in args else "perf_" + args[0]
                elif tool == "py-spy":
                    phase = "pyspy"
                elif args[:2] == ["-m", "cProfile"]:
                    phase = "cprofile"
                else:
                    phase = args[args.index("--mode") + 1]
                seen[variant].add(phase)
            expected = {"verify", "calibrate", "raw", "perf_stat", "perf_record",
                        "cache", "cprofile", "pyspy"}
            self.assertEqual(seen["baseline"], expected)
            self.assertEqual(seen["optimized"], expected)
            self.assertEqual(suite_calls, [("baseline", ["nbody", "baseline"])])


if __name__ == "__main__":
    unittest.main()
