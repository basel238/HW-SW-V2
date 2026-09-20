#!/usr/bin/env python3
"""
Optimized variants of the authentic upstream pyperformance raytrace workload.

The default ``shadow_ray`` kernel constructs and normalizes one shadow Ray per
nonempty Scene._lightIsVisible query, then reuses it for each intersection test.
Upstream repeats the same construction for every object visited. The supplied
Sphere and Halfspace primitives only read the ray; the scene, intersection
order, early exit, strict EPSILON comparison and arithmetic expressions stay
unchanged. An empty object list still returns True without constructing a ray.
This assumes read-only intersection methods, as in the supplied benchmark;
custom objects that mutate their input ray are outside this optimization's
contract.

``upstream`` is the unmodified reference. ``guards`` retains the separate,
experimental exact-class specialization of six Vector/Point methods. It avoids
polymorphic guard calls but changes general API semantics: subclasses, custom
guard methods and overridden predicates can behave differently. Its arithmetic
is unchanged and its fixed-scene pixels must match, but a pixel hash does not
prove equivalence for arbitrary objects. A whole-frame instruction count divided
by a call count is not the marginal cost of a guard call, and the fraction of
calls removed is not a measured speedup.

``combined`` applies both shadow-ray reuse and the six guard specializations.
It inherits both contracts above; it is an explicit experimental choice, while
``shadow_ray`` remains the default. The gains can overlap and must be measured.

Patches are installed only while calling upstream's own bench_raytrace function
and restored even if it raises. Patch setup/restoration is outside upstream's
internal timer; ray construction, rendering and scene construction remain inside
it. Upstream files are never edited. ``--mode verify`` checks every kernel at
small, configured and nonsquare resolutions against a reference rendered before
the patch, and checks a fresh baseline after each candidate in the same process.
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

    Every arithmetic expression below is copied verbatim from upstream. The
    polymorphic predicates become exact-class tests, so this is a
    specialization for the supplied scene, not general API equivalence.
    """
    Vector = up.Vector
    Point = up.Point

    # --- DISPATCH: the predicate selects the result type -------------------
    def v_add(self, other):                      # upstream: if other.isPoint()
        if other.__class__ is Point:
            return Point(self.x + other.x, self.y + other.y, self.z + other.z)
        return Vector(self.x + other.x, self.y + other.y, self.z + other.z)

    def p_sub(self, other):                      # upstream: if other.isPoint()
        if other.__class__ is Point:
            return Vector(self.x - other.x, self.y - other.y, self.z - other.z)
        return Point(self.x - other.x, self.y - other.y, self.z - other.z)

    # --- GUARD: Vector passes, Point raises --------------------------------
    def v_sub(self, other):                      # upstream: other.mustBeVector()
        if other.__class__ is not Vector:
            raise TypeError('Points are not vectors!')
        return Vector(self.x - other.x, self.y - other.y, self.z - other.z)

    def v_dot(self, other):                      # upstream: other.mustBeVector()
        if other.__class__ is not Vector:
            raise TypeError('Points are not vectors!')
        return (self.x * other.x) + (self.y * other.y) + (self.z * other.z)

    def v_cross(self, other):                    # upstream: other.mustBeVector()
        if other.__class__ is not Vector:
            raise TypeError('Points are not vectors!')
        return Vector(self.y * other.z - self.z * other.y,
                      self.z * other.x - self.x * other.z,
                      self.x * other.y - self.y * other.x)

    def p_add(self, other):                      # upstream: other.mustBeVector()
        if other.__class__ is not Vector:
            raise TypeError('Points are not vectors!')
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


def _methods(up, kernel):
    if kernel == "shadow_ray":
        return _shadow_methods(up)
    if kernel == "guards":
        return _r1_methods(up)
    if kernel == "combined":
        return _r1_methods(up) + _shadow_methods(up)
    if kernel == "upstream":
        return []
    raise ValueError(f"unknown kernel: {kernel}")


@contextlib.contextmanager
def _patched(up, kernel):
    """Install the selected kernel and restore the cached upstream module."""
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


def _method_state(up):
    """Snapshot every method this module can patch, including inherited ones."""
    return tuple((cls, name, name in cls.__dict__, getattr(cls, name))
                 for cls, name, _ in _r1_methods(up) + _shadow_methods(up))


def _require_restored(state):
    for cls, name, owned, fn in state:
        if (name in cls.__dict__) != owned or getattr(cls, name) is not fn:
            raise AssertionError(f"patch leaked: {cls.__name__}.{name}")


def verify(width, height):
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
    p.add_argument("--kernel", choices=tuple(KERNELS), default="shadow_ray",
                   help="timed kernel (verify always checks all kernels)")
    p.add_argument("--no-gc", action="store_true")
    p.add_argument("--checksum", action="store_true")
    a = p.parse_args()

    if a.no_gc:
        gc.disable()
    scene_fn = KERNELS[a.kernel]

    if a.mode == "calibrate":
        print(calibrate(a.width, a.height, scene_fn)); return 0

    if a.mode == "verify":
        verify(a.width, a.height)
        return 0

    if a.mode == "ablate":
        import statistics
        loops = a.loops or calibrate(a.width, a.height, None)
        reps = 5
        samples = dict((k, []) for k in KERNELS)
        for _ in range(reps):
            for name, fn in KERNELS.items():
                el, _ = base.benchmark(loops, a.width, a.height, fn)
                samples[name].append(el)
        ref = statistics.median(samples["upstream"])
        print(f"ABLATION  loops={loops} {a.width}x{a.height} reps={reps}")
        print(f"{'kernel':<12}{'median s':>12}{'speedup':>10}{'time red.':>11}")
        print("-" * 45)
        for name in KERNELS:
            m = statistics.median(samples[name])
            print(f"{name:<12}{m:>12.6f}{ref / m:>9.4f}x"
                  f"{(1 - m / ref) * 100:>10.2f}%")
        return 0

    loops = a.loops or calibrate(a.width, a.height, scene_fn)
    elapsed, _ = base.benchmark(loops, a.width, a.height, scene_fn)
    rays = loops * a.width * a.height

    label = {"upstream": "unmodified reference",
             "guards": "exact-class guard specialization",
             "shadow_ray": "one shadow ray per visibility query",
             "combined": "guard specialization + shadow-ray reuse"}[a.kernel]
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
