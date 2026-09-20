#!/usr/bin/env python3
"""Analytical offload sensitivity; no measured hardware performance is claimed."""
import argparse
import json
import math


def estimate(*, tests, root_fraction, mhz, bandwidth_gbs, batch, launch_us,
             pack_ns, software_s, offloaded_fraction):
    # Round-number budgets include FSM handshake overhead. Their source is the
    # RTL schedule and HardFloat cycle counter, not a hardware measurement.
    cycles = (1 - root_fraction) * 20 + root_fraction * 80
    compute_s = tests * cycles / (mhz * 1e6)
    transfer_s = tests * (88 + 16) / (bandwidth_gbs * 1e9)
    launch_s = math.ceil(tests / batch) * launch_us * 1e-6
    pack_s = tests * pack_ns * 1e-9
    offload_s = compute_s + transfer_s + launch_s + pack_s
    total_s = software_s * (1 - offloaded_fraction) + offload_s
    return dict(compute_s=compute_s, transfer_s=transfer_s, launch_s=launch_s,
                pack_s=pack_s, offload_s=offload_s, estimated_total_s=total_s,
                speedup=software_s / total_s,
                time_reduction_percent=100 * (1 - total_s / software_s),
                break_even_offloaded_fraction=offload_s / software_s)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--tests', type=int, default=179457)
    p.add_argument('--root-fraction', type=float, default=1.)
    p.add_argument('--mhz', type=float, default=50.)
    p.add_argument('--bandwidth-gbs', type=float, default=1.)
    p.add_argument('--batch', type=int, default=1024)
    p.add_argument('--launch-us', type=float, default=10.)
    p.add_argument('--pack-ns', type=float, default=100.)
    p.add_argument('--software-s', type=float, default=2.444091 / 4)
    p.add_argument('--offloaded-fraction', type=float, default=.5)
    a = p.parse_args()
    if not (0 <= a.root_fraction <= 1 and 0 <= a.offloaded_fraction <= 1):
        p.error('fractions must be between 0 and 1')
    if min(a.tests, a.mhz, a.bandwidth_gbs, a.batch, a.software_s) <= 0:
        p.error('counts, rate and software time must be positive')
    if min(a.launch_us, a.pack_ns) < 0:
        p.error('overheads cannot be negative')
    print(json.dumps({'status':'analytical sensitivity, not measured or simulated',
                      'assumptions':vars(a), 'estimate':estimate(**vars(a))}, indent=2))


if __name__ == '__main__':
    main()
