#!/usr/bin/env python3
"""
bench/bm_nbody_upstream.py — BASELINE wrapper around the REAL pyperformance
nbody kernel.

WHAT IS MEASURED
----------------
`upstream.bench_nbody()` itself — upstream's own timed loop, including its own
call to offset_momentum() and its own report_energy()/advance() sequence. This
wrapper adds a CLI and a correctness gate and nothing else. It defines no
physics.

WHY THIS MATTERS (a defect this file previously had)
----------------------------------------------------
An earlier version reimplemented bench_nbody's loop locally. The hot kernel
(advance) was still upstream's, but the harness structure was a private copy, so
a change to upstream's loop would not have been picked up. A tamper test on the
raytrace wrapper exposed the same class of bug there: editing upstream left the
result unchanged.

Both wrappers now call upstream's own bench function, so every byte of the
measured workload comes from upstream/. The tamper test in
tools/verify_upstream.sh proves it automatically.

HOW THE OPTIMIZED VARIANT SUBSTITUTES A KERNEL
-----------------------------------------------
upstream's bench_nbody() calls the module-global `advance`. An optimized variant
therefore swaps `up.advance` at module level and then calls upstream's OWN
bench_nbody(). The timed loop, state setup and energy reporting all remain
upstream's; only the named function changes. That keeps the before/after an
explicit, auditable one-symbol diff.

IMPORTANT — UPSTREAM MUTATES MODULE-LEVEL STATE
-----------------------------------------------
SYSTEM/PAIRS alias the lists inside BODIES and advance() mutates them in place,
so state accumulates across loops. That is upstream's own behaviour and is
preserved. Reproducibility comes from loading a FRESH module for every
measurement, so each run starts from pristine initial conditions.

Modes: raw | calibrate | verify
"""

import argparse
import gc
import hashlib
import importlib.util
import os
import sys
import time
import types

TARGET_SEC = float(os.environ.get("TARGET_SEC", "3.0"))
HERE = os.path.dirname(os.path.abspath(__file__))
UPSTREAM = os.path.join(HERE, "..", "upstream", "bm_nbody_upstream.py")

_COUNTER = 0


def load_upstream():
    """
    Import the upstream kernel with a FRESH module namespace every call.

    Fresh import is required, not merely tidy: upstream mutates BODIES/SYSTEM in
    place, so reusing the module would make each measurement start from the
    previous one's end state.

    A minimal pyperf stub is injected because upstream does `import pyperf` for
    perf_counter only. pyperf.perf_counter IS time.perf_counter, so timing
    semantics are unchanged and the upstream file stays byte-identical.
    """
    global _COUNTER

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

    _COUNTER += 1
    spec = importlib.util.spec_from_file_location(
        f"_upstream_nbody_{_COUNTER}", UPSTREAM)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
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
def benchmark(loops, iterations, advance=None):
    """
    Returns (elapsed_seconds, final_energy, module).

    `advance` optionally replaces upstream's advance() at MODULE level before
    upstream's own bench_nbody() runs. The timed loop remains upstream's.
    """
    up = load_upstream()
    if advance is not None:
        # upstream calls advance(0.01, iterations) with two positional args and
        # relies on the module-level defaults bodies=SYSTEM, pairs=PAIRS. Bind
        # THIS module's objects so the kernel mutates the state upstream is
        # actually timing. Getting this wrong silently measures a module that
        # never advances.
        import functools
        up.advance = functools.partial(advance, bodies=up.SYSTEM, pairs=up.PAIRS)
    elapsed = up.bench_nbody(loops, up.DEFAULT_REFERENCE, iterations)
    return elapsed, up.report_energy(), up


def snapshot(up):
    """Full state: positions and velocities of every body."""
    state = []
    for (r, v, m) in up.SYSTEM:
        state.extend([r[0], r[1], r[2], v[0], v[1], v[2]])
    return state


def calibrate(iterations, advance=None):
    loops = 1
    while True:
        el, _, _ = benchmark(loops, iterations, advance)
        if el >= TARGET_SEC or loops >= 4096:
            return max(1, loops)
        loops *= 2


def main():
    probe = load_upstream()
    p = argparse.ArgumentParser(
        description="upstream pyperformance nbody (baseline, unmodified)")
    p.add_argument("--mode", choices=("raw", "calibrate", "verify"), default="raw")
    p.add_argument("--loops", type=int, default=0, help="0 => auto-calibrate")
    p.add_argument("--iterations", type=int, default=0,
                   help="advance() steps per loop; 0 => upstream default")
    p.add_argument("--no-gc", action="store_true")
    a = p.parse_args()

    iters = a.iterations or probe.DEFAULT_ITERATIONS

    if a.mode == "calibrate":
        print(calibrate(iters)); return 0

    if a.mode == "verify":
        # Determinism over the FULL STATE, not just the energy scalar: two
        # different configurations can share an energy value.
        _, e1, up1 = benchmark(1, iters)
        _, e2, up2 = benchmark(1, iters)
        s1, s2 = snapshot(up1), snapshot(up2)
        assert e1 == e2, f"upstream nbody not deterministic: {e1!r} vs {e2!r}"
        assert s1 == s2, "upstream nbody STATE not deterministic"

        # Energy conservation, judged correctly for a symplectic integrator:
        # its error is BOUNDED and oscillatory, never exactly zero.
        up0 = load_upstream()
        up0.offset_momentum(up0.BODIES[up0.DEFAULT_REFERENCE])
        e0 = up0.report_energy()
        rel = abs(e1 - e0) / abs(e0)
        assert rel < 1e-3, f"energy not conserved: e0={e0!r} e1={e1!r} rel={rel:.3e}"

        # Momentum is an independent invariant: after offset_momentum the total
        # is ~0 and must stay there.
        px = sum(v[0] * m for (_r, v, m) in up1.SYSTEM)
        py = sum(v[1] * m for (_r, v, m) in up1.SYSTEM)
        pz = sum(v[2] * m for (_r, v, m) in up1.SYSTEM)
        pmag = (px * px + py * py + pz * pz) ** 0.5
        assert pmag < 1e-10, f"momentum not conserved: |p|={pmag:.3e}"

        print(f"verify: OK  iterations={iters}")
        print(f"  energy      = {e1!r}")
        print(f"  rel_drift   = {rel:.3e}  (symplectic: bounded, not zero)")
        print(f"  state deterministic over {len(s1)} values")
        print(f"  |momentum|  = {pmag:.3e}")
        print(f"  kernel source sha256 = {upstream_sha256()[:32]}")
        return 0

    loops = a.loops or calibrate(iters)
    if a.no_gc:
        gc.disable()

    elapsed, energy, up = benchmark(loops, iters)
    total_steps = loops * iters

    print("UPSTREAM pyperformance nbody kernel (unmodified)")
    print(f"  source: upstream/bm_nbody_upstream.py")
    print(f"  sha256: {upstream_sha256()[:32]}")
    print(f"bodies={len(up.SYSTEM)} pairs={len(up.PAIRS)} "
          f"iterations={iters} loops={loops}")
    print(f"elapsed={elapsed:.6f} s  {elapsed / loops * 1e3:.3f} ms/loop")
    print(f"energy={energy!r}")
    print(f"step_rate={total_steps / elapsed / 1e3:.2f} ksteps/s")
    print(f"RESULT total_sec={elapsed:.6f} loops={loops} "
          f"ms_per_loop={elapsed / loops * 1e3:.4f} energy={energy!r} "
          f"iterations={iters}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
