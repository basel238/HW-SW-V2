# Latest raytrace shadow-only: performance counter evidence

Only the pair `raytrace_baseline_20260920-012836` / `raytrace_optimized_20260920-014248` is used. Both render four 100×100 frames per process with release Python 3.10.12, GC off, CPU 0 pinning. The optimized workload log explicitly confirms `kernel=shadow_ray` in all five repeats.

## Primary counter set: TXT

These are means over five processes. “Per frame” divides each mean by four.

|Event|Baseline per frame|Shadow per frame|Change|
|---|---:|---:|---:|
|instructions|5,067,947,180.50|3,892,298,231.25|-23.20%|
|cycles|1,915,135,339.25|1,486,510,385.50|-22.38%|
|branches|652,960,329.75|497,212,246.50|-23.85%|
|branch-misses|2,403,987.75|2,214,941.75|-7.86%|
|L1-dcache-loads|1,639,053,961.25|1,263,443,767.50|-22.92%|
|L1-dcache-load-misses|43,420,936.25|37,610,804.25|-13.38%|
|dTLB-loads|816,933,436.25|628,908,119.50|-23.02%|
|dTLB-load-misses|67,354.75|89,391.25|+32.72%|
|cache-references|2,356,041.25|2,551,436.75|+8.29%|
|cache-misses|2,453.00|5,949.50|+142.54%|

Ratios of means (not necessarily the printed aggregation in perf):

|Metric|Baseline|Shadow|
|---|---:|---:|
|IPC|2.646261|2.618413|
|branch_miss_percent|0.368168|0.445472|
|L1_load_miss_percent|2.649146|2.976848|
|dTLB_load_miss_percent|0.008245|0.014214|
|generic_cache_miss_percent|0.104115|0.233182|

## Independent CSV repeat set

|Event|TXT change|CSV change|
|---|---:|---:|
|instructions|-23.20%|-22.96%|
|cycles|-22.38%|-20.86%|
|branches|-23.85%|-23.20%|
|branch-misses|-7.86%|-0.68%|
|L1-dcache-loads|-22.92%|-23.05%|
|L1-dcache-load-misses|-13.38%|-10.57%|
|dTLB-loads|-23.02%|-22.87%|
|dTLB-load-misses|+32.72%|+131.19%|
|cache-references|+8.29%|-4.64%|
|cache-misses|+142.54%|+85.99%|

## Interpretation

The main mechanism is less executed work: about 23% fewer instructions, L1 data loads and dTLB load accesses; about 21–22% fewer cycles; nearly unchanged IPC. This matches eliminating redundant Ray/Vector construction, normalization and helper calls while retaining intersection work. It is not evidence of a large improvement in per-instruction CPU efficiency.

Absolute L1 load misses decrease, but less than total loads, so the miss fraction rises. Branch-miss fraction likewise rises while absolute misses are flat to modestly lower. This is expected when removing a frequently executed, relatively predictable segment. Neither rate increase contradicts an overall speedup.

## Limits

- TXT and CSV are separate perf stat invocations with five fresh processes each; never combine numerator from one with denominator from the other.
- Counts are per-process mean counts, scaled for multiplexing; divide by four for per-frame normalization, not by five.
- Hardware events run for about 40–60% of wall accounting time, in a one-vCPU KVM VM. Large consistent instruction changes are strong corroboration; fine-grained cache and stall interpretation is limited.
- Printed perf metric ratios can differ from ratios of mean counts due to perf repetition/metric aggregation. Calculated table uses ratios of mean counts.
- Topdown is system-wide and nonsensical: baseline bad speculation -61.2%, optimized -60.6%. Reject all its bottleneck percentages, including 86% backend bound.
- LLC-loads and LLC-load-misses are unsupported, not zero. Generic cache-references/cache-misses should not silently be treated as trustworthy LLC/DRAM measurements.
- Generic cache-miss counts have very high reported variation (TXT 56.14/26.64%, CSV 61.81/50.47%). No evidence supports saying cache misses were eliminated or cache hierarchy improved.
- Exact candidate hash and dirty file identities are not in manifests: same commit d54e98c but dirty 6 vs 8 files. Runtime logs identify shadow_ray, which is stronger evidence of selected kernel than the generic manifest wording.
- Perf stat counts whole-process startup/import/wrapper overhead as well as four frames, whereas clean RESULT measures internal benchmark time. Use clean runtime for the 7% result.
- Low cache-miss rates and unchanged IPC do not prove a particular frontend/backend bound classification.

## Sources

- `/Users/baselsalameh/Desktop/M.Sc. Technion/Semester 6/HW:SW Co-Design/HW-SW-V2/results/raytrace_baseline_20260920-012836/perf/stat_baseline.txt`
- `/Users/baselsalameh/Desktop/M.Sc. Technion/Semester 6/HW:SW Co-Design/HW-SW-V2/results/raytrace_optimized_20260920-014248/perf/stat_optimized.txt`
- `/Users/baselsalameh/Desktop/M.Sc. Technion/Semester 6/HW:SW Co-Design/HW-SW-V2/results/raytrace_baseline_20260920-012836/perf/stat_baseline.csv`
- `/Users/baselsalameh/Desktop/M.Sc. Technion/Semester 6/HW:SW Co-Design/HW-SW-V2/results/raytrace_optimized_20260920-014248/perf/stat_optimized.csv`
