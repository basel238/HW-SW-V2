#!/usr/bin/env python3
"""Exact nbody diagnostic controls; production default remains flat_pow.

These isolate structural hypotheses. They are not claimed speedups. They use
actual passed state/masses and preserve upstream arithmetic/pair order. Fixed-
five controls have the same restricted successful-call contract as flat_pow.
"""
import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import platform
import statistics
import struct
import sys
import gc

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("nbody_controls_production", ROOT / "variants/bm_nbody_upstream_opt.py")
production = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(production)
_check_inputs = production._check_flat_inputs

def advance_unrolled_pairs(dt, n, bodies=None, pairs=None):
    _check_inputs(dt, n, bodies, pairs)
    pair01, pair02, pair03, pair04, pair12, pair13, pair14, pair23, pair24, pair34 = pairs
    for _ in range(n):
        # Pair (0, 1), in upstream order.
        (([x1, y1, z1], v1, m1), ([x2, y2, z2], v2, m2)) = pair01
        dx = x1 - x2
        dy = y1 - y2
        dz = z1 - z2
        mag = dt * ((dx * dx + dy * dy + dz * dz) ** (-1.5))
        b1m = m1 * mag
        b2m = m2 * mag
        v1[0] -= dx * b2m
        v1[1] -= dy * b2m
        v1[2] -= dz * b2m
        v2[0] += dx * b1m
        v2[1] += dy * b1m
        v2[2] += dz * b1m
        # Pair (0, 2), in upstream order.
        (([x1, y1, z1], v1, m1), ([x2, y2, z2], v2, m2)) = pair02
        dx = x1 - x2
        dy = y1 - y2
        dz = z1 - z2
        mag = dt * ((dx * dx + dy * dy + dz * dz) ** (-1.5))
        b1m = m1 * mag
        b2m = m2 * mag
        v1[0] -= dx * b2m
        v1[1] -= dy * b2m
        v1[2] -= dz * b2m
        v2[0] += dx * b1m
        v2[1] += dy * b1m
        v2[2] += dz * b1m
        # Pair (0, 3), in upstream order.
        (([x1, y1, z1], v1, m1), ([x2, y2, z2], v2, m2)) = pair03
        dx = x1 - x2
        dy = y1 - y2
        dz = z1 - z2
        mag = dt * ((dx * dx + dy * dy + dz * dz) ** (-1.5))
        b1m = m1 * mag
        b2m = m2 * mag
        v1[0] -= dx * b2m
        v1[1] -= dy * b2m
        v1[2] -= dz * b2m
        v2[0] += dx * b1m
        v2[1] += dy * b1m
        v2[2] += dz * b1m
        # Pair (0, 4), in upstream order.
        (([x1, y1, z1], v1, m1), ([x2, y2, z2], v2, m2)) = pair04
        dx = x1 - x2
        dy = y1 - y2
        dz = z1 - z2
        mag = dt * ((dx * dx + dy * dy + dz * dz) ** (-1.5))
        b1m = m1 * mag
        b2m = m2 * mag
        v1[0] -= dx * b2m
        v1[1] -= dy * b2m
        v1[2] -= dz * b2m
        v2[0] += dx * b1m
        v2[1] += dy * b1m
        v2[2] += dz * b1m
        # Pair (1, 2), in upstream order.
        (([x1, y1, z1], v1, m1), ([x2, y2, z2], v2, m2)) = pair12
        dx = x1 - x2
        dy = y1 - y2
        dz = z1 - z2
        mag = dt * ((dx * dx + dy * dy + dz * dz) ** (-1.5))
        b1m = m1 * mag
        b2m = m2 * mag
        v1[0] -= dx * b2m
        v1[1] -= dy * b2m
        v1[2] -= dz * b2m
        v2[0] += dx * b1m
        v2[1] += dy * b1m
        v2[2] += dz * b1m
        # Pair (1, 3), in upstream order.
        (([x1, y1, z1], v1, m1), ([x2, y2, z2], v2, m2)) = pair13
        dx = x1 - x2
        dy = y1 - y2
        dz = z1 - z2
        mag = dt * ((dx * dx + dy * dy + dz * dz) ** (-1.5))
        b1m = m1 * mag
        b2m = m2 * mag
        v1[0] -= dx * b2m
        v1[1] -= dy * b2m
        v1[2] -= dz * b2m
        v2[0] += dx * b1m
        v2[1] += dy * b1m
        v2[2] += dz * b1m
        # Pair (1, 4), in upstream order.
        (([x1, y1, z1], v1, m1), ([x2, y2, z2], v2, m2)) = pair14
        dx = x1 - x2
        dy = y1 - y2
        dz = z1 - z2
        mag = dt * ((dx * dx + dy * dy + dz * dz) ** (-1.5))
        b1m = m1 * mag
        b2m = m2 * mag
        v1[0] -= dx * b2m
        v1[1] -= dy * b2m
        v1[2] -= dz * b2m
        v2[0] += dx * b1m
        v2[1] += dy * b1m
        v2[2] += dz * b1m
        # Pair (2, 3), in upstream order.
        (([x1, y1, z1], v1, m1), ([x2, y2, z2], v2, m2)) = pair23
        dx = x1 - x2
        dy = y1 - y2
        dz = z1 - z2
        mag = dt * ((dx * dx + dy * dy + dz * dz) ** (-1.5))
        b1m = m1 * mag
        b2m = m2 * mag
        v1[0] -= dx * b2m
        v1[1] -= dy * b2m
        v1[2] -= dz * b2m
        v2[0] += dx * b1m
        v2[1] += dy * b1m
        v2[2] += dz * b1m
        # Pair (2, 4), in upstream order.
        (([x1, y1, z1], v1, m1), ([x2, y2, z2], v2, m2)) = pair24
        dx = x1 - x2
        dy = y1 - y2
        dz = z1 - z2
        mag = dt * ((dx * dx + dy * dy + dz * dz) ** (-1.5))
        b1m = m1 * mag
        b2m = m2 * mag
        v1[0] -= dx * b2m
        v1[1] -= dy * b2m
        v1[2] -= dz * b2m
        v2[0] += dx * b1m
        v2[1] += dy * b1m
        v2[2] += dz * b1m
        # Pair (3, 4), in upstream order.
        (([x1, y1, z1], v1, m1), ([x2, y2, z2], v2, m2)) = pair34
        dx = x1 - x2
        dy = y1 - y2
        dz = z1 - z2
        mag = dt * ((dx * dx + dy * dy + dz * dz) ** (-1.5))
        b1m = m1 * mag
        b2m = m2 * mag
        v1[0] -= dx * b2m
        v1[1] -= dy * b2m
        v1[2] -= dz * b2m
        v2[0] += dx * b1m
        v2[1] += dy * b1m
        v2[2] += dz * b1m
        # Drift only after all ten force interactions.
        for (r, [vx, vy, vz], m) in bodies:
            r[0] += dt * vx
            r[1] += dt * vy
            r[2] += dt * vz


def advance_unrolled_lists(dt, n, bodies=None, pairs=None):
    _check_inputs(dt, n, bodies, pairs)
    r0, v0, m0 = bodies[0]
    r1, v1, m1 = bodies[1]
    r2, v2, m2 = bodies[2]
    r3, v3, m3 = bodies[3]
    r4, v4, m4 = bodies[4]
    for _ in range(n):
        # Pair (0, 1), in upstream order.
        x0, y0, z0 = r0
        x1, y1, z1 = r1
        dx = x0 - x1
        dy = y0 - y1
        dz = z0 - z1
        mag = dt * ((dx * dx + dy * dy + dz * dz) ** (-1.5))
        b1m = m0 * mag
        b2m = m1 * mag
        v0[0] -= dx * b2m
        v0[1] -= dy * b2m
        v0[2] -= dz * b2m
        v1[0] += dx * b1m
        v1[1] += dy * b1m
        v1[2] += dz * b1m
        # Pair (0, 2), in upstream order.
        x0, y0, z0 = r0
        x2, y2, z2 = r2
        dx = x0 - x2
        dy = y0 - y2
        dz = z0 - z2
        mag = dt * ((dx * dx + dy * dy + dz * dz) ** (-1.5))
        b1m = m0 * mag
        b2m = m2 * mag
        v0[0] -= dx * b2m
        v0[1] -= dy * b2m
        v0[2] -= dz * b2m
        v2[0] += dx * b1m
        v2[1] += dy * b1m
        v2[2] += dz * b1m
        # Pair (0, 3), in upstream order.
        x0, y0, z0 = r0
        x3, y3, z3 = r3
        dx = x0 - x3
        dy = y0 - y3
        dz = z0 - z3
        mag = dt * ((dx * dx + dy * dy + dz * dz) ** (-1.5))
        b1m = m0 * mag
        b2m = m3 * mag
        v0[0] -= dx * b2m
        v0[1] -= dy * b2m
        v0[2] -= dz * b2m
        v3[0] += dx * b1m
        v3[1] += dy * b1m
        v3[2] += dz * b1m
        # Pair (0, 4), in upstream order.
        x0, y0, z0 = r0
        x4, y4, z4 = r4
        dx = x0 - x4
        dy = y0 - y4
        dz = z0 - z4
        mag = dt * ((dx * dx + dy * dy + dz * dz) ** (-1.5))
        b1m = m0 * mag
        b2m = m4 * mag
        v0[0] -= dx * b2m
        v0[1] -= dy * b2m
        v0[2] -= dz * b2m
        v4[0] += dx * b1m
        v4[1] += dy * b1m
        v4[2] += dz * b1m
        # Pair (1, 2), in upstream order.
        x1, y1, z1 = r1
        x2, y2, z2 = r2
        dx = x1 - x2
        dy = y1 - y2
        dz = z1 - z2
        mag = dt * ((dx * dx + dy * dy + dz * dz) ** (-1.5))
        b1m = m1 * mag
        b2m = m2 * mag
        v1[0] -= dx * b2m
        v1[1] -= dy * b2m
        v1[2] -= dz * b2m
        v2[0] += dx * b1m
        v2[1] += dy * b1m
        v2[2] += dz * b1m
        # Pair (1, 3), in upstream order.
        x1, y1, z1 = r1
        x3, y3, z3 = r3
        dx = x1 - x3
        dy = y1 - y3
        dz = z1 - z3
        mag = dt * ((dx * dx + dy * dy + dz * dz) ** (-1.5))
        b1m = m1 * mag
        b2m = m3 * mag
        v1[0] -= dx * b2m
        v1[1] -= dy * b2m
        v1[2] -= dz * b2m
        v3[0] += dx * b1m
        v3[1] += dy * b1m
        v3[2] += dz * b1m
        # Pair (1, 4), in upstream order.
        x1, y1, z1 = r1
        x4, y4, z4 = r4
        dx = x1 - x4
        dy = y1 - y4
        dz = z1 - z4
        mag = dt * ((dx * dx + dy * dy + dz * dz) ** (-1.5))
        b1m = m1 * mag
        b2m = m4 * mag
        v1[0] -= dx * b2m
        v1[1] -= dy * b2m
        v1[2] -= dz * b2m
        v4[0] += dx * b1m
        v4[1] += dy * b1m
        v4[2] += dz * b1m
        # Pair (2, 3), in upstream order.
        x2, y2, z2 = r2
        x3, y3, z3 = r3
        dx = x2 - x3
        dy = y2 - y3
        dz = z2 - z3
        mag = dt * ((dx * dx + dy * dy + dz * dz) ** (-1.5))
        b1m = m2 * mag
        b2m = m3 * mag
        v2[0] -= dx * b2m
        v2[1] -= dy * b2m
        v2[2] -= dz * b2m
        v3[0] += dx * b1m
        v3[1] += dy * b1m
        v3[2] += dz * b1m
        # Pair (2, 4), in upstream order.
        x2, y2, z2 = r2
        x4, y4, z4 = r4
        dx = x2 - x4
        dy = y2 - y4
        dz = z2 - z4
        mag = dt * ((dx * dx + dy * dy + dz * dz) ** (-1.5))
        b1m = m2 * mag
        b2m = m4 * mag
        v2[0] -= dx * b2m
        v2[1] -= dy * b2m
        v2[2] -= dz * b2m
        v4[0] += dx * b1m
        v4[1] += dy * b1m
        v4[2] += dz * b1m
        # Pair (3, 4), in upstream order.
        x3, y3, z3 = r3
        x4, y4, z4 = r4
        dx = x3 - x4
        dy = y3 - y4
        dz = z3 - z4
        mag = dt * ((dx * dx + dy * dy + dz * dz) ** (-1.5))
        b1m = m3 * mag
        b2m = m4 * mag
        v3[0] -= dx * b2m
        v3[1] -= dy * b2m
        v3[2] -= dz * b2m
        v4[0] += dx * b1m
        v4[1] += dy * b1m
        v4[2] += dz * b1m
        # Drift only after all ten force interactions.
        vx0, vy0, vz0 = v0
        r0[0] += dt * vx0
        r0[1] += dt * vy0
        r0[2] += dt * vz0
        vx1, vy1, vz1 = v1
        r1[0] += dt * vx1
        r1[1] += dt * vy1
        r1[2] += dt * vz1
        vx2, vy2, vz2 = v2
        r2[0] += dt * vx2
        r2[1] += dt * vy2
        r2[2] += dt * vz2
        vx3, vy3, vz3 = v3
        r3[0] += dt * vx3
        r3[1] += dt * vy3
        r3[2] += dt * vz3
        vx4, vy4, vz4 = v4
        r4[0] += dt * vx4
        r4[1] += dt * vy4
        r4[2] += dt * vz4


def advance_velocity_locals(dt, n, bodies=None, pairs=None):
    _check_inputs(dt, n, bodies, pairs)
    r0, v0, m0 = bodies[0]
    vx0, vy0, vz0 = v0
    r1, v1, m1 = bodies[1]
    vx1, vy1, vz1 = v1
    r2, v2, m2 = bodies[2]
    vx2, vy2, vz2 = v2
    r3, v3, m3 = bodies[3]
    vx3, vy3, vz3 = v3
    r4, v4, m4 = bodies[4]
    vx4, vy4, vz4 = v4
    for _ in range(n):
        # Pair (0, 1), in upstream order.
        x0, y0, z0 = r0
        x1, y1, z1 = r1
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
        x0, y0, z0 = r0
        x2, y2, z2 = r2
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
        x0, y0, z0 = r0
        x3, y3, z3 = r3
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
        x0, y0, z0 = r0
        x4, y4, z4 = r4
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
        x1, y1, z1 = r1
        x2, y2, z2 = r2
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
        x1, y1, z1 = r1
        x3, y3, z3 = r3
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
        x1, y1, z1 = r1
        x4, y4, z4 = r4
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
        x2, y2, z2 = r2
        x3, y3, z3 = r3
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
        x2, y2, z2 = r2
        x4, y4, z4 = r4
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
        x3, y3, z3 = r3
        x4, y4, z4 = r4
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
        r0[0] += dt * vx0
        r0[1] += dt * vy0
        r0[2] += dt * vz0
        r1[0] += dt * vx1
        r1[1] += dt * vy1
        r1[2] += dt * vz1
        r2[0] += dt * vx2
        r2[1] += dt * vy2
        r2[2] += dt * vz2
        r3[0] += dt * vx3
        r3[1] += dt * vy3
        r3[2] += dt * vz3
        r4[0] += dt * vx4
        r4[1] += dt * vy4
        r4[2] += dt * vz4
    # Publish state before the caller's energy calculation.
    v0[0] = vx0
    v0[1] = vy0
    v0[2] = vz0
    v1[0] = vx1
    v1[1] = vy1
    v1[2] = vz1
    v2[0] = vx2
    v2[1] = vy2
    v2[2] = vz2
    v3[0] = vx3
    v3[1] = vy3
    v3[2] = vz3
    v4[0] = vx4
    v4[1] = vy4
    v4[2] = vz4


def flat_unpacked(dt, n, bodies=None, pairs=None):
    """Original pair traversal, bulk velocity unpacking, immediate list stores."""
    for _ in range(n):
        for (([x1, y1, z1], v1, m1), ([x2, y2, z2], v2, m2)) in pairs:
            dx = x1 - x2
            dy = y1 - y2
            dz = z1 - z2
            mag = dt * ((dx * dx + dy * dy + dz * dz) ** (-1.5))
            b1m = m1 * mag
            b2m = m2 * mag
            vx1, vy1, vz1 = v1
            vx2, vy2, vz2 = v2
            v1[0] = vx1 - dx * b2m
            v1[1] = vy1 - dy * b2m
            v1[2] = vz1 - dz * b2m
            v2[0] = vx2 + dx * b1m
            v2[1] = vy2 + dy * b1m
            v2[2] = vz2 + dz * b1m
        for (r, [vx, vy, vz], m) in bodies:
            r[0] += dt * vx
            r[1] += dt * vy
            r[2] += dt * vz


def grouped_indexed(dt, n, bodies=None, pairs=None):
    """Group original pair references but retain original per-pair indexed work.

    This is a traversal control, not bytecode-identical to the existing grouped
    variant: groups hold complete pair references, so original pair unpacking
    and original indexed arithmetic can remain verbatim in the inner loop.
    """
    groups = []
    for pair in pairs:
        first, second = pair
        if groups and first is groups[-1][0]:
            groups[-1][1].append(pair)
        else:
            groups.append((first, [pair]))
    for _ in range(n):
        for first, group in groups:
            for (([x1, y1, z1], v1, m1), ([x2, y2, z2], v2, m2)) in group:
                dx = x1 - x2
                dy = y1 - y2
                dz = z1 - z2
                mag = dt * ((dx * dx + dy * dy + dz * dz) ** (-1.5))
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

KERNELS = {
    "upstream": None,
    "grouped": production.advance_grouped,
    "unpacked": flat_unpacked,
    "grouped_indexed": grouped_indexed,
    "unrolled_pairs": advance_unrolled_pairs,
    "unrolled_lists": advance_unrolled_lists,
    "velocity_locals": advance_velocity_locals,
    "flat_pow": production.advance_flat_pow,
}


def fingerprint(energy, module):
    values = production.base.snapshot(module) + [energy]
    if len(values) != 31 or not all(math.isfinite(v) for v in values):
        raise ValueError("non-finite or incomplete state")
    return struct.pack("!31d", *values)


def verify(names, loops, iterations):
    _, energy, module = production._run(loops, iterations, None)
    expected = fingerprint(energy, module)
    for name in names:
        _, energy, module = production._run(loops, iterations, KERNELS[name])
        if fingerprint(energy, module) != expected:
            raise RuntimeError("bit-identical correctness failed for " + name)
        print(name + ": energy and all 30 state components BIT-IDENTICAL", flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", choices=("verify", "ablate"), default="verify")
    p.add_argument("--loops", type=int, default=16)
    p.add_argument("--iterations", type=int, default=20000)
    p.add_argument("--reps", type=int, default=16)
    p.add_argument("--kernels", nargs="+", choices=tuple(KERNELS), default=list(KERNELS))
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    if a.loops < 1 or a.iterations < 0 or a.reps < 1:
        p.error("positive loops/reps and nonnegative iterations required")
    names = list(dict.fromkeys(["upstream"] + a.kernels))
    gc.disable()
    verify(names, a.loops, a.iterations)
    if a.mode == "verify":
        return 0
    samples = {name: [] for name in names}
    records = []
    for rep in range(a.reps):
        offset = rep % len(names)
        for position, name in enumerate(names[offset:] + names[:offset]):
            elapsed, _, _ = production._run(a.loops, a.iterations, KERNELS[name])
            samples[name].append(elapsed)
            records.append(dict(rep=rep+1, position=position+1, kernel=name, total_sec=elapsed))
    reference = statistics.median(samples["upstream"])
    summary = {}
    for name, values in samples.items():
        median = statistics.median(values)
        summary[name] = dict(median_sec=median, mean_sec=statistics.mean(values),
                             stdev_sec=statistics.stdev(values) if len(values)>1 else 0.,
                             time_reduction_pct=100*(1-median/reference))
        print(f"{name:<18} median={median:.6f}s reduction={100*(1-median/reference):.2f}%")
    payload = dict(kind="exploratory_exact_nbody_controls", loops=a.loops, iterations=a.iterations,
                   reps=a.reps, python=sys.version, platform=platform.platform(),
                   controls_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                   variant_sha256=production._variant_sha256(),
                   upstream_sha256=production.base.upstream_sha256(),
                   samples_sec=samples, records=records, summary=summary)
    if a.output:
        a.output.write_text(json.dumps(payload, indent=2)+"\n")
    print("In-process exploratory timing only; confirm on target VM with clean independent processes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
