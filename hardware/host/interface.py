"""Host-side wire format for the proposed ray-sphere batch interface.

This module packs buffers and provides a scalar semantic reference. It does not
pretend to drive hardware: a platform transport, driver, and renderer batching
integration are future work. No benchmark imports this module.
"""
from math import isfinite, sqrt
import struct

REQUEST = struct.Struct('<10dII')  # 80-byte geometry, tag, reserved=0: 88 bytes
RESPONSE = struct.Struct('<dII')   # t, tag, status: 16 bytes


def pack_request(origin, direction, center, radius, tag):
    if any(len(vector) != 3 for vector in (origin, direction, center)):
        raise ValueError('origin, direction and center must each have 3 components')
    values = (*origin, *direction, *center, radius)
    if not all(isfinite(value) for value in values) or radius < 0:
        raise ValueError('geometry must be finite with a nonnegative radius')
    if not isinstance(tag, int) or not 0 <= tag < 2**32:
        raise ValueError('tag must fit uint32')
    # Caller supplies upstream Ray.vector; this function does not renormalize it.
    return REQUEST.pack(*values, tag, 0)


def unpack_request(data):
    values = REQUEST.unpack(data)
    if values[-1] != 0:
        raise ValueError('nonzero reserved request word')
    return {'origin': values[:3], 'direction': values[3:6], 'center': values[6:9],
            'radius': values[9], 'tag': values[10]}


def unpack_response(data):
    t, tag, status = RESPONSE.unpack(data)
    if status & ~0x7f:
        raise ValueError('nonzero reserved response status bits')
    has_root, error = bool(status & 1), bool(status & 2)
    if has_root and error:
        raise ValueError('response cannot simultaneously contain a root and an error')
    if has_root and not isfinite(t):
        raise ValueError('nonfinite root')
    return {'t': t if has_root else None, 'tag': tag, 'has_root': has_root,
            'error': error, 'exception_flags': (status >> 2) & 0x1f}


def reference_intersection(origin, direction, center, radius):
    """Same expression tree as upstream; a host model, not an HDL simulation."""
    x, y, z = (center[0] - origin[0], center[1] - origin[1], center[2] - origin[2])
    v = (x * direction[0]) + (y * direction[1]) + (z * direction[2])
    discriminant = (radius * radius) - ((x * x + y * y + z * z) - v * v)
    if discriminant < 0:
        return None
    return v - sqrt(discriminant)


def decode_batch(data, expected_tags):
    """Check ordered replies from a future transport, including sticky FP flags.

    The caller must fall back to its CPU implementation on error=True. A root
    can be negative: Scene logic, not the accelerator, applies the epsilon test.
    """
    expected_tags = list(expected_tags)
    if len(data) != RESPONSE.size * len(expected_tags):
        raise ValueError('batch reply size does not match request count')
    results = []
    for i, tag in enumerate(expected_tags):
        result = unpack_response(data[i * RESPONSE.size:(i + 1) * RESPONSE.size])
        if result['tag'] != tag:
            raise ValueError('batch reply tag/order mismatch')
        results.append(result)
    return results
