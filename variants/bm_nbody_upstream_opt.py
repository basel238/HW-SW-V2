#!/usr/bin/env python3
"""
Isolated optimization candidates for the authentic pyperformance nbody kernel.
The reference in upstream/ is unchanged. The shared wrapper calls upstream's
own timed benchmark and substitutes only advance(), bound to that run's state.

DEFAULT: FLAT STATE, ORIGINAL POWER ARITHMETIC
---------------------------------------------
`flat_pow` keeps all 30 position/velocity components in scalar locals across
advance(), expands the ten canonical pair interactions and five body drifts,
and writes state back once before returning. No component list indexing or
pair/body traversal remains inside the timestep loop. Pair order, original
power expression, each velocity update, and drift after all pairs are retained.

`flat_sqrt` combines the same layout with the legacy inverse-power rewrite,
using dt / (d2 * sqrt(d2)). Its floating-point rounding can differ. Both flat
kernels read actual passed state and masses; no trajectories are precomputed.
They specialize five bodies with canonical pairs and distinct ordinary float
lists. Entry checks, initial loads and final stores stay INSIDE the timer.
Deferred writeback does not preserve partial-state visibility on exceptions or
for observers during advance(); aliased/custom containers are not supported.

These changes reduce repeated container operations and loop control. Python
locals still hold boxed floats; unchanged arithmetic still creates float
results. Source/bytecode counts are not time fractions or speedup predictions.
The 20,000-step workload is unchanged. Measure runtime on the target VM.

SEPARATE CANDIDATES
------------------
    upstream   original upstream advance(), unmodified control
    grouped    consecutive-pair reuse, original power arithmetic
    flat_pow   full-call local state and unrolled pairs/drift (default)
    flat_sqrt  flat_pow layout plus inverse-power rewrite
    sqrt       legacy inverse-power rewrite with locally bound sqrt
    hoist      legacy per-pair velocity loads/stores; no cross-pair reuse
    full       legacy sqrt + per-pair hoist combination
Grouped preserves its original implementation as an intermediate comparison.

CORRECTNESS
-----------
Verify mode checks all candidates at the requested iterations AND loops
(default one loop). Grouped and flat_pow require finite, bit-identical energy
and all 30 position/velocity components. Other candidates retain the existing
1e-9 relative-energy and norm-relative-state tolerance. The state tolerance is
max absolute error divided by the maximum absolute reference component; it is
not a per-component relative bound. Flat_sqrt must pass the full batch too.
"""

import argparse
import gc
import hashlib
import json
import os
from pathlib import Path
import platform
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


# Fixed-five workload specialization. Validate once per call, never per step.
# The explicit pair order mirrors upstream.PAIRS; retaining it preserves each
# velocity component's floating-point accumulation order.
def _check_flat_inputs(dt, n, bodies, pairs):
    if type(dt) is not float or type(n) is not int or n < 0:
        raise ValueError("requires float dt and nonnegative integer n")
    if bodies is None or len(bodies) != 5 or pairs is None or len(pairs) != 10:
        raise ValueError("requires five bodies and ten pairs")
    component_lists = []
    for body in bodies:
        if len(body) != 3 or type(body[2]) is not float:
            raise ValueError("requires float masses")
        for components in body[:2]:
            if type(components) is not list or len(components) != 3:
                raise ValueError("requires ordinary three-component lists")
            if any(type(value) is not float for value in components):
                raise ValueError("requires float components")
            component_lists.append(components)
    if len({id(items) for items in component_lists}) != 10:
        raise ValueError("requires distinct component lists")
    pair_index = 0
    for i in range(4):
        for j in range(i + 1, 5):
            a, b = pairs[pair_index]
            if a is not bodies[i] or b is not bodies[j]:
                raise ValueError("requires canonical pair identities/order")
            pair_index += 1


def advance_flat_pow(dt, n, bodies=None, pairs=None):
    """Keep the full state local, preserving upstream floating-point order."""
    _check_flat_inputs(dt, n, bodies, pairs)
    r0, v0, m0 = bodies[0]
    vx0, vy0, vz0 = v0
    x0, y0, z0 = r0
    r1, v1, m1 = bodies[1]
    vx1, vy1, vz1 = v1
    x1, y1, z1 = r1
    r2, v2, m2 = bodies[2]
    vx2, vy2, vz2 = v2
    x2, y2, z2 = r2
    r3, v3, m3 = bodies[3]
    vx3, vy3, vz3 = v3
    x3, y3, z3 = r3
    r4, v4, m4 = bodies[4]
    vx4, vy4, vz4 = v4
    x4, y4, z4 = r4
    for _ in range(n):
        # Pair (0, 1), in upstream order.
        dx = x0 - x1
        dy = y0 - y1
        dz = z0 - z1
        mag = dt * ((dx * dx + dy * dy + dz * dz) ** (-1.5))
        b1m = m0 * mag
        b2m = m1 * mag
        vx0 -= dx * b2m
        vy0 -= dy * b2m
        vz0 -= dz * b2m
        vx1 += dx * b1m
        vy1 += dy * b1m
        vz1 += dz * b1m
        # Pair (0, 2), in upstream order.
        dx = x0 - x2
        dy = y0 - y2
        dz = z0 - z2
        mag = dt * ((dx * dx + dy * dy + dz * dz) ** (-1.5))
        b1m = m0 * mag
        b2m = m2 * mag
        vx0 -= dx * b2m
        vy0 -= dy * b2m
        vz0 -= dz * b2m
        vx2 += dx * b1m
        vy2 += dy * b1m
        vz2 += dz * b1m
        # Pair (0, 3), in upstream order.
        dx = x0 - x3
        dy = y0 - y3
        dz = z0 - z3
        mag = dt * ((dx * dx + dy * dy + dz * dz) ** (-1.5))
        b1m = m0 * mag
        b2m = m3 * mag
        vx0 -= dx * b2m
        vy0 -= dy * b2m
        vz0 -= dz * b2m
        vx3 += dx * b1m
        vy3 += dy * b1m
        vz3 += dz * b1m
        # Pair (0, 4), in upstream order.
        dx = x0 - x4
        dy = y0 - y4
        dz = z0 - z4
        mag = dt * ((dx * dx + dy * dy + dz * dz) ** (-1.5))
        b1m = m0 * mag
        b2m = m4 * mag
        vx0 -= dx * b2m
        vy0 -= dy * b2m
        vz0 -= dz * b2m
        vx4 += dx * b1m
        vy4 += dy * b1m
        vz4 += dz * b1m
        # Pair (1, 2), in upstream order.
        dx = x1 - x2
        dy = y1 - y2
        dz = z1 - z2
        mag = dt * ((dx * dx + dy * dy + dz * dz) ** (-1.5))
        b1m = m1 * mag
        b2m = m2 * mag
        vx1 -= dx * b2m
        vy1 -= dy * b2m
        vz1 -= dz * b2m
        vx2 += dx * b1m
        vy2 += dy * b1m
        vz2 += dz * b1m
        # Pair (1, 3), in upstream order.
        dx = x1 - x3
        dy = y1 - y3
        dz = z1 - z3
        mag = dt * ((dx * dx + dy * dy + dz * dz) ** (-1.5))
        b1m = m1 * mag
        b2m = m3 * mag
        vx1 -= dx * b2m
        vy1 -= dy * b2m
        vz1 -= dz * b2m
        vx3 += dx * b1m
        vy3 += dy * b1m
        vz3 += dz * b1m
        # Pair (1, 4), in upstream order.
        dx = x1 - x4
        dy = y1 - y4
        dz = z1 - z4
        mag = dt * ((dx * dx + dy * dy + dz * dz) ** (-1.5))
        b1m = m1 * mag
        b2m = m4 * mag
        vx1 -= dx * b2m
        vy1 -= dy * b2m
        vz1 -= dz * b2m
        vx4 += dx * b1m
        vy4 += dy * b1m
        vz4 += dz * b1m
        # Pair (2, 3), in upstream order.
        dx = x2 - x3
        dy = y2 - y3
        dz = z2 - z3
        mag = dt * ((dx * dx + dy * dy + dz * dz) ** (-1.5))
        b1m = m2 * mag
        b2m = m3 * mag
        vx2 -= dx * b2m
        vy2 -= dy * b2m
        vz2 -= dz * b2m
        vx3 += dx * b1m
        vy3 += dy * b1m
        vz3 += dz * b1m
        # Pair (2, 4), in upstream order.
        dx = x2 - x4
        dy = y2 - y4
        dz = z2 - z4
        mag = dt * ((dx * dx + dy * dy + dz * dz) ** (-1.5))
        b1m = m2 * mag
        b2m = m4 * mag
        vx2 -= dx * b2m
        vy2 -= dy * b2m
        vz2 -= dz * b2m
        vx4 += dx * b1m
        vy4 += dy * b1m
        vz4 += dz * b1m
        # Pair (3, 4), in upstream order.
        dx = x3 - x4
        dy = y3 - y4
        dz = z3 - z4
        mag = dt * ((dx * dx + dy * dy + dz * dz) ** (-1.5))
        b1m = m3 * mag
        b2m = m4 * mag
        vx3 -= dx * b2m
        vy3 -= dy * b2m
        vz3 -= dz * b2m
        vx4 += dx * b1m
        vy4 += dy * b1m
        vz4 += dz * b1m
        # Drift only after all ten force interactions.
        x0 += dt * vx0
        y0 += dt * vy0
        z0 += dt * vz0
        x1 += dt * vx1
        y1 += dt * vy1
        z1 += dt * vz1
        x2 += dt * vx2
        y2 += dt * vy2
        z2 += dt * vz2
        x3 += dt * vx3
        y3 += dt * vy3
        z3 += dt * vz3
        x4 += dt * vx4
        y4 += dt * vy4
        z4 += dt * vz4
    # Publish state before the caller's energy calculation.
    r0[0] = x0
    r0[1] = y0
    r0[2] = z0
    v0[0] = vx0
    v0[1] = vy0
    v0[2] = vz0
    r1[0] = x1
    r1[1] = y1
    r1[2] = z1
    v1[0] = vx1
    v1[1] = vy1
    v1[2] = vz1
    r2[0] = x2
    r2[1] = y2
    r2[2] = z2
    v2[0] = vx2
    v2[1] = vy2
    v2[2] = vz2
    r3[0] = x3
    r3[1] = y3
    r3[2] = z3
    v3[0] = vx3
    v3[1] = vy3
    v3[2] = vz3
    r4[0] = x4
    r4[1] = y4
    r4[2] = z4
    v4[0] = vx4
    v4[1] = vy4
    v4[2] = vz4


def advance_flat_sqrt(dt, n, bodies=None, pairs=None, _sqrt=sqrt):
    """Combine full-call local state with the approximate inverse-power rewrite."""
    _check_flat_inputs(dt, n, bodies, pairs)
    r0, v0, m0 = bodies[0]
    vx0, vy0, vz0 = v0
    x0, y0, z0 = r0
    r1, v1, m1 = bodies[1]
    vx1, vy1, vz1 = v1
    x1, y1, z1 = r1
    r2, v2, m2 = bodies[2]
    vx2, vy2, vz2 = v2
    x2, y2, z2 = r2
    r3, v3, m3 = bodies[3]
    vx3, vy3, vz3 = v3
    x3, y3, z3 = r3
    r4, v4, m4 = bodies[4]
    vx4, vy4, vz4 = v4
    x4, y4, z4 = r4
    for _ in range(n):
        # Pair (0, 1), in upstream order.
        dx = x0 - x1
        dy = y0 - y1
        dz = z0 - z1
        d2 = dx * dx + dy * dy + dz * dz
        mag = dt / (d2 * _sqrt(d2))
        b1m = m0 * mag
        b2m = m1 * mag
        vx0 -= dx * b2m
        vy0 -= dy * b2m
        vz0 -= dz * b2m
        vx1 += dx * b1m
        vy1 += dy * b1m
        vz1 += dz * b1m
        # Pair (0, 2), in upstream order.
        dx = x0 - x2
        dy = y0 - y2
        dz = z0 - z2
        d2 = dx * dx + dy * dy + dz * dz
        mag = dt / (d2 * _sqrt(d2))
        b1m = m0 * mag
        b2m = m2 * mag
        vx0 -= dx * b2m
        vy0 -= dy * b2m
        vz0 -= dz * b2m
        vx2 += dx * b1m
        vy2 += dy * b1m
        vz2 += dz * b1m
        # Pair (0, 3), in upstream order.
        dx = x0 - x3
        dy = y0 - y3
        dz = z0 - z3
        d2 = dx * dx + dy * dy + dz * dz
        mag = dt / (d2 * _sqrt(d2))
        b1m = m0 * mag
        b2m = m3 * mag
        vx0 -= dx * b2m
        vy0 -= dy * b2m
        vz0 -= dz * b2m
        vx3 += dx * b1m
        vy3 += dy * b1m
        vz3 += dz * b1m
        # Pair (0, 4), in upstream order.
        dx = x0 - x4
        dy = y0 - y4
        dz = z0 - z4
        d2 = dx * dx + dy * dy + dz * dz
        mag = dt / (d2 * _sqrt(d2))
        b1m = m0 * mag
        b2m = m4 * mag
        vx0 -= dx * b2m
        vy0 -= dy * b2m
        vz0 -= dz * b2m
        vx4 += dx * b1m
        vy4 += dy * b1m
        vz4 += dz * b1m
        # Pair (1, 2), in upstream order.
        dx = x1 - x2
        dy = y1 - y2
        dz = z1 - z2
        d2 = dx * dx + dy * dy + dz * dz
        mag = dt / (d2 * _sqrt(d2))
        b1m = m1 * mag
        b2m = m2 * mag
        vx1 -= dx * b2m
        vy1 -= dy * b2m
        vz1 -= dz * b2m
        vx2 += dx * b1m
        vy2 += dy * b1m
        vz2 += dz * b1m
        # Pair (1, 3), in upstream order.
        dx = x1 - x3
        dy = y1 - y3
        dz = z1 - z3
        d2 = dx * dx + dy * dy + dz * dz
        mag = dt / (d2 * _sqrt(d2))
        b1m = m1 * mag
        b2m = m3 * mag
        vx1 -= dx * b2m
        vy1 -= dy * b2m
        vz1 -= dz * b2m
        vx3 += dx * b1m
        vy3 += dy * b1m
        vz3 += dz * b1m
        # Pair (1, 4), in upstream order.
        dx = x1 - x4
        dy = y1 - y4
        dz = z1 - z4
        d2 = dx * dx + dy * dy + dz * dz
        mag = dt / (d2 * _sqrt(d2))
        b1m = m1 * mag
        b2m = m4 * mag
        vx1 -= dx * b2m
        vy1 -= dy * b2m
        vz1 -= dz * b2m
        vx4 += dx * b1m
        vy4 += dy * b1m
        vz4 += dz * b1m
        # Pair (2, 3), in upstream order.
        dx = x2 - x3
        dy = y2 - y3
        dz = z2 - z3
        d2 = dx * dx + dy * dy + dz * dz
        mag = dt / (d2 * _sqrt(d2))
        b1m = m2 * mag
        b2m = m3 * mag
        vx2 -= dx * b2m
        vy2 -= dy * b2m
        vz2 -= dz * b2m
        vx3 += dx * b1m
        vy3 += dy * b1m
        vz3 += dz * b1m
        # Pair (2, 4), in upstream order.
        dx = x2 - x4
        dy = y2 - y4
        dz = z2 - z4
        d2 = dx * dx + dy * dy + dz * dz
        mag = dt / (d2 * _sqrt(d2))
        b1m = m2 * mag
        b2m = m4 * mag
        vx2 -= dx * b2m
        vy2 -= dy * b2m
        vz2 -= dz * b2m
        vx4 += dx * b1m
        vy4 += dy * b1m
        vz4 += dz * b1m
        # Pair (3, 4), in upstream order.
        dx = x3 - x4
        dy = y3 - y4
        dz = z3 - z4
        d2 = dx * dx + dy * dy + dz * dz
        mag = dt / (d2 * _sqrt(d2))
        b1m = m3 * mag
        b2m = m4 * mag
        vx3 -= dx * b2m
        vy3 -= dy * b2m
        vz3 -= dz * b2m
        vx4 += dx * b1m
        vy4 += dy * b1m
        vz4 += dz * b1m
        # Drift only after all ten force interactions.
        x0 += dt * vx0
        y0 += dt * vy0
        z0 += dt * vz0
        x1 += dt * vx1
        y1 += dt * vy1
        z1 += dt * vz1
        x2 += dt * vx2
        y2 += dt * vy2
        z2 += dt * vz2
        x3 += dt * vx3
        y3 += dt * vy3
        z3 += dt * vz3
        x4 += dt * vx4
        y4 += dt * vy4
        z4 += dt * vz4
    # Publish state before the caller's energy calculation.
    r0[0] = x0
    r0[1] = y0
    r0[2] = z0
    v0[0] = vx0
    v0[1] = vy0
    v0[2] = vz0
    r1[0] = x1
    r1[1] = y1
    r1[2] = z1
    v1[0] = vx1
    v1[1] = vy1
    v1[2] = vz1
    r2[0] = x2
    r2[1] = y2
    r2[2] = z2
    v2[0] = vx2
    v2[1] = vy2
    v2[2] = vz2
    r3[0] = x3
    r3[1] = y3
    r3[2] = z3
    v3[0] = vx3
    v3[1] = vy3
    v3[2] = vz3
    r4[0] = x4
    r4[1] = y4
    r4[2] = z4
    v4[0] = vx4
    v4[1] = vy4
    v4[2] = vz4


KERNELS = {
    "upstream": None,               # None => use upstream's own advance()
    "grouped":  advance_grouped,
    "flat_pow": advance_flat_pow,
    "flat_sqrt": advance_flat_sqrt,
    "sqrt":     advance_sqrt,
    "hoist":    advance_hoist,
    "full":     advance_full,
}


EXACT_KERNELS = frozenset({"grouped", "flat_pow"})


def _variant_sha256():
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


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
        if name in EXACT_KERNELS:
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
    print("verify: OK  grouped/flat_pow are bit-identical; other kernels agree "
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
    p.add_argument("--kernel", choices=tuple(KERNELS), default="flat_pow")
    p.add_argument("--reps", type=int, default=15,
                   help="positive repetition count for exploratory ablation (default: 15)")
    p.add_argument("--ablation-json", type=Path,
                   help="save ablation samples, run order and source/environment metadata")
    p.add_argument("--no-gc", action="store_true")
    a = p.parse_args()
    if a.reps < 1:
        p.error("--reps must be positive")
    if a.ablation_json is not None and a.mode != "ablate":
        p.error("--ablation-json requires --mode ablate")
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
        # Exploratory in-process comparison. Rotate starting position so a
        # candidate does not always follow the same position in each batch.
        # This is not a substitute for target-VM independent-process timing.
        import statistics
        loops = a.loops or calibrate(iters, KERNELS["upstream"])
        names = list(KERNELS)
        samples = {name: [] for name in names}
        records = []
        for rep in range(a.reps):
            offset = rep % len(names)
            order = names[offset:] + names[:offset]
            for position, name in enumerate(order):
                el, _, _ = _run(loops, iters, KERNELS[name])
                samples[name].append(el)
                records.append({"rep": rep + 1, "position": position + 1,
                                "kernel": name, "total_sec": el})
        ref = statistics.median(samples["upstream"])
        summary = {}
        print(f"ABLATION  loops={loops} iterations={iters} reps={a.reps}")
        print(f"variant_sha256={_variant_sha256()}")
        print(f"{'kernel':<12}{'median s':>12}{'stdev s':>12}"
              f"{'speedup':>10}{'time red.':>11}")
        print("-" * 57)
        for name in names:
            values = samples[name]
            median = statistics.median(values)
            sd = statistics.stdev(values) if len(values) > 1 else 0.0
            summary[name] = {"median_sec": median, "mean_sec": statistics.mean(values),
                             "stdev_sec": sd, "speedup": ref / median,
                             "time_reduction_pct": (1 - median / ref) * 100}
            print(f"{name:<12}{median:>12.6f}{sd:>12.6f}{ref / median:>9.4f}x"
                  f"{(1 - median / ref) * 100:>10.2f}%")
        for name in names:
            print(f"ABLATION_SAMPLES kernel={name} total_sec={json.dumps(samples[name])}")
        if a.ablation_json is not None:
            payload = {"kind": "exploratory_in_process_ablation",
                       "python": sys.version, "platform": platform.platform(),
                       "upstream_sha256": base.upstream_sha256(),
                       "variant_sha256": _variant_sha256(),
                       "loops": loops, "iterations": iters, "reps": a.reps,
                       "gc_enabled": gc.isenabled(), "records": records,
                       "samples_sec": samples, "summary": summary}
            a.ablation_json.write_text(json.dumps(payload, indent=2) + "\n")
            print(f"Saved ablation evidence: {a.ablation_json}")
        print("Exploratory results: confirm promising candidates with clean")
        print("independent-process timing on the target VM; stdev is not a confidence interval.")
        return 0

    loops = a.loops or calibrate(iters, kernel)

    elapsed, energy, up = _run(loops, iters, kernel)
    total_steps = loops * iters

    print(f"OPTIMIZED upstream nbody — kernel={a.kernel}")
    print(f"variant_sha256={_variant_sha256()}")
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
