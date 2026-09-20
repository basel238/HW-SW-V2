# Hardware proposal: evidence and decision

The implemented proposal is a sequential FP64 ray–sphere accelerator. Read
[HARDWARE_DESIGN.md](HARDWARE_DESIGN.md) for the datapath, controller, ports,
reset/backpressure contract, software interface, block diagram and analytical
performance model. RTL and licensed floating-point primitives are in
`hardware/`; syntax/elaboration passed, but hardware behavior and frequency
have not been simulated or measured.

## Evidence supporting the experiment

- The original 100×100 upstream raytrace profile contains 179,457 sphere
  intersection calls. The operation has a defined FP64 input/output boundary.
- The current clean software comparison reports 789.7555 ms/frame upstream and
  611.02275 ms/frame for shadow-ray reuse, a 22.63% time reduction. This is a
  **software measurement**, not hardware evidence. Source:
  `results/comparison_raytrace_20260920-015451/summary.txt`.
- Python calls, temporary objects, attribute lookup and arithmetic dispatch are
  plausible costs removed by moving an entire batch to a native/hardware path.
  Their removal must be measured in a defined integration, not inferred from
  instructions divided by total calls.
- A compiled CPU implementation of the same batch operation is an essential
  future comparator. Otherwise a hardware comparison against Python could
  largely measure the benefit of leaving the interpreter.

## Claims this proposal does not make

Debug-build self samples are not release-runtime Amdahl fractions. A small
native float-handler share does not prove a fixed hardware speedup ceiling,
and a large interpreter share does not prove that a small FPU removes that
share. Historical custom-kernel speedups are not current upstream results.
There is no verified 1 GHz clock, one-query-per-cycle throughput, measured
hardware speedup, area ratio between FP32 and FP64, or demonstrated equivalence
of an approximate reciprocal-square-root datapath.

The implemented core keeps upstream's exact operation tree with separate FP64
rounding. Batched software/transport integration is specified but not
implemented; per-intersection MMIO would keep Python dispatch and add overhead.
Batching may also increase query count by evaluating work that the visibility
loop would have skipped. Both effects belong in the performance estimate.

## Honest analytical result

For an illustrative 50 MHz clock, all-root 80-cycle budget, 1 GB/s transfer,
1,024-query batches, 10 microseconds launch overhead and 100 ns native packing
per query, the old 179,457-call workload costs about 325.500 ms to offload.
Against 611.02275 ms optimized software, it must remove more than 53.27% of
runtime merely to break even. That removed fraction has not been established.
The sensitivity table in the design document includes faster and slower cases;
these are assumptions and calculations, not achieved performance.

Nbody hardware is deferred because exact upstream nonintegral `pow` semantics
and sequential velocity dependencies require a different, more involved
contract. The current nbody software optimizations remain independent of this
raytrace hardware proposal.
