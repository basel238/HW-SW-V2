"""Focused correctness checks; run: python3 -B -m unittest discover -s tests -v."""

import contextlib
import gc
import importlib.util
import io
import math
from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "raytrace_variant", ROOT / "variants" / "bm_raytrace_upstream_opt.py")
variant = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(variant)


class RaytraceShadowTests(unittest.TestCase):
    def setUp(self):
        self.up = variant.base.load_upstream(force_reload=True)
        self.state = variant._method_state(self.up)

    def tearDown(self):
        variant._require_restored(self.state)

    def query(self, distances, kernel):
        up = self.up
        visited, rays, constructed = [], [], []

        class Hit:
            def __init__(self, index, distance):
                self.index, self.distance = index, distance

            def intersectionTime(self, ray):
                visited.append(self.index)
                rays.append(ray)
                return self.distance

        original_ray = up.Ray

        def counted_ray(point, direction):
            ray = original_ray(point, direction)
            constructed.append(ray)
            return ray

        scene = up.Scene()
        scene.objects = [(Hit(i, t), None) for i, t in enumerate(distances)]
        p, light = up.Point(1, 2, 3), up.Point(4, 6, 8)
        with variant._patched(up, kernel):
            # Patch AFTER installing the method: globals must resolve at call time.
            with mock.patch.object(up, "Ray", counted_ray):
                result = scene._lightIsVisible(light, p)
        return result, visited, rays, constructed

    def test_reuses_one_ray_and_preserves_geometry_and_object_order(self):
        baseline = self.query([None, -1, 0, self.up.EPSILON], "upstream")
        candidate = self.query([None, -1, 0, self.up.EPSILON], "shadow_ray")
        self.assertEqual(baseline[:2], candidate[:2])
        self.assertEqual(candidate[:2], (True, [0, 1, 2, 3]))
        self.assertEqual(len(baseline[3]), 4)
        self.assertEqual(len(candidate[3]), 1)
        self.assertTrue(all(ray is candidate[3][0] for ray in candidate[2]))
        for before, after in zip(baseline[2], candidate[2]):
            self.assertEqual(vars(before.point), vars(after.point))
            self.assertEqual(vars(before.vector), vars(after.vector))

    def test_epsilon_is_strict_and_first_blocker_exits_early(self):
        distances = [None, -1, 0, self.up.EPSILON,
                     math.nextafter(self.up.EPSILON, math.inf), 1]
        for kernel in ("upstream", "shadow_ray", "combined"):
            with self.subTest(kernel=kernel):
                visible, visited, _, constructed = self.query(distances, kernel)
                self.assertFalse(visible)
                self.assertEqual(visited, [0, 1, 2, 3, 4])
                self.assertEqual(len(constructed), 5 if kernel == "upstream" else 1)

    def test_empty_scene_does_not_construct_or_normalize_ray(self):
        up = self.up
        scene, point = up.Scene(), up.Point(1, 2, 3)
        for kernel in ("upstream", "shadow_ray", "combined"):
            with self.subTest(kernel=kernel), variant._patched(up, kernel):
                with mock.patch.object(up, "Ray", side_effect=AssertionError("Ray called")):
                    self.assertTrue(scene._lightIsVisible(point, point))

    def test_global_epsilon_is_not_captured_when_patch_is_built(self):
        up = self.up
        scene = up.Scene()
        scene.objects = [(mock.Mock(intersectionTime=lambda ray: 0.5), None)]
        point, light = up.Point(0, 0, 0), up.Point(1, 0, 0)
        with variant._patched(up, "shadow_ray"):
            with mock.patch.object(up, "EPSILON", 1):
                self.assertTrue(scene._lightIsVisible(light, point))
            self.assertFalse(scene._lightIsVisible(light, point))

    def test_shadow_does_not_install_guard_specialization(self):
        up = self.up
        with variant._patched(up, "shadow_ray"):
            for cls, name, _, fn in self.state:
                if cls is not up.Scene:
                    self.assertIs(getattr(cls, name), fn)
            self.assertIsNot(up.Scene._lightIsVisible, self.state[-1][3])
            self.assertIs(variant.base.load_upstream(), up)

    def test_combined_installs_both_changes_and_reuses_one_ray(self):
        with variant._patched(self.up, "combined"):
            for cls, name, _, original in self.state:
                self.assertIsNot(getattr(cls, name), original)
        baseline = self.query([None, -1, 0, self.up.EPSILON], "upstream")
        candidate = self.query([None, -1, 0, self.up.EPSILON], "combined")
        self.assertEqual(candidate[:2], baseline[:2])
        self.assertEqual(len(candidate[3]), 1)
        self.assertTrue(all(ray is candidate[3][0] for ray in candidate[2]))
        for before, after in zip(baseline[2], candidate[2]):
            self.assertEqual(vars(before.point), vars(after.point))
            self.assertEqual(vars(before.vector), vars(after.vector))

    def test_wrappers_restore_after_success_and_exception(self):
        up = self.up
        for kernel in ("guards", "shadow_ray", "combined"):
            for fail in (False, True):
                with self.subTest(kernel=kernel, fail=fail):
                    def bench(loops, width, height, filename):
                        self.assertEqual((loops, width, height, filename), (1, 24, 24, None))
                        for cls, name, _, original in self.state:
                            changed = (kernel == "combined" or
                                       (cls is up.Scene) == (kernel == "shadow_ray"))
                            if changed:
                                self.assertIsNot(getattr(cls, name), original)
                            else:
                                self.assertIs(getattr(cls, name), original)
                        if fail:
                            raise RuntimeError("intersection failed")
                        return 1.25

                    with mock.patch.object(up, "bench_raytrace", bench):
                        if fail:
                            with self.assertRaisesRegex(RuntimeError, "intersection failed"):
                                variant.KERNELS[kernel](1, 24, 24, None)
                        else:
                            self.assertEqual(variant.KERNELS[kernel](1, 24, 24, None), 1.25)
                    variant._require_restored(self.state)

    def test_intersection_exception_restores_method(self):
        up = self.up
        scene = up.Scene()
        bad = mock.Mock()
        bad.intersectionTime.side_effect = ValueError("bad intersection")
        scene.objects = [(bad, None)]
        with self.assertRaisesRegex(ValueError, "bad intersection"):
            with variant._patched(up, "shadow_ray"):
                scene._lightIsVisible(up.Point(1, 0, 0), up.Point(0, 0, 0))
        variant._require_restored(self.state)

    def test_all_kernel_pixels_and_same_process_baseline_restoration(self):
        with contextlib.redirect_stdout(io.StringIO()):
            variant.verify(100, 100)

    def test_verify_rejects_leaked_patch_even_when_pixels_match(self):
        up = self.up
        original = up.Scene._lightIsVisible

        def leaking_render(width, height, fn=None):
            if fn is not None:
                up.Scene._lightIsVisible = lambda *args: True
            return "same hash", width * height * 3

        try:
            with mock.patch.object(variant.base, "render_checksum", leaking_render):
                with contextlib.redirect_stdout(io.StringIO()):
                    with self.assertRaisesRegex(AssertionError, "patch leaked"):
                        variant.verify(24, 24)
        finally:
            up.Scene._lightIsVisible = original

    def test_cli_defaults_to_shadow_ray(self):
        args = ["raytrace", "--loops", "1", "--width", "24", "--height", "24"]
        with mock.patch.object(sys, "argv", args):
            with mock.patch.object(variant.base, "benchmark", return_value=(1.0, None)) as bench:
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(variant.main(), 0)
                self.assertIs(bench.call_args.args[3], variant.KERNELS["shadow_ray"])

    def test_no_gc_applies_to_calibration_and_ablation(self):
        enabled = gc.isenabled()

        def benchmark(*args):
            self.assertFalse(gc.isenabled())
            return variant.TARGET_SEC + 1, None

        try:
            for mode in ("calibrate", "ablate"):
                gc.enable()
                with self.subTest(mode=mode):
                    args = ["raytrace", "--mode", mode, "--no-gc"]
                    with mock.patch.object(sys, "argv", args):
                        with mock.patch.object(variant.base, "benchmark", benchmark):
                            with contextlib.redirect_stdout(io.StringIO()):
                                self.assertEqual(variant.main(), 0)
        finally:
            gc.enable() if enabled else gc.disable()


if __name__ == "__main__":
    unittest.main()
