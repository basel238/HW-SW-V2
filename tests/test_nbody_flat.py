"""Behavioral checks for the fixed-five-body flat-state nbody candidates."""

import copy
import importlib.util
import math
from pathlib import Path
import random
import struct
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "nbody_flat_variant", ROOT / "variants" / "bm_nbody_upstream_opt.py")
variant = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(variant)


def bits(values):
    return struct.pack(f"!{len(values)}d", *values)


def snapshot(bodies):
    return [value for position, velocity, _ in bodies
            for components in (position, velocity) for value in components]


def pairs_for(bodies):
    return [(bodies[i], bodies[j]) for i in range(len(bodies))
            for j in range(i + 1, len(bodies))]


class NbodyFlatTests(unittest.TestCase):
    def assert_close_state_energy(self, actual_state, actual_energy,
                                 expected_state, expected_energy):
        self.assertEqual(len(actual_state), 30)
        self.assertTrue(all(math.isfinite(x) for x in actual_state + [actual_energy]))
        state_scale = max(max(abs(x) for x in expected_state), 1e-300)
        error = max(abs(a - b) for a, b in zip(actual_state, expected_state))
        self.assertLess(error / state_scale, 1e-9)
        self.assertLess(abs(actual_energy - expected_energy) /
                        max(abs(expected_energy), 1e-300), 1e-9)

    def test_all_state_and_energy_at_zero_short_default_and_accumulated_steps(self):
        for loops, iterations in ((1, 0), (1, 1), (1, 37), (1, 20000), (16, 20000)):
            _, expected_energy, expected = variant._run(loops, iterations, None)
            expected_state = variant.base.snapshot(expected)
            for name in ("flat_pow", "flat_sqrt"):
                with self.subTest(kernel=name, loops=loops, iterations=iterations):
                    _, energy, actual = variant._run(loops, iterations, variant.KERNELS[name])
                    state = variant.base.snapshot(actual)
                    self.assert_close_state_energy(state, energy, expected_state, expected_energy)
                    if name == "flat_pow":
                        self.assertEqual(bits(state + [energy]),
                                         bits(expected_state + [expected_energy]))

    def test_repeated_advance_preserves_identity_and_uses_current_input_state(self):
        for name in ("flat_pow", "flat_sqrt"):
            expected = variant.base.load_upstream()
            actual = variant.base.load_upstream()
            identities = [(id(body), id(body[0]), id(body[1])) for body in actual.SYSTEM]
            for steps in (0, 1, 10, 37):
                with self.subTest(kernel=name, steps=steps):
                    # An external state edit between calls must be observed, not cached.
                    expected.SYSTEM[2][1][1] += .0001
                    actual.SYSTEM[2][1][1] += .0001
                    expected.advance(.01, steps)
                    variant.KERNELS[name](.01, steps, actual.SYSTEM, actual.PAIRS)
                    state, reference = snapshot(actual.SYSTEM), snapshot(expected.SYSTEM)
                    self.assert_close_state_energy(state, actual.report_energy(),
                                                 reference, expected.report_energy())
                    if name == "flat_pow":
                        self.assertEqual(bits(state), bits(reference))
                    self.assertEqual(identities,
                                     [(id(b), id(b[0]), id(b[1])) for b in actual.SYSTEM])

    def test_benchmark_runs_start_fresh_and_do_not_replace_baseline(self):
        _, expected_energy, expected = variant._run(2, 10, None)
        expected_bits = bits(snapshot(expected.SYSTEM) + [expected_energy])
        for name in ("flat_pow", "flat_sqrt"):
            _, first_energy, first = variant._run(2, 10, variant.KERNELS[name])
            _, second_energy, second = variant._run(2, 10, variant.KERNELS[name])
            self.assertEqual(bits(snapshot(first.SYSTEM) + [first_energy]),
                             bits(snapshot(second.SYSTEM) + [second_energy]))
            self.assertIsNot(first, second)
            self.assertIsNot(first.SYSTEM[0][1], second.SYSTEM[0][1])
            _, after_energy, after = variant._run(2, 10, None)
            self.assertEqual(bits(snapshot(after.SYSTEM) + [after_energy]), expected_bits)
            self.assertEqual(after.advance.__name__, "advance")

    def test_varied_state_masses_and_dt_preserve_the_reference_calculation(self):
        rng = random.Random(20260920)
        upstream = variant.base.load_upstream()
        for case in range(16):
            bodies = [([4. * i + rng.uniform(-.5, .5),
                        rng.uniform(-1., 1.), rng.uniform(-1., 1.)],
                       [rng.uniform(-.2, .2) for _ in range(3)],
                       rng.uniform(.05, 2.)) for i in range(5)]
            dt = (0., .001, .01, -.001)[case % 4]
            expected = copy.deepcopy(bodies)
            upstream.advance(dt, 100, expected, pairs_for(expected))
            expected_energy = upstream.report_energy(expected, pairs_for(expected))
            for name in ("flat_pow", "flat_sqrt"):
                with self.subTest(kernel=name, case=case, dt=dt):
                    actual = copy.deepcopy(bodies)
                    variant.KERNELS[name](dt, 100, actual, pairs_for(actual))
                    energy = upstream.report_energy(actual, pairs_for(actual))
                    self.assert_close_state_energy(snapshot(actual), energy,
                                                 snapshot(expected), expected_energy)
                    if name == "flat_pow":
                        self.assertEqual(bits(snapshot(actual) + [energy]),
                                         bits(snapshot(expected) + [expected_energy]))

    def test_rejects_noncanonical_pair_sequences_before_mutating_state(self):
        for name in ("flat_pow", "flat_sqrt"):
            for case in ("reordered", "reversed", "foreign", "missing", "self"):
                with self.subTest(kernel=name, case=case):
                    up = variant.base.load_upstream()
                    pairs = list(up.PAIRS)
                    if case == "reordered":
                        pairs[0], pairs[1] = pairs[1], pairs[0]
                    elif case == "reversed":
                        pairs[0] = pairs[0][::-1]
                    elif case == "foreign":
                        pairs[0] = (copy.deepcopy(pairs[0][0]), pairs[0][1])
                    elif case == "missing":
                        pairs.pop()
                    else:
                        pairs[0] = (up.SYSTEM[0], up.SYSTEM[0])
                    before = bits(snapshot(up.SYSTEM))
                    with self.assertRaises(ValueError):
                        variant.KERNELS[name](.01, 1, up.SYSTEM, pairs)
                    self.assertEqual(bits(snapshot(up.SYSTEM)), before)

    def test_rejects_unsupported_shape_aliases_and_component_types(self):
        for name in ("flat_pow", "flat_sqrt"):
            for case in ("four_bodies", "alias", "tuple_position", "short_velocity",
                         "integer_component", "integer_mass"):
                with self.subTest(kernel=name, case=case):
                    bodies = [[list(p), list(v), m]
                              for p, v, m in variant.base.load_upstream().SYSTEM]
                    if case == "four_bodies":
                        bodies.pop()
                    elif case == "alias":
                        bodies[1][0] = bodies[0][0]
                    elif case == "tuple_position":
                        bodies[0][0] = tuple(bodies[0][0])
                    elif case == "short_velocity":
                        bodies[0][1].pop()
                    elif case == "integer_component":
                        bodies[0][0][0] = 0
                    else:
                        bodies[0][2] = 1
                    before = copy.deepcopy(bodies)
                    with self.assertRaises(ValueError):
                        variant.KERNELS[name](.01, 1, bodies, pairs_for(bodies))
                    self.assertEqual(bodies, before)

    def test_rejects_invalid_step_count_or_dt_before_mutating_state(self):
        for name in ("flat_pow", "flat_sqrt"):
            for dt, n in ((.01, -1), (.01, 1.5), (.01, True), (1, 1)):
                with self.subTest(kernel=name, dt=dt, steps=n):
                    up = variant.base.load_upstream()
                    before = bits(snapshot(up.SYSTEM))
                    with self.assertRaises(ValueError):
                        variant.KERNELS[name](dt, n, up.SYSTEM, up.PAIRS)
                    self.assertEqual(bits(snapshot(up.SYSTEM)), before)


if __name__ == "__main__":
    unittest.main()
