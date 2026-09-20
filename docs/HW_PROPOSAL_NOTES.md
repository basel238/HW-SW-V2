# Hardware proposal: current evidence and decision

The candidate remains the sequential exact FP64 ray-sphere core. See
[HARDWARE_DESIGN.md](HARDWARE_DESIGN.md) for the datapath, controller, ports,
block diagram, software stack, numerical contract, trade-offs and validation.
No RTL, driver or transport was changed in this result review.

## Updated evidence

The newest full raytrace software run is 791.2145 -> 452.69625 ms/frame,
42.78% lower runtime. The full profile still makes 179,457 sphere queries,
but only 6,934 reach sqrt (3.8639%). This is measured software work, not
hardware performance. The preceding shadow-only 22.63% result is historical.

At the existing assumed 50 MHz, 20 cycles/miss, 80/root, 1 GB/s transfer,
1,024-query batches, 10 us launch/batch and 100 ns native packing/query,
modeled offload costs **118.472828 ms**. Break-even against full requires
removing over **26.17%** of release runtime. The removed fraction is unknown;
traced sphere time and debug sample shares cannot establish it. The model
includes both winning and losing scenarios and does not claim achieved speed.

## Reassessment

A sqrt-only accelerator has a weak workload target: most queries exit before
sqrt. The present complete sphere operation has a clearer boundary, but its
single-query core repeatedly transfers operands. Resident scene/ray data,
batching and the pre-discriminant path deserve priority. A reusable FP64
command engine is an alternative to fixed geometric control; no redesign has
been selected or implemented. A native CPU batch comparator is needed to
separate escaping Python from the value of hardware.

The code-derived clock/cycle budgets, transport and native packing assumptions
remain unvalidated. Batched early-exit behavior may change query counts/mix.
Syntax/elaboration and host reference checks are recorded; behavioral HDL
simulation, achieved timing, deployed transport and pixel equivalence through
hardware remain unverified. The exact operation tree has no FMA, reassociation
or approximation. Nbody hardware remains deferred because matching host
nonintegral pow and ordered dependent state updates needs a distinct contract.
