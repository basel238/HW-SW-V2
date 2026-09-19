#!/usr/bin/env python3
"""
bench/bm_raytrace_upstream.py — BASELINE wrapper around the REAL pyperformance
raytrace kernel.

WHAT IS MEASURED
----------------
`upstream.bench_raytrace()` itself — upstream's own timed loop, including its
own scene construction. This wrapper adds a CLI and a correctness gate and
nothing else. It defines no rendering code and no scene.

WHY THIS MATTERS (a defect this file previously had)
----------------------------------------------------
An earlier version of this wrapper TRANSCRIBED upstream's scene into a local
`render_once()` instead of calling `bench_raytrace()`. The rendering classes
still came from upstream, but the scene definition was a private copy. A tamper
test exposed it: editing the sphere radius in upstream/ from 2 to 2.5 left the
rendered checksum UNCHANGED, proving that part of the workload was not actually
sourced from upstream.

The wrapper now calls `up.bench_raytrace(...)` directly, so every byte of the
measured workload — algorithms AND scene — comes from upstream/. Re-running the
tamper test now changes the checksum, which is the property that makes the
"we measure the real benchmark" claim verifiable rather than asserted.

HOW THE CHECKSUM IS OBTAINED WITHOUT DUPLICATING ANYTHING
----------------------------------------------------------
`bench_raytrace(loops, width, height, filename)` returns only a duration, but it
writes the rendered canvas to `filename` as a PPM — and critically, it does so
AFTER stopping its timer:

    dt = pyperf.perf_counter() - t0
    if filename:
        canvas.write_ppm(filename)
    return dt

So passing a filename yields the exact pixels upstream produced, without
affecting the measured time. Verification hashes that PPM. Timed runs pass
filename=None.

Modes: raw | calibrate | verify
"""

import argparse
import gc
import hashlib
import importlib.util
import os
import sys
import tempfile
import time
import types

TARGET_SEC = float(os.environ.get("TARGET_SEC", "3.0"))
HERE = os.path.dirname(os.path.abspath(__file__))
UPSTREAM = os.path.join(HERE, "..", "upstream", "bm_raytrace_upstream.py")

_MOD = None


def load_upstream(force_reload=False):
    """
    Import the upstream kernel.

    A minimal pyperf stub is injected because upstream does `import pyperf` for
    perf_counter only; stubbing it keeps the upstream file byte-identical while
    letting the wrapper run under the system interpreter with no venv.
    pyperf.perf_counter IS time.perf_counter, so timing semantics are unchanged.
    """
    global _MOD
    if _MOD is not None and not force_reload:
        return _MOD

    if "pyperf" not in sys.modules:
        stub = types.ModuleType("pyperf")
        stub.perf_counter = time.perf_counter

        class _Runner:  # present only so `import pyperf` cannot fail
            def __init__(self, *a, **k):
                raise RuntimeError("pyperf.Runner is unavailable in this harness")
        stub.Runner = _Runner
        sys.modules["pyperf"] = stub

    if not os.path.exists(UPSTREAM):
        sys.exit(f"missing upstream kernel: {UPSTREAM}\n"
                 f"Run ./setup/05_get_upstream.sh to extract it from the "
                 f"installed pyperformance package.")

    spec = importlib.util.spec_from_file_location("_upstream_raytrace", UPSTREAM)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _MOD = mod
    return mod


def upstream_sha256():
    """Hash of the kernel source actually loaded — recorded in run output."""
    try:
        with open(UPSTREAM, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()
    except OSError:
        return "unavailable"


# ---------------------------------------------------------------------------
# Measurement — upstream's own timed function, called directly
# ---------------------------------------------------------------------------
def benchmark(loops, width, height, bench_fn=None):
    """
    Returns (elapsed_seconds, None).

    `bench_fn` lets an optimized variant substitute its own bench function while
    keeping this harness identical; None means upstream's own.
    """
    up = load_upstream()
    fn = bench_fn if bench_fn is not None else up.bench_raytrace
    elapsed = fn(loops, width, height, None)
    return elapsed, None


def render_checksum(width, height, bench_fn=None):
    """
    SHA-256 of the pixels upstream produced, via its own PPM writer.
    The write happens outside upstream's timed region, so this does not
    perturb any measurement.
    """
    up = load_upstream()
    fn = bench_fn if bench_fn is not None else up.bench_raytrace
    fd, path = tempfile.mkstemp(suffix=".ppm")
    os.close(fd)
    try:
        fn(1, width, height, path)
        with open(path, "rb") as fh:
            data = fh.read()
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
    # Strip the "P6 W H 255\n" header so the hash covers pixels only, making it
    # comparable across renderers that might format the header differently.
    parts = data.split(b"\n", 1)
    pixels = parts[1] if len(parts) == 2 else data
    return hashlib.sha256(pixels).hexdigest(), len(pixels)


def calibrate(width, height, bench_fn=None):
    loops = 1
    while True:
        el, _ = benchmark(loops, width, height, bench_fn)
        if el >= TARGET_SEC or loops >= 4096:
            return max(1, loops)
        loops *= 2


def main():
    up = load_upstream()
    p = argparse.ArgumentParser(
        description="upstream pyperformance raytrace (baseline, unmodified)")
    p.add_argument("--mode", choices=("raw", "calibrate", "verify"), default="raw")
    p.add_argument("--loops", type=int, default=0, help="0 => auto-calibrate")
    p.add_argument("--width", type=int, default=up.DEFAULT_WIDTH)
    p.add_argument("--height", type=int, default=up.DEFAULT_HEIGHT)
    p.add_argument("--no-gc", action="store_true")
    p.add_argument("--checksum", action="store_true")
    a = p.parse_args()

    if a.mode == "calibrate":
        print(calibrate(a.width, a.height)); return 0

    if a.mode == "verify":
        # Determinism at the MEASURED resolution as well as small and odd sizes.
        for (w, h) in [(24, 24), (a.width, a.height), (37, 23)]:
            s1, n1 = render_checksum(w, h)
            s2, _ = render_checksum(w, h)
            assert s1 == s2, f"upstream raytrace not deterministic at {w}x{h}"
            assert n1 == w * h * 3, f"pixel count wrong at {w}x{h}: {n1}"
            print(f"  {w}x{h:<4} sha={s1[:16]} pixels={n1}")
        print("verify: OK  (upstream kernel, unmodified)")
        print(f"  kernel source sha256 = {upstream_sha256()[:32]}")
        return 0

    loops = a.loops or calibrate(a.width, a.height)
    if a.no_gc:
        # The cyclic GC fires on allocation counts. Upstream allocates a Vector
        # or Point per arithmetic operation, so collector pauses would land
        # inside the timed region and show up in the profile as collect().
        gc.disable()

    elapsed, _ = benchmark(loops, a.width, a.height)
    rays = loops * a.width * a.height

    print("UPSTREAM pyperformance raytrace kernel (unmodified)")
    print(f"  source: upstream/bm_raytrace_upstream.py")
    print(f"  sha256: {upstream_sha256()[:32]}")
    print(f"resolution={a.width}x{a.height} loops={loops}")
    print(f"elapsed={elapsed:.6f} s  {elapsed / loops * 1e3:.3f} ms/frame")
    print(f"primary_rays={rays}  {rays / elapsed / 1000.0:.2f} kray/s")
    if a.checksum:
        cs, _ = render_checksum(a.width, a.height)
        print(f"checksum={cs}")
    print(f"RESULT total_sec={elapsed:.6f} loops={loops} "
          f"ms_per_frame={elapsed / loops * 1e3:.4f} "
          f"krays_per_sec={rays / elapsed / 1000.0:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
