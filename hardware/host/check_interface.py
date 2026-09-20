#!/usr/bin/env python3
"""Check packing and host formula against upstream. Does not simulate RTL."""
import importlib.util
import math
from pathlib import Path
import random
import struct
import sys

from interface import REQUEST, RESPONSE, pack_request, unpack_request, unpack_response, reference_intersection, decode_batch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'bench'))
try:
    import bm_raytrace_upstream as base
except ImportError:
    sys.exit('Run this check inside the complete repository with bench/ and upstream/.')
up = base.load_upstream()
rng = random.Random(238)
checks = 0
for i in range(256):
    origin = tuple(rng.uniform(-10, 10) for _ in range(3))
    center = tuple(rng.uniform(-10, 10) for _ in range(3))
    direction = tuple(rng.uniform(-1, 1) for _ in range(3))
    radius = rng.uniform(0.01, 10)
    ray = up.Ray(up.Point(*origin), up.Vector(*direction))
    normalized = (ray.vector.x, ray.vector.y, ray.vector.z)
    expected = up.Sphere(up.Point(*center), radius).intersectionTime(ray)
    actual = reference_intersection(origin, normalized, center, radius)
    if expected is None:
        if actual is not None:
            raise AssertionError('miss/root mismatch')
    elif struct.pack('<d', expected) != struct.pack('<d', actual):
        raise AssertionError('host reference expression differs from upstream')
    packed = pack_request(origin, normalized, center, radius, i)
    decoded = unpack_request(packed)
    if decoded != dict(origin=origin, direction=normalized, center=center, radius=radius, tag=i):
        raise AssertionError('request packing did not round-trip')
    status = 0 if actual is None else 1
    response = RESPONSE.pack(0. if actual is None else actual, i, status)
    result = decode_batch(response, [i])[0]
    if result['t'] != actual:
        raise AssertionError('response packing did not round-trip')
    checks += 1
# Exact tangent and interior rays are useful protocol distinctions: root=0 and
# negative root must not be confused with a negative-discriminant miss.
for origin, center, radius, expected in [((0.,0.,0.),(0.,1.,0.),1.,0.),
                                         ((0.,0.,0.),(0.,0.,0.),1.,-1.),
                                         ((0.,0.,0.),(0.,2.,0.),1.,None)]:
    result = reference_intersection(origin, (1.,0.,0.), center, radius)
    if result != expected:
        raise AssertionError('edge-case host formula mismatch')
for bad in (math.inf, math.nan):
    try:
        pack_request((bad,0.,0.), (1.,0.,0.), (0.,0.,0.), 1., 0)
    except ValueError:
        pass
    else:
        raise AssertionError('nonfinite host input accepted')
print(f'Host-only checks: PASS ({checks} upstream formula/packing cases + edge cases)')
print(f'Request bytes={REQUEST.size}; response bytes={RESPONSE.size}. RTL was not simulated.')
