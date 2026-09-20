#!/usr/bin/env python3
"""Exact pure-Python optimizations of the upstream raytrace benchmark.

``full`` is the default: safe guard fast paths, shadow-ray reuse, scalar sphere
intersections, invariant camera work, nearest-hit scanning and removal of a
checkerboard temporary. Arithmetic order, pixel conversion, EPSILON comparisons,
object order and the upstream scene are unchanged. Historical kernels remain
independently selectable. Fast paths target ordinary stock classes; subclasses
and custom primitives use original methods where specialization bypasses their
behavior. Rendering assumes scenes are not mutated concurrently or monkey-patched.

No upstream source is modified. Patches are scoped and restored on exceptions.
Setup is outside the upstream timer; scene construction, camera caches and all
rendering are inside it. Verification compares exact images before/after patching;
tests add primitive-bit, varied-scene, edge-case and fallback checks. These are
evidence for the tested contract, not proof for arbitrary Python objects.
"""

import argparse
import contextlib
import gc
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "bench"))

import bm_raytrace_upstream as base  # noqa: E402  (shared loader + harness)

TARGET_SEC = float(os.environ.get("TARGET_SEC", "3.0"))


# ---------------------------------------------------------------------------
# R1 — inlined type guards
# ---------------------------------------------------------------------------
def _r1_methods(up):
    """Build the six replacement methods, closed over upstream's classes.

    Arithmetic is copied verbatim. Stock operand fast paths avoid redundant
    predicates; subclasses and custom operands retain original polymorphism.
    """
    Vector = up.Vector
    Point = up.Point

    originals = {(cls, name): getattr(cls, name) for cls, name in (
        (Vector, "__add__"), (Vector, "__sub__"), (Vector, "dot"),
        (Vector, "cross"), (Point, "__add__"), (Point, "__sub__"))}

    # --- DISPATCH: the predicate selects the result type -------------------
    def v_add(self, other):                      # upstream: if other.isPoint()
        other_type = type(other)
        if other_type is not Point and other_type is not Vector:
            return originals[(Vector, "__add__")](self, other)
        if other_type is Point:
            return Point(self.x + other.x, self.y + other.y, self.z + other.z)
        return Vector(self.x + other.x, self.y + other.y, self.z + other.z)

    def p_sub(self, other):                      # upstream: if other.isPoint()
        other_type = type(other)
        if other_type is not Point and other_type is not Vector:
            return originals[(Point, "__sub__")](self, other)
        if other_type is Point:
            return Vector(self.x - other.x, self.y - other.y, self.z - other.z)
        return Point(self.x - other.x, self.y - other.y, self.z - other.z)

    # --- GUARD: Vector passes, Point raises --------------------------------
    def v_sub(self, other):                      # upstream: other.mustBeVector()
        if type(other) is not Vector:
            return originals[(Vector, "__sub__")](self, other)
        return Vector(self.x - other.x, self.y - other.y, self.z - other.z)

    def v_dot(self, other):                      # upstream: other.mustBeVector()
        if type(other) is not Vector:
            return originals[(Vector, "dot")](self, other)
        return (self.x * other.x) + (self.y * other.y) + (self.z * other.z)

    def v_cross(self, other):                    # upstream: other.mustBeVector()
        if type(other) is not Vector:
            return originals[(Vector, "cross")](self, other)
        return Vector(self.y * other.z - self.z * other.y,
                      self.z * other.x - self.x * other.z,
                      self.x * other.y - self.y * other.x)

    def p_add(self, other):                      # upstream: other.mustBeVector()
        if type(other) is not Vector:
            return originals[(Point, "__add__")](self, other)
        return Point(self.x + other.x, self.y + other.y, self.z + other.z)

    return [
        (Vector, "__add__", v_add),
        (Vector, "__sub__", v_sub),
        (Vector, "dot",     v_dot),
        (Vector, "cross",   v_cross),
        (Point,  "__add__", p_add),
        (Point,  "__sub__", p_sub),
    ]


def _shadow_light_is_visible(self, l, p):
    """Template rebound to upstream's globals by _shadow_methods."""
    if not self.objects:
        return True
    ray = Ray(p, l - p)
    for (o, s) in self.objects:
        t = o.intersectionTime(ray)
        if t is not None and t > EPSILON:
            return False
    return True


def _shadow_methods(up):
    # Resolve Ray and EPSILON in exactly the same module namespace as upstream.
    # Capturing their current values in a closure would change global lookups.
    fn = types.FunctionType(_shadow_light_is_visible.__code__,
                            up.Scene._lightIsVisible.__globals__,
                            name="_lightIsVisible")
    return [(up.Scene, "_lightIsVisible", fn)]


def _extra_methods(up, kernel):
    Point, Vector, Sphere, Halfspace = up.Point, up.Vector, up.Sphere, up.Halfspace
    original_sphere = Sphere.intersectionTime
    original_render = up.Scene.render
    original_colour = up.Scene.rayColour
    original_checker = up.CheckerboardSurface.baseColourAt
    original_visibility = up.Scene._lightIsVisible

    def sphere(self, ray):
        if (type(self) is not Sphere or type(self.centre) is not Point or
                type(ray) is not up.Ray or type(ray.point) is not Point or
                type(ray.vector) is not Vector):
            return original_sphere(self, ray)
        cp_x = self.centre.x - ray.point.x
        cp_y = self.centre.y - ray.point.y
        cp_z = self.centre.z - ray.point.z
        rv = ray.vector
        v = (cp_x * rv.x) + (cp_y * rv.y) + (cp_z * rv.z)
        discriminant = (self.radius * self.radius) - (
            ((cp_x * cp_x) + (cp_y * cp_y) + (cp_z * cp_z)) - v * v)
        if discriminant < 0:
            return None
        return v - up.math.sqrt(discriminant)

    active_scenes = set()

    def stock_scene(scene):
        if id(scene) in active_scenes:
            return True
        return (type(scene) is up.Scene and
                all(type(o) in (Sphere, Halfspace) and
                    type(surface) in (up.SimpleSurface, up.CheckerboardSurface)
                    for o, surface in scene.objects))

    def render(self, canvas):
        # Custom shaders/objects can mutate camera values or shared vectors.
        if (not stock_scene(self) or type(canvas) is not up.Canvas or
                type(self.position) is not Point or type(self.lookingAt) is not Point):
            return original_render(self, canvas)
        fovRadians = up.math.pi * (self.fieldOfView / 2.0) / 180.0
        halfWidth = up.math.tan(fovRadians)
        halfHeight = 0.75 * halfWidth
        width = halfWidth * 2
        height = halfHeight * 2
        pixelWidth = width / (canvas.width - 1)
        pixelHeight = height / (canvas.height - 1)
        eye = up.Ray(self.position, self.lookingAt - self.position)
        vpRight = eye.vector.cross(Vector.UP).normalized()
        vpUp = vpRight.cross(eye.vector).normalized()
        xcomponents = [vpRight.scale(x * pixelWidth - halfWidth)
                       for x in range(canvas.width)]
        active_scenes.add(id(self))
        try:
            for y in range(canvas.height):
                ycomp = vpUp.scale(y * pixelHeight - halfHeight)
                for x, xcomp in enumerate(xcomponents):
                    ray = up.Ray(eye.point, eye.vector + xcomp + ycomp)
                    colour = self.rayColour(ray)
                    canvas.plot(x, y, *colour)
        finally:
            active_scenes.discard(id(self))

    def trusted_render(self, canvas):
        if not stock_scene(self):
            return original_render(self, canvas)
        active_scenes.add(id(self))
        try:
            return original_render(self, canvas)
        finally:
            active_scenes.discard(id(self))

    def ray_colour(self, ray):
        if not stock_scene(self):
            return original_colour(self, ray)
        if self.recursionDepth > 3:
            return (0, 0, 0)
        try:
            self.recursionDepth = self.recursionDepth + 1
            best = None
            # Evaluate every primitive; equal distances retain the first hit.
            for o, surface in self.objects:
                t = o.intersectionTime(ray)
                if t is not None and t > -up.EPSILON:
                    if best is None or t < best[1]:
                        best = (o, t, surface)
            if best is None:
                return (0, 0, 0)
            o, t, surface = best
            p = ray.pointAtTime(t)
            return surface.colourAt(self, ray, p, o.normalAt(p))
        finally:
            self.recursionDepth = self.recursionDepth - 1

    def checker(self, p):
        if type(p) is not Point or type(up.Point.ZERO) is not Point:
            return original_checker(self, p)
        v = p - up.Point.ZERO
        # Retain division and multiplication exceptions. The discarded scale
        # result is an upstream bug: do not apply it to the checker coordinates.
        factor = 1.0 / self.checkSize
        factor * v.x
        factor * v.y
        factor * v.z
        if ((int(abs(v.x) + 0.5) + int(abs(v.y) + 0.5)
             + int(abs(v.z) + 0.5)) % 2):
            return self.otherColour
        return self.baseColour

    def visibility(self, light, point):
        if not stock_scene(self):
            return original_visibility(self, light, point)
        if not self.objects:
            return True
        ray = up.Ray(point, light - point)
        for o, surface in self.objects:
            t = o.intersectionTime(ray)
            if t is not None and t > up.EPSILON:
                return False
        return True

    entries = {
        "sphere_scalar": [(Sphere, "intersectionTime", sphere)],
        "camera": [(up.Scene, "render", render)],
        "nearest_hit": [(up.Scene, "rayColour", ray_colour),
                        (up.Scene, "render", trusted_render)],
        "checkerboard": [(up.CheckerboardSurface, "baseColourAt", checker)],
    }
    if kernel == "full":
        return (_r1_methods(up) + [(up.Scene, "_lightIsVisible", visibility)] +
                [entry for name, group in entries.items() for entry in group
                 if not (name == "nearest_hit" and entry[1] == "render")])
    return entries[kernel]

def _slot_methods(up):
    """Optional storage experiment; not the default public-class contract.

    Replacement classes deliberately have no instance __dict__ or weakrefs.
    Method code is reused verbatim and globals still resolve in upstream.
    Existing instances/subclasses remain instances of the original classes;
    consequently this experiment is limited to fresh stock scenes.
    """
    replacements = []
    for name, fields in (("Vector", ("x", "y", "z")),
                         ("Point", ("x", "y", "z")),
                         ("Ray", ("point", "vector"))):
        old = getattr(up, name)
        namespace = {key: value for key, value in old.__dict__.items()
                     if key not in ("__dict__", "__weakref__", "__slots__")}
        namespace["__slots__"] = fields
        new = type(name, (object,), namespace)
        if name == "Vector":
            for constant in ("ZERO", "RIGHT", "UP", "OUT"):
                obj = getattr(old, constant)
                setattr(new, constant, new(obj.x, obj.y, obj.z))
        elif name == "Point":
            obj = old.ZERO
            new.ZERO = new(obj.x, obj.y, obj.z)
        replacements.append((up, name, new))
    return replacements

def _methods(up, kernel):
    if kernel == "slots":
        return _slot_methods(up)
    if kernel == "shadow_ray":
        return _shadow_methods(up)
    if kernel == "guards":
        return _r1_methods(up)
    if kernel == "combined":
        return _r1_methods(up) + _shadow_methods(up)
    if kernel == "upstream":
        return []
    if kernel in ("sphere_scalar", "camera", "nearest_hit", "checkerboard", "full"):
        return _extra_methods(up, kernel)
    raise ValueError(f"unknown kernel: {kernel}")


@contextlib.contextmanager
def _patched(up, kernel):
    """Install the selected kernel and restore the cached upstream module."""
    if kernel == "full_slots":
        with _patched(up, "slots"):
            with _patched(up, "full"):
                yield
        return
    missing = object()
    saved = []
    try:
        for cls, name, fn in _methods(up, kernel):
            saved.append((cls, name, cls.__dict__.get(name, missing)))
            setattr(cls, name, fn)
        yield
    finally:
        for cls, name, old in reversed(saved):
            if old is missing:
                delattr(cls, name)
            else:
                setattr(cls, name, old)


def _bench_guards(loops, width, height, filename):
    """Drop-in for up.bench_raytrace with R1 active.

    up.bench_raytrace starts its own perf_counter INSIDE itself, so the
    patch/restore performed here is outside the measured region.
    """
    up = base.load_upstream()
    with _patched(up, "guards"):
        return up.bench_raytrace(loops, width, height, filename)


def _bench_shadow_ray(loops, width, height, filename):
    """Call upstream's timed function with only shadow-ray reuse active."""
    up = base.load_upstream()
    with _patched(up, "shadow_ray"):
        return up.bench_raytrace(loops, width, height, filename)


def _bench_combined(loops, width, height, filename):
    """Call upstream's timed function with guards and shadow-ray reuse active."""
    up = base.load_upstream()
    with _patched(up, "combined"):
        return up.bench_raytrace(loops, width, height, filename)


# Kernel registry. None => upstream, unmodified.
KERNELS = {
    "upstream": None,
    "guards":   _bench_guards,
    "shadow_ray": _bench_shadow_ray,
    "combined": _bench_combined,
}



def _make_bench(kernel):
    def bench(loops, width, height, filename):
        up = base.load_upstream()
        with _patched(up, kernel):
            return up.bench_raytrace(loops, width, height, filename)
    bench.__name__ = "_bench_" + kernel
    return bench


for _name in ("sphere_scalar", "camera", "nearest_hit", "checkerboard", "full", "slots", "full_slots"):
    KERNELS[_name] = _make_bench(_name)

def _method_state(up):
    """Snapshot every method this module can patch, including inherited ones."""
    return tuple((cls, name, name in cls.__dict__, getattr(cls, name))
                 for cls, name, _ in _methods(up, "full") + _slot_methods(up))


def _require_restored(state):
    for cls, name, owned, fn in state:
        if (name in cls.__dict__) != owned or getattr(cls, name) is not fn:
            raise AssertionError(f"patch leaked: {cls.__name__}.{name}")


def _render_frames(up, loops, width, height, kernel):
    """Capture every frame in a verification-only run, outside clean timing."""
    frames = []
    original = up.Canvas.__init__
    def capture(canvas, w, h):
        original(canvas, w, h)
        frames.append(canvas)
    try:
        up.Canvas.__init__ = capture
        with _patched(up, kernel):
            up.bench_raytrace(loops, width, height, None)
        return tuple(canvas.bytes.tobytes() for canvas in frames)
    finally:
        up.Canvas.__init__ = original


def verify(width, height, loops=1, kernel="full"):

    """Check all kernels against pre-patch and post-patch baseline renders."""
    up = base.load_upstream()
    state = _method_state(up)
    sizes = dict.fromkeys(((24, 24), (width, height), (37, 23)))
    for w, h in sizes:
        reference = base.render_checksum(w, h, None)
        if reference[1] != w * h * 3:
            raise AssertionError(f"upstream pixel count wrong at {w}x{h}")
        for name, fn in KERNELS.items():
            for _ in range(2):
                candidate = base.render_checksum(w, h, fn)
                _require_restored(state)
                if candidate != reference:
                    raise AssertionError(
                        f"IMAGE DIFFERS FROM UPSTREAM: {name} at {w}x{h}\n"
                        f"  upstream={reference} candidate={candidate}")
            after = base.render_checksum(w, h, None)
            _require_restored(state)
            if after != reference:
                raise AssertionError(f"baseline changed after {name} at {w}x{h}")
            print(f"  {w}x{h:<4} kernel={name:<10} sha={reference[0][:16]} "
                  "BIT-IDENTICAL; baseline restored")
    if loops < 1:
        raise ValueError("verification loops must be positive")
    reference_frames = _render_frames(up, loops, width, height, "upstream")
    candidate_frames = _render_frames(up, loops, width, height, kernel)
    after_frames = _render_frames(up, loops, width, height, "upstream")
    _require_restored(state)
    if len(reference_frames) != loops or candidate_frames != reference_frames or after_frames != reference_frames:
        raise AssertionError("batch images differ or frame count incorrect")
    print(f"batch verify: {loops} frames at {width}x{height}, kernel={kernel}, all BIT-IDENTICAL")
    print("verify: OK  all kernels; baseline before and after each candidate")


def calibrate(width, height, scene_fn):
    loops = 1
    while True:
        el, _ = base.benchmark(loops, width, height, scene_fn)
        if el >= TARGET_SEC or loops >= 4096:
            return max(1, loops)
        loops *= 2


def main():
    up = base.load_upstream()
    p = argparse.ArgumentParser(
        description="upstream raytrace with independent optimization kernels")
    p.add_argument("--mode", choices=("raw", "calibrate", "verify", "ablate"),
                   default="raw")
    p.add_argument("--loops", type=int, default=0)
    p.add_argument("--width", type=int, default=up.DEFAULT_WIDTH)
    p.add_argument("--height", type=int, default=up.DEFAULT_HEIGHT)
    p.add_argument("--kernel", choices=tuple(KERNELS), default="full",
                   help="timed kernel (verify always checks all kernels)")
    p.add_argument("--reps", type=int, default=7, help="ablation repetitions with rotating order")
    p.add_argument("--json", dest="json_path", help="save ablation samples and source hashes")
    p.add_argument("--no-gc", action="store_true")
    p.add_argument("--checksum", action="store_true")
    a = p.parse_args()

    if a.loops < 0 or a.reps < 1:
        p.error("loops must be nonnegative and reps positive")

    if a.no_gc:
        gc.disable()
    scene_fn = KERNELS[a.kernel]

    if a.mode == "calibrate":
        print(calibrate(a.width, a.height, scene_fn)); return 0

    if a.mode == "verify":
        verify(a.width, a.height, a.loops or 1, a.kernel)
        return 0

    if a.mode == "ablate":
        import statistics
        loops = a.loops or calibrate(a.width, a.height, None)
        reps = a.reps
        samples = dict((k, []) for k in KERNELS)
        names = list(KERNELS)
        for rep in range(reps):
            offset = rep % len(names)
            order = names[offset:] + names[:offset]
            for name in order:
                el, _ = base.benchmark(loops, a.width, a.height, KERNELS[name])
                samples[name].append(el)
        ref = statistics.median(samples["upstream"])
        print(f"ABLATION  loops={loops} {a.width}x{a.height} reps={reps}")
        print(f"{'kernel':<12}{'median s':>12}{'speedup':>10}{'time red.':>11}")
        print("-" * 45)
        for name in KERNELS:
            m = statistics.median(samples[name])
            print(f"{name:<12}{m:>12.6f}{ref / m:>9.4f}x"
                  f"{(1 - m / ref) * 100:>10.2f}%")
        if a.json_path:
            import hashlib
            import json
            import platform
            from pathlib import Path
            payload = {"python": sys.version, "platform": platform.platform(),
                       "loops": loops, "width": a.width, "height": a.height,
                       "repetitions": reps, "order": "rotating",
                       "gc_disabled": a.no_gc, "samples_seconds": samples,
                       "upstream_sha256": base.upstream_sha256(),
                       "variant_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
            Path(a.json_path).write_text(json.dumps(payload, indent=2) + "\n")
        return 0

    loops = a.loops or calibrate(a.width, a.height, scene_fn)
    elapsed, _ = base.benchmark(loops, a.width, a.height, scene_fn)
    rays = loops * a.width * a.height

    label = {"upstream": "unmodified reference",
             "guards": "exact-class guard specialization",
             "shadow_ray": "one shadow ray per visibility query",
             "combined": "guard specialization + shadow-ray reuse",
             "sphere_scalar": "scalar sphere arithmetic",
             "camera": "reuse camera components",
             "nearest_hit": "fused nearest intersection scan",
             "checkerboard": "remove discarded vector allocation",
             "full": "all exact pure-Python optimizations",
             "slots": "optional fresh-scene slotted classes",
             "full_slots": "full plus optional slotted classes"}[a.kernel]
    print(f"UPSTREAM raytrace — kernel={a.kernel} ({label})")
    print(f"resolution={a.width}x{a.height} loops={loops}")
    print(f"elapsed={elapsed:.6f} s  {elapsed / loops * 1e3:.3f} ms/frame")
    print(f"primary_rays={rays}  {rays / elapsed / 1000.0:.2f} kray/s")
    if a.checksum:
        cs, _ = base.render_checksum(a.width, a.height, scene_fn)
        print(f"checksum={cs}")
    print(f"RESULT total_sec={elapsed:.6f} loops={loops} "
          f"ms_per_frame={elapsed / loops * 1e3:.4f} "
          f"krays_per_sec={rays / elapsed / 1000.0:.4f} kernel={a.kernel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
