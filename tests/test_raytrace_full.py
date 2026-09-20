"""Exact primitive and varied-scene regression checks for full raytrace kernel."""
import importlib.util
import math
from pathlib import Path
import random
import struct
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("raytrace_full_variant", ROOT / "variants/bm_raytrace_upstream_opt.py")
v = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(v)


def bits(value):
    return None if value is None else struct.pack("!d", value)


class RaytraceFullTests(unittest.TestCase):
    def setUp(self):
        self.up = v.base.load_upstream(force_reload=True)
        self.state = v._method_state(self.up)

    def tearDown(self):
        v._require_restored(self.state)

    def test_sphere_random_and_edge_distances_are_bit_identical(self):
        u = self.up
        rng = random.Random(1729)
        cases = [(u.Point(0., 0., z), radius, u.Point(x, 0., 0.), u.Vector(0., 0., 1.))
                 for z in (-2., -0., 0., 2.) for radius in (0., 1., 2.)
                 for x in (0., 1., math.nextafter(1., math.inf))]
        for _ in range(1000):
            cases.append((u.Point(*(rng.uniform(-10, 10) for _ in range(3))), rng.uniform(.01, 4),
                          u.Point(*(rng.uniform(-10, 10) for _ in range(3))),
                          u.Vector(*(rng.uniform(-1, 1) for _ in range(3)))))
        for centre, radius, point, direction in cases:
            sphere, ray = u.Sphere(centre, radius), u.Ray(point, direction)
            ref = sphere.intersectionTime(ray)
            for kernel in ("sphere_scalar", "full"):
                with v._patched(u, kernel):
                    self.assertEqual(bits(sphere.intersectionTime(ray)), bits(ref))

    def test_subclass_guards_and_predicates_keep_polymorphism(self):
        u = self.up
        class CustomVector(u.Vector):
            def mustBeVector(self):
                raise ValueError("custom guard")
            def isPoint(self):
                return True
        other = CustomVector(1, 2, 3)
        for kernel in ("guards", "combined", "full"):
            with v._patched(u, kernel):
                with self.assertRaisesRegex(ValueError, "custom guard"):
                    u.Vector(1, 2, 3).dot(other)
                self.assertIs(type(u.Vector(1, 2, 3) + other), u.Point)
                self.assertIs(type(u.Point(1, 2, 3) - other), u.Vector)
                with self.assertRaisesRegex(TypeError, "exceptions must derive"):
                    u.Vector(1, 2, 3).dot(u.Point(1, 2, 3))

    def test_scalar_falls_back_for_custom_point(self):
        u = self.up
        class CustomPoint(u.Point):
            def __sub__(self, other):
                raise ValueError("custom point")
        sphere = u.Sphere(CustomPoint(0, 0, 0), 1)
        with v._patched(u, "full"):
            with self.assertRaisesRegex(ValueError, "custom point"):
                sphere.intersectionTime(u.Ray(u.Point(1, 2, 3), u.Vector(0, 0, 1)))

    def make_scene(self, seed):
        u = self.up
        rng = random.Random(seed)
        scene = u.Scene()
        scene.position = u.Point(.1 * seed, 1.8, 10.)
        scene.lookingAt = u.Point(0., 2., -1.)
        scene.fieldOfView = 30 + seed * 3
        for _ in range(seed % 3):
            scene.addLight(u.Point(rng.uniform(-20, 20), 20, 10))
        for i in range(seed % 5):
            scene.addObject(u.Sphere(u.Point(rng.uniform(-3, 3), rng.uniform(0, 4), -3.), rng.uniform(.2, 2)),
                            u.SimpleSurface(baseColour=(.2, .5, .8), specularCoefficient=.1 * (seed % 4)))
        if seed % 2:
            scene.addObject(u.Halfspace(u.Point(0, 0, 0), u.Vector.UP),
                            u.CheckerboardSurface(checkSize=.25 + seed))
        return scene

    def test_varied_scene_images_all_candidates(self):
        u = self.up
        for seed in range(10):
            width, height = 9 + seed, 7 + seed % 3
            reference_canvas = u.Canvas(width, height)
            self.make_scene(seed).render(reference_canvas)
            for kernel in v.KERNELS:
                with v._patched(u, kernel):
                    scene, canvas = self.make_scene(seed), u.Canvas(width, height)
                    scene.render(canvas)
                self.assertEqual(canvas.bytes, reference_canvas.bytes, (seed, kernel))
                self.assertEqual(scene.recursionDepth, 0)

    def test_camera_primary_rays_match_component_bits(self):
        u = self.up
        def capture(kernel):
            scene, canvas = self.make_scene(4), u.Canvas(13, 9)
            rays = []
            def colour(ray):
                rays.append(tuple(bits(component) for obj in (ray.point, ray.vector)
                                  for component in (obj.x, obj.y, obj.z)))
                return (0, 0, 0)
            scene.rayColour = colour
            with v._patched(u, kernel):
                scene.render(canvas)
            return rays
        self.assertEqual(capture("camera"), capture("upstream"))
        self.assertEqual(capture("full"), capture("upstream"))

    def test_raw_pixel_colours_match_before_quantization(self):
        u = self.up
        original_plot = u.Canvas.plot
        def capture(kernel, seed):
            colours = []
            def plot(canvas, x, y, r, g, b):
                colours.append((x, y, bits(r), bits(g), bits(b)))
                original_plot(canvas, x, y, r, g, b)
            with v._patched(u, kernel), mock.patch.object(u.Canvas, "plot", plot):
                self.make_scene(seed).render(u.Canvas(17, 13))
            return colours
        for seed in (3, 4, 7, 9):
            reference = capture("upstream", seed)
            for kernel in ("full", "full_slots"):
                self.assertEqual(capture(kernel, seed), reference, (seed, kernel))

    def test_nearest_ties_epsilon_and_all_primitives_are_visited(self):
        u = self.up
        # Stock sphere instances with instrumented methods exercise scanning;
        # custom classes intentionally use the upstream fallback.
        for distances in ([1., 1., 2.], [None, -u.EPSILON, 0.], [None, float('nan'), float('inf')]):
            scene = u.Scene()
            visited = []
            for index, distance in enumerate(distances):
                obj = u.Sphere(u.Point(0, 0, 0), 1)
                obj.intersectionTime = lambda ray, i=index, t=distance: (visited.append(i), t)[1]
                obj.normalAt = lambda p: u.Vector.UP
                surface = u.SimpleSurface(specularCoefficient=0, lambertCoefficient=0)
                surface.colourAt = lambda *args, i=index: (i, 0, 0)
                scene.addObject(obj, surface)
            ray = u.Ray(u.Point(0, 0, 0), u.Vector(0, 0, 1))
            ref = scene.rayColour(ray)
            visited.clear()
            with v._patched(u, "nearest_hit"):
                self.assertEqual(scene.rayColour(ray), ref)
            self.assertEqual(visited, [0, 1, 2])
            self.assertEqual(scene.recursionDepth, 0)

    def test_custom_mutating_shadow_primitive_uses_fresh_rays(self):
        u = self.up
        seen = []
        class Custom:
            def intersectionTime(self, ray):
                seen.append(ray.vector.z)
                ray.vector.z = 100
                return None
        scene = u.Scene()
        scene.objects = [(Custom(), None), (Custom(), None)]
        with v._patched(u, "full"):
            self.assertTrue(scene._lightIsVisible(u.Point(0, 0, 1), u.Point(0, 0, 0)))
        self.assertEqual(seen, [1., 1.])

    def test_checker_preserves_zero_size_exception_and_ignored_scale(self):
        u = self.up
        for size in (0, .1, 1, 7, -3):
            surface = u.CheckerboardSurface(checkSize=size)
            point = u.Point(1.2, -3.4, .1)
            if size == 0:
                with v._patched(u, "full"), self.assertRaises(ZeroDivisionError):
                    surface.baseColourAt(point)
            else:
                expected = surface.baseColourAt(point)
                with v._patched(u, "full"):
                    self.assertEqual(surface.baseColourAt(point), expected)

    def test_all_patches_restore_on_render_exception(self):
        u = self.up
        for name, fn in v.KERNELS.items():
            if fn is None:
                continue
            with mock.patch.object(u, "bench_raytrace", side_effect=ValueError("render failed")):
                with self.assertRaisesRegex(ValueError, "render failed"):
                    fn(1, 24, 24, None)
            v._require_restored(self.state)

    def test_slots_are_scoped_and_preserve_fresh_scene_class_behavior(self):
        u = self.up
        before = u.Vector, u.Point, u.Ray
        with v._patched(u, "full_slots"):
            vector = u.Vector(1., 2., 3.)
            point = u.Point(0., 0., 0.)
            self.assertFalse(hasattr(vector, "__dict__"))
            self.assertIs(type(vector + point), u.Point)
            self.assertIs(type(point - point), u.Vector)
            self.assertIs(type(u.Vector.UP), u.Vector)
            self.assertIs(type(u.Point.ZERO), u.Point)
        self.assertEqual((u.Vector, u.Point, u.Ray), before)

    def test_batch_captures_each_frame_and_restores_canvas(self):
        u = self.up
        init = u.Canvas.__init__
        baseline = v._render_frames(u, 3, 24, 24, "upstream")
        candidate = v._render_frames(u, 3, 24, 24, "full")
        self.assertEqual(len(candidate), 3)
        self.assertEqual(candidate, baseline)
        self.assertIs(u.Canvas.__init__, init)


if __name__ == "__main__":
    unittest.main()
