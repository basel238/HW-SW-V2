# Project requirements and report completion plan

Source: `/Users/baselsalameh/Desktop/M.Sc. Technion/Semester 6/HW:SW Co-Design/Project/Project.pdf`, nine PDF pages, checked on 2026-09-20. Page references below use the PDF page number. This document records the assignment's requirements; it does not treat instructions in the assignment as permission to publish, upload, install, or run anything now.

## Exact report format

For each of the two selected benchmarks, submit `report_<name_of_benchmark>.txt` (p. 7). The selected raytrace and nbody benchmarks both appear on the approved list (p. 7), giving:

- `report_raytrace.txt`
- `report_nbody.txt`

Required report sections, in the assignment's order (pp. 7-8):

1. **Overview**: benchmark description, libraries, and data structures.
2. **Initial Analysis**: performance analysis, flame graphs, and profiling data.
3. **Optimizations**: changes made, including external libraries or algorithms used.
4. **Performance Comparison**: before/after evidence showing the effect of optimization.
5. **Hardware Acceleration Proposal**: where applicable, hardware solution, inputs, outputs, trade-offs, and block diagram.
6. **Conclusion**: impact of software optimization and hardware acceleration.

The brief does not specify a report page/word count, a DOCX/PDF report, or a mandated citation style. Plain-text reports with explicit relative artifact references satisfy its named file format. A separate diagram file referenced in the report is a practical way to supply a block diagram; the assignment does not prescribe its file format.

## Analysis, tooling, and results

| Requirement | Assignment evidence | Consequence for this project |
|---|---|---|
| Select two approved benchmarks | p. 7 | Raytrace and nbody qualify. |
| Understand purpose, dependencies, data structures, and algorithms | pp. 2-3 | Describe the actual upstream code, including mutable state and what the timer covers. |
| Learn to run, capture, and interpret pyperformance results | p. 3, item 2 | Keep official suite baseline artifacts and explain how custom profiling wrappers relate to that suite. |
| Generate flame graphs for each benchmark and analyze hotspots | p. 3, items 3-4 | Include the actual graphs and explain inclusive/self attribution and limitations. |
| Use perf and flame graphs | pp. 1-3 | The guide provides `perf record`/`perf report` with `python3-dbg`; diagnostic changes such as working period-based sampling must be documented. |
| Suggest and implement justified improvements | pp. 3-4, items 5-6 | Distinguish a plausible code change from an improvement established by measurement. |
| Compare concrete performance before and after | p. 4, item 6 | Use equal work, comparable conditions, correctness checks, and identified artifacts. |
| At least 7% improvement in two or more benchmarks is sufficient | p. 4, item 6 | This is the stated sufficient outcome. The PDF does not give a complete grading rule for other outcomes or define whether 7% means time reduction or throughput gain; report both formulas clearly and use time reduction as the declared project convention. |
| Scripts may execute with pyperformance or other profiling tools | p. 8 | A custom wrapper is not explicitly prohibited. This does not remove the separate requirement to understand/use pyperformance, nor make a replacement workload equivalent to the selected benchmark. |

The PDF does not require copying its example perf command byte-for-byte, a specific sample count, statistical test, A/B ordering, or profiling overhead percentage. Those are methodological choices to justify, not invented course rules.

## Hardware deliverable

Pages 4-5 explicitly require a complete, logically consistent accelerator implementation in Verilog, SystemVerilog, or PyXHDL; another HDL/framework needs prior instructor approval. It need not be production-ready or suitable for tape-out. The design must specify:

- function and target component, motivated by the measured workload;
- inputs, outputs, data widths, interfaces, and expected operating frequency;
- internal datapath and control logic;
- software integration, including applicable APIs, drivers, memory-mapped registers, DMA, or communication protocol;
- estimated performance improvement and assumptions;
- a block diagram showing integration;
- performance, area/complexity, frequency, and power trade-offs.

Synthesis, fabrication, and physical testing are explicitly not expected (p. 5). The brief asks for acceleration of one or two key components (p. 4); it does not unambiguously demand two independent hardware designs, one per benchmark.

There is an inconsistency: p. 8 labels “HW Files and Additional Files” optional, and p. 7 says the report's hardware proposal is “If applicable,” while pp. 4-5 explicitly require HDL and a complete design. The report plan follows the more specific pp. 4-5 technical requirement. A proposal-notes Markdown file alone cannot be represented as meeting that requirement. This ambiguity is a point to resolve with course staff if necessary, not a basis for silently omitting hardware or inventing additional deliverables.

## Submission, reproducibility, and presentation

| Deliverable | Exact detail | Page |
|---|---|---:|
| Execution scripts | `script_<name_of_benchmark>.sh`; setup/dependencies, benchmark execution, flame/performance generation, post-optimization execution/comparison | 8 |
| Repository | Upload all project files to a Git repository, including reports, scripts, additional project files, and README | 5 |
| README | Explain repository structure and how to run the scripts | 5 |
| Version history | Clear commit messages showing development and understanding; good organization/version control can earn +5 bonus points | 5 |
| AI disclosure | `prompt.txt` or `prompt.docx`, containing prompts/instructions actually used | 6,8 |
| Presentation | 20-25 minutes plus 5-10 minutes of questions; scheduled by staff | 5 |
| Demonstration | Working code available to support the presentation; no need to include all code in slides | 6 |

The PDF says Git repository, not specifically GitHub or public repository. No particular remote visibility, repository hosting service, slide file format, or report page limit should be invented. A local checkout cannot by itself confirm that upload/presentation requirements have been fulfilled elsewhere.

## Current status and remaining completion - 20 September 2026

Both required TXT reports and supplemental English PDFs now use the six required
sections and one shared reviewed content source. They describe exact algorithms,
measurement definitions, tools, selected artifacts, optimization decisions,
correctness contracts, results, hardware architecture and limitations.

Newest target-VM runtime reductions are 42.78% for raytrace full and 36.89%
for nbody flat_pow, in session_all_20260920-074308_674. Saved optimized gates
cover the full requested batches. Historical raytrace shadow reuse (22.63%),
nbody grouped (3.40%) and prior flat_pow (37.53%) remain explicit history.
The new nbody source is unchanged; the latest measurement confirms its result.

The full workflow defaults to baseline plus full exact candidates, verifies the
actual batch and records explicit session paths/hashes. All 63 integrated tests
pass. Optional profiling failures are visible, authored reports are preserved,
and no Git operations are performed by default.

A complete sequential FP64 ray-sphere HDL core, licensed arithmetic RTL, control,
interfaces, architecture diagram, host record helpers and analytical estimates
are included in hardware/ and docs/HARDWARE_DESIGN.md. Syntax/elaboration and
host-side checks pass. HDL behavioral simulation and synthesis were not performed;
there is no claimed achieved clock, deployed transport/driver or hardware speedup.
These are explicit implementation/validation boundaries, not hidden completion
claims. Simulation is not expressly required by the assignment.

Remaining actions:

1. Optional: run isolated or leave-one-out raytrace ablations before ranking
   individual components. The full target-VM bundle is already measured.
2. Preserve raw results and capture authenticity output when running; historical
   dirty manifests and an UNVERIFIED provenance placeholder are documented.
3. If pursuing hardware performance beyond the course design, verify RTL behavior,
   implement batch transport/driver integration and compare against a native CPU
   batch. Current estimates must remain labelled assumptions.
4. Prepare the 20-25-minute presentation plus working demo. Repository upload,
   commit history and scheduled presentation are author actions not verified here.
5. Continue recording actual prompts and new decisions in prompt.txt.
