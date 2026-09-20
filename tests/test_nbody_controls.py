"""Numerical checks for independent nbody structural experiments."""
import copy
import importlib.util
import math
from pathlib import Path
import random
import struct
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('controls', ROOT/'experiments/nbody_controls.py')
controls = importlib.util.module_from_spec(spec)
spec.loader.exec_module(controls)


def state_bits(bodies, energy):
    values = [v for r, vel, _ in bodies for v in r + vel] + [energy]
    if not all(math.isfinite(v) for v in values):
        raise AssertionError('nonfinite state')
    return struct.pack('!31d', *values)


def pairs(bodies):
    return [(bodies[i], bodies[j]) for i in range(4) for j in range(i+1, 5)]


class NbodyControlTests(unittest.TestCase):
    def test_all_controls_preserve_accumulated_benchmark_state(self):
        controls.verify(list(controls.KERNELS), 2, 2000)

    def test_controls_use_varied_actual_state_masses_and_timestep(self):
        rng = random.Random(20260920)
        up = controls.production.base.load_upstream()
        for trial in range(8):
            original = [([float(i*10)+rng.random(), rng.random(), rng.random()],
                         [rng.uniform(-.1,.1) for _ in range(3)], rng.uniform(.1, 5.))
                        for i in range(5)]
            dt = [.001, .01, -.001, 0.][trial % 4]
            reference = copy.deepcopy(original)
            up.advance(dt, 100, reference, pairs(reference))
            expected = state_bits(reference, up.report_energy(reference, pairs(reference)))
            for name, fn in controls.KERNELS.items():
                if fn is None:
                    continue
                with self.subTest(trial=trial, kernel=name):
                    actual = copy.deepcopy(original)
                    fn(dt, 100, actual, pairs(actual))
                    self.assertEqual(state_bits(actual, up.report_energy(actual, pairs(actual))), expected)


if __name__ == '__main__':
    unittest.main()
