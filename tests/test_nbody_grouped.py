"""Nbody correctness checks: python3 -B -m unittest discover -s tests -v."""

import contextlib
import gc
import importlib.util
import io
import math
from pathlib import Path
import struct
import subprocess
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
VARIANT_PATH = ROOT / "variants" / "bm_nbody_upstream_opt.py"
SPEC = importlib.util.spec_from_file_location("nbody_variant", VARIANT_PATH)
variant = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(variant)


def bits(values):
    return struct.pack(f"!{len(values)}d", *values)


def run_state(loops, iterations, kernel):
    _, energy, up = variant._run(loops, iterations, kernel)
    state = variant.base.snapshot(up)
    if len(state) != 30 or not all(math.isfinite(x) for x in [energy] + state):
        raise AssertionError("invalid test state")
    return bits([energy] + state), up


class NbodyGroupedTests(unittest.TestCase):
    def test_bit_identical_at_short_default_and_accumulated_batch_sizes(self):
        for loops, iterations in ((1, 1), (1, 10), (1, 20000), (16, 20000)):
            with self.subTest(loops=loops, iterations=iterations):
                expected, _ = run_state(loops, iterations, None)
                actual, _ = run_state(loops, iterations, variant.advance_grouped)
                self.assertEqual(actual, expected)

    def test_consecutive_groups_use_identity_without_sorting_or_merging(self):
        first = ([0., 1., 2.], [3., 4., 5.], 1.)
        equal_but_distinct = ([0., 1., 2.], [3., 4., 5.], 1.)
        second, third = object(), object()
        pairs = [(first, second), (first, third),
                 (equal_but_distinct, second), (first, second)]
        groups = variant._group_consecutive_pairs(pairs)
        self.assertEqual([len(others) for _, others in groups], [2, 1, 1])
        self.assertIs(groups[0][0], first)
        self.assertIs(groups[1][0], equal_but_distinct)
        self.assertIs(groups[2][0], first)
        flattened = [(body, other) for body, others in groups for other in others]
        for old_pair, new_pair in zip(pairs, flattened):
            self.assertIs(old_pair[0], new_pair[0])
            self.assertIs(old_pair[1], new_pair[1])
        self.assertEqual(variant._group_consecutive_pairs([]), [])

    def test_nonconsecutive_groups_reload_values_updated_as_second_body(self):
        expected = variant.base.load_upstream()
        actual = variant.base.load_upstream()
        order = ((0, 1), (1, 2), (0, 2), (2, 3), (0, 4), (1, 4))
        original_pairs = [(expected.SYSTEM[i], expected.SYSTEM[j]) for i, j in order]
        grouped_pairs = [(actual.SYSTEM[i], actual.SYSTEM[j]) for i, j in order]
        expected.advance(.01, 10, expected.SYSTEM, original_pairs)
        variant.advance_grouped(.01, 10, actual.SYSTEM, grouped_pairs)
        self.assertEqual(bits(variant.base.snapshot(actual)),
                         bits(variant.base.snapshot(expected)))

    def test_repeated_advance_preserves_body_and_list_identity(self):
        expected = variant.base.load_upstream()
        actual = variant.base.load_upstream()
        identities = [(id(body), id(body[0]), id(body[1])) for body in actual.SYSTEM]
        for steps in (1, 10, 37):
            expected.advance(.01, steps)
            variant.advance_grouped(.01, steps, actual.SYSTEM, actual.PAIRS)
            self.assertEqual(bits(variant.base.snapshot(actual)),
                             bits(variant.base.snapshot(expected)))
            self.assertEqual(identities,
                             [(id(b), id(b[0]), id(b[1])) for b in actual.SYSTEM])

    def test_benchmark_runs_start_fresh_and_leave_baseline_independent(self):
        baseline, baseline_module = run_state(2, 10, None)
        first, first_module = run_state(2, 10, variant.advance_grouped)
        second, second_module = run_state(2, 10, variant.advance_grouped)
        after, after_module = run_state(2, 10, None)
        self.assertEqual(first, baseline)
        self.assertEqual(second, baseline)
        self.assertEqual(after, baseline)
        self.assertIsNot(first_module, second_module)
        self.assertIsNot(first_module.SYSTEM[0][1], second_module.SYSTEM[0][1])
        self.assertIsNot(baseline_module, after_module)
        self.assertEqual(after_module.advance.__name__, "advance")

    def test_group_construction_is_once_per_advance_not_per_timestep(self):
        up = variant.base.load_upstream()
        with mock.patch.object(variant, "_group_consecutive_pairs",
                               wraps=variant._group_consecutive_pairs) as group:
            variant.advance_grouped(.01, 10, up.SYSTEM, up.PAIRS)
            group.assert_called_once_with(up.PAIRS)
            variant.advance_grouped(.01, 1, up.SYSTEM, up.PAIRS)
            self.assertEqual(group.call_count, 2)

    def test_cli_defaults_to_grouped_and_keeps_legacy_choices(self):
        self.assertEqual(set(variant.KERNELS), {"upstream", "grouped", "sqrt", "hoist", "full"})
        args = ["nbody", "--loops", "1", "--iterations", "10"]
        up = variant.base.load_upstream()
        with mock.patch.object(sys, "argv", args):
            with mock.patch.object(variant, "_run", return_value=(1., -.1, up)) as run:
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(variant.main(), 0)
        run.assert_called_once_with(1, 10, variant.advance_grouped)
        self.assertIn("kernel=grouped", output.getvalue())

    def test_cli_verification_honors_loops_and_defaults_to_one(self):
        for extra_args, loops in (([], 1), (["--loops", "16"], 16)):
            with self.subTest(loops=loops):
                args = ["nbody", "--mode", "verify", "--iterations", "20000"] + extra_args
                with mock.patch.object(sys, "argv", args):
                    with mock.patch.object(variant, "verify") as verify:
                        self.assertEqual(variant.main(), 0)
                verify.assert_called_once_with(loops, 20000)

    def check_fake_verify(self, energy=-.1, state=None, kernel="grouped"):
        reference = [float(i) for i in range(1, 31)]
        actual = list(reference if state is None else state)
        fn = variant.KERNELS[kernel]
        with mock.patch.dict(variant.KERNELS, {"upstream": None, kernel: fn}, clear=True):
            with mock.patch.object(variant, "_run", side_effect=[(1., -.1, reference), (1., energy, actual)]) as run:
                with mock.patch.object(variant.base, "snapshot", side_effect=lambda up: up):
                    with contextlib.redirect_stdout(io.StringIO()):
                        variant.verify(3, 10)
                self.assertEqual(run.call_args_list, [mock.call(3, 10, None), mock.call(3, 10, fn)])

    def test_verify_rejects_one_bit_of_grouped_state_or_energy_difference(self):
        changed = [float(i) for i in range(1, 31)]
        changed[0] = math.nextafter(changed[0], math.inf)
        with self.assertRaisesRegex(AssertionError, "verification failed for: grouped"):
            self.check_fake_verify(state=changed)
        with self.assertRaisesRegex(AssertionError, "verification failed for: grouped"):
            self.check_fake_verify(energy=math.nextafter(-.1, math.inf))

    def test_verify_rejects_nonfinite_values_for_every_kernel(self):
        for name in ("grouped", "sqrt", "hoist", "full"):
            for value in (math.inf, -math.inf, math.nan):
                with self.subTest(kernel=name, energy=value):
                    with self.assertRaisesRegex(AssertionError, "non-finite"):
                        self.check_fake_verify(energy=value, kernel=name)
                state = [float(i) for i in range(1, 31)]
                state[7] = value
                with self.subTest(kernel=name, component=value):
                    with self.assertRaisesRegex(AssertionError, "non-finite"):
                        self.check_fake_verify(state=state, kernel=name)
        with self.assertRaisesRegex(AssertionError, "expected 30"):
            self.check_fake_verify(state=[1.])

    def test_verify_preserves_norm_relative_tolerance_for_legacy_candidates(self):
        changed = [float(i) for i in range(1, 31)]
        changed[0] += 1e-8  # Relative to max component (30), below 1e-9.
        for name in ("sqrt", "hoist", "full"):
            with self.subTest(kernel=name):
                self.check_fake_verify(state=changed, kernel=name)
        changed[0] += 1e-6
        with self.assertRaisesRegex(AssertionError, "verification failed for: hoist"):
            self.check_fake_verify(state=changed, kernel="hoist")

    def test_verify_failure_is_active_under_python_optimized_mode(self):
        code = f'''import importlib.util
spec = importlib.util.spec_from_file_location("candidate", {str(VARIANT_PATH)!r})
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
v.KERNELS = {{"upstream": None, "grouped": lambda *a, **k: None}}
v.verify(1, 10)
'''
        result = subprocess.run([sys.executable, "-B", "-O", "-c", code],
                                text=True, capture_output=True, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("verification failed for: grouped", result.stderr)

    def test_no_gc_applies_to_calibration_and_ablation(self):
        enabled = gc.isenabled()
        up = variant.base.load_upstream()

        def run(*args):
            self.assertFalse(gc.isenabled())
            return variant.TARGET_SEC + 1, -.1, up

        try:
            for mode in ("calibrate", "ablate"):
                gc.enable()
                args = ["nbody", "--mode", mode, "--no-gc"]
                with self.subTest(mode=mode), mock.patch.object(sys, "argv", args):
                    with mock.patch.object(variant, "_run", run):
                        with contextlib.redirect_stdout(io.StringIO()):
                            self.assertEqual(variant.main(), 0)
        finally:
            gc.enable() if enabled else gc.disable()


if __name__ == "__main__":
    unittest.main()
