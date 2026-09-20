#!/usr/bin/env python3
"""
Isolated optimization candidates for the authentic pyperformance nbody kernel.
The reference in upstream/ is unchanged. The shared wrapper calls upstream's
own timed benchmark and substitutes only advance(), bound to that run's state.

DEFAULT: GROUPED LOCAL STATE
---------------------------
Upstream already unpacks position coordinates into locals for each pair. The
new `grouped` candidate goes further: it retains the first body's position and
velocity components across consecutive pairs with that identical first body.
Second-body velocity updates remain immediate; the first body's velocity is
written back after its group. Positions move only after every pair is handled.

Pair order, each floating-point expression, the power operation, and the order
of increments to every velocity component are preserved. Groups contain body
references, are never sorted, and are built once per advance() call INSIDE the
upstream timer. State is reloaded at the start of each group and timestep.
As in upstream's five-body workload, bodies have distinct mutable position and
velocity lists and no pair contains the same body twice. This is a workload
optimization, not a generic API for aliased bodies or side-effecting containers.

For ten pairs arranged as four first-body groups, pair processing reduces each
of position-component reads, velocity-component reads, and velocity-component
writes from 60 to 42 per timestep. That removes 54 component accesses per step
(1,080,000 at 20,000 steps), counting reads performed by unpacking. These are
source-level access counts, not machine instructions or a speedup prediction.
Float arithmetic and result allocation remain; extra grouping/loop overhead
also remains. Target-VM performance must be measured before claiming a gain.

SEPARATE CANDIDATES
------------------
    upstream   original upstream advance(), unmodified control
    grouped    consecutive-pair reuse, original power arithmetic (default)
    sqrt       existing inverse-power rewrite with locally bound sqrt
    hoist      existing per-pair velocity loads/stores; no cross-pair reuse
    full       existing sqrt + per-pair hoist combination
The legacy candidates are retained independently; `grouped` does not enable
sqrt or combine with `full`.

CORRECTNESS
-----------
Verify mode checks all candidates at the requested iterations AND loops
(default one loop). Grouped must have finite, bit-identical energy and all 30
position/velocity components. Legacy candidates retain their previous 1e-9
relative-energy and norm-relative-state tolerance, because sqrt changes
rounding. The state tolerance is max absolute error divided by the maximum
absolute reference component; it is not a per-component relative bound.
"""

import argparse
import gc
import os
import sys
from math import isfinite, sqrt
import struct

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "bench"))

import bm_nbody_upstream as base  # noqa: E402  (shared loader + harness)

TARGET_SEC = float(os.environ.get("TARGET_SEC", "3.0"))



# ---------------------------------------------------------------------------
# [U1] + [U2] — replace pow() with sqrt(), bind sqrt as a fast local.
# Signature matches upstream advance(dt, n, bodies, pairs) exactly.
# ---------------------------------------------------------------------------
def advance_sqrt(dt, n, bodies=None, pairs=None, _sqrt=sqrt):
    for _ in range(n):
        for (([x1, y1, z1], v1, m1),
             ([x2, y2, z2], v2, m2)) in pairs:
            dx = x1 - x2
            dy = y1 - y2
            dz = z1 - z2
            d2 = dx * dx + dy * dy + dz * dz
            # [U1] Same real-number identity for d2 > 0; rounding may differ.
            mag = dt / (d2 * _sqrt(d2))
            b1m = m1 * mag
            b2m = m2 * mag
            v1[0] -= dx * b2m
            v1[1] -= dy * b2m
            v1[2] -= dz * b2m
            v2[0] += dx * b1m
            v2[1] += dy * b1m
            v2[2] += dz * b1m
        for (r, [vx, vy, vz], m) in bodies:
            r[0] += dt * vx
            r[1] += dt * vy
            r[2] += dt * vz


# ---------------------------------------------------------------------------
# [U3] only — velocity component hoisting, keeping upstream's pow().
# Isolated so the ablation can show whether it helps at all.
# ---------------------------------------------------------------------------
def advance_hoist(dt, n, bodies=None, pairs=None):
    for _ in range(n):
        for (([x1, y1, z1], v1, m1),
             ([x2, y2, z2], v2, m2)) in pairs:
            dx = x1 - x2
            dy = y1 - y2
            dz = z1 - z2
            mag = dt * ((dx * dx + dy * dy + dz * dz) ** (-1.5))
            b1m = m1 * mag
            b2m = m2 * mag
            a0 = v1[0]; a1 = v1[1]; a2 = v1[2]
            c0 = v2[0]; c1 = v2[1]; c2 = v2[2]
            v1[0] = a0 - dx * b2m
            v1[1] = a1 - dy * b2m
            v1[2] = a2 - dz * b2m
            v2[0] = c0 + dx * b1m
            v2[1] = c1 + dy * b1m
            v2[2] = c2 + dz * b1m
        for (r, [vx, vy, vz], m) in bodies:
            r[0] += dt * vx
            r[1] += dt * vy
            r[2] += dt * vz


# ---------------------------------------------------------------------------
# full — [U1] + [U2] + [U3]
# ---------------------------------------------------------------------------
def advance_full(dt, n, bodies=None, pairs=None, _sqrt=sqrt):
    for _ in range(n):
        for (([x1, y1, z1], v1, m1),
             ([x2, y2, z2], v2, m2)) in pairs:
            dx = x1 - x2
            dy = y1 - y2
            dz = z1 - z2
            d2 = dx * dx + dy * dy + dz * dz
            mag = dt / (d2 * _sqrt(d2))
            b1m = m1 * mag
            b2m = m2 * mag
            a0 = v1[0]; a1 = v1[1]; a2 = v1[2]
            c0 = v2[0]; c1 = v2[1]; c2 = v2[2]
            v1[0] = a0 - dx * b2m
            v1[1] = a1 - dy * b2m
            v1[2] = a2 - dz * b2m
            v2[0] = c0 + dx * b1m
            v2[1] = c1 + dy * b1m
            v2[2] = c2 + dz * b1m
        for (r, [vx, vy, vz], m) in bodies:
            r[0] += dt * vx
            r[1] += dt * vy
            r[2] += dt * vz


# Group only consecutive first-body references; preserve the original order.
def _group_consecutive_pairs(pairs):
    groups = []
    for first, second in pairs:
        if groups and first is groups[-1][0]:
            groups[-1][1].append(second)
        else:
            groups.append((first, [second]))
    return groups


def advance_grouped(dt, n, bodies=None, pairs=None):
    """Reuse local state while retaining upstream's exact pow arithmetic."""
    if bodies is None or pairs is None:
        raise ValueError("pass the upstream module's bodies and pairs")
    groups = _group_consecutive_pairs(pairs)
    for _ in range(n):
        for (([x1, y1, z1], v1, m1), others) in groups:
            vx1, vy1, vz1 = v1
            for ([x2, y2, z2], v2, m2) in others:
                dx = x1 - x2
                dy = y1 - y2
                dz = z1 - z2
                mag = dt * ((dx * dx + dy * dy + dz * dz) ** (-1.5))
                b1m = m1 * mag
                b2m = m2 * mag
                # Same arithmetic and ordering as upstream's v1[0:3] updates.
                vx1 -= dx * b2m
                vy1 -= dy * b2m
                vz1 -= dz * b2m
                # Second-body stores remain immediate and in original order.
                v2[0] += dx * b1m
                v2[1] += dy * b1m
                v2[2] += dz * b1m
            v1[0] = vx1
            v1[1] = vy1
            v1[2] = vz1
        for (r, [vx, vy, vz], m) in bodies:
            r[0] += dt * vx
            r[1] += dt * vy
            r[2] += dt * vz


KERNELS = {
    "upstream": None,               # None => use upstream's own advance()
    "grouped":  advance_grouped,
    "sqrt":     advance_sqrt,
    "hoist":    advance_hoist,
    "full":     advance_full,
}


def _run(loops, iterations, kernel):
    """
    Run upstream's own bench_nbody with `kernel` substituted for advance().

    base.benchmark() binds the kernel to the timed module's SYSTEM/PAIRS, so no
    pre-loading happens here. An earlier version pre-loaded a separate module to
    capture that state, which meant the kernel mutated one module while upstream
    timed another -- all three kernels then "diverged" identically, which is the
    signature of a plumbing bug rather than an arithmetic one.
    """
    return base.benchmark(loops, iterations, advance=kernel)


def calibrate(iterations, kernel):
    loops = 1
    while True:
        el, _, _ = _run(loops, iterations, kernel)
        if el >= TARGET_SEC or loops >= 4096:
            return max(1, loops)
        loops *= 2


def _checked_snapshot(up, energy, name):
    state = base.snapshot(up)
    if len(state) != 30:
        raise AssertionError(f"{name}: expected 30 state components, got {len(state)}")
    if not isfinite(energy) or not all(isfinite(value) for value in state):
        raise AssertionError(f"{name}: non-finite energy or state")
    return state


def _float_bits(values):
    return struct.pack(f"!{len(values)}d", *values)


def verify(loops, iterations):
    """Check the actual accumulated batch; explicit failures survive python -O."""
    _, e_ref, up_ref = _run(loops, iterations, None)
    s_ref = _checked_snapshot(up_ref, e_ref, "upstream")
    print(f"reference (upstream advance), iterations={iterations} loops={loops}")
    print(f"  energy = {e_ref!r}")

    failures = []
    for name, fn in KERNELS.items():
        if fn is None:
            continue
        _, energy, up = _run(loops, iterations, fn)
        state = _checked_snapshot(up, energy, name)
        if name == "grouped":
            ok_energy = _float_bits([energy]) == _float_bits([e_ref])
            ok_state = _float_bits(state) == _float_bits(s_ref)
            ok = ok_energy and ok_state
            print(f"  {name:<9} energy bit-identical={ok_energy} "
                  f"| all 30 state components bit-identical={ok_state}")
        else:
            rel_energy = abs(energy - e_ref) / max(abs(e_ref), 1e-300)
            max_abs = max(abs(x - y) for x, y in zip(state, s_ref))
            denom = max(max(abs(x) for x in s_ref), 1e-300)
            norm_rel = max_abs / denom
            ok = rel_energy < 1e-9 and norm_rel < 1e-9
            print(f"  {name:<9} energy rel_diff={rel_energy:.3e} "
                  f"| state max_abs={max_abs:.3e} norm_rel={norm_rel:.3e} "
                  f"{'OK' if ok else 'FAIL'}")
        if not ok:
            failures.append(name)
    if failures:
        raise AssertionError("verification failed for: " + ", ".join(failures))
    print("verify: OK  grouped is bit-identical; legacy kernels agree "
          "within 1e-9 relative energy / norm-relative state")


def main():
    p = argparse.ArgumentParser(
        description="OPTIMIZED upstream pyperformance nbody")
    p.add_argument("--mode", choices=("raw", "calibrate", "verify", "ablate"),
                   default="raw", help="verify checks all kernels, including the selected kernel")
    p.add_argument("--loops", type=int, default=0,
                   help="0 => auto-calibrate for timing; 1 loop for verification")
    p.add_argument("--iterations", type=int, default=0,
                   help="0 => upstream default (20000)")
    p.add_argument("--kernel", choices=tuple(KERNELS), default="grouped")
    p.add_argument("--no-gc", action="store_true")
    a = p.parse_args()
    if a.no_gc:
        gc.disable()

    probe = base.load_upstream()
    iters = a.iterations or probe.DEFAULT_ITERATIONS
    kernel = KERNELS[a.kernel]

    if a.mode == "calibrate":
        print(calibrate(iters, kernel)); return 0

    if a.mode == "verify":
        verify(a.loops or 1, iters)
        return 0

    if a.mode == "ablate":
        # Attribute the speedup to individual edits. Median of several runs each,
        # interleaved to blunt any monotonic host drift.
        import statistics
        loops = a.loops or calibrate(iters, KERNELS["upstream"])
        reps = 5
        samples = dict((k, []) for k in KERNELS)
        for _ in range(reps):
            for name, fn in KERNELS.items():
                el, _, _ = _run(loops, iters, fn)
                samples[name].append(el)
        ref = statistics.median(samples["upstream"])
        print(f"ABLATION  loops={loops} iterations={iters} reps={reps}")
        print(f"{'kernel':<10}{'median s':>12}{'speedup':>10}{'time red.':>11}")
        print("-" * 43)
        for name in KERNELS:
            m = statistics.median(samples[name])
            print(f"{name:<10}{m:>12.6f}{ref / m:>9.4f}x"
                  f"{(1 - m / ref) * 100:>10.2f}%")
        print()
        print("Interpretation: any kernel whose speedup is ~1.00x contributes")
        print("nothing on the real upstream layout and must not be claimed.")
        return 0

    loops = a.loops or calibrate(iters, kernel)

    elapsed, energy, up = _run(loops, iters, kernel)
    total_steps = loops * iters

    print(f"OPTIMIZED upstream nbody — kernel={a.kernel}")
    print(f"bodies={len(up.SYSTEM)} pairs={len(up.PAIRS)} "
          f"iterations={iters} loops={loops}")
    print(f"elapsed={elapsed:.6f} s  {elapsed / loops * 1e3:.3f} ms/loop")
    print(f"energy={energy!r}")
    print(f"step_rate={total_steps / elapsed / 1e3:.2f} ksteps/s")
    print(f"RESULT total_sec={elapsed:.6f} loops={loops} "
          f"ms_per_loop={elapsed / loops * 1e3:.4f} energy={energy!r} "
          f"iterations={iters} kernel={a.kernel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
