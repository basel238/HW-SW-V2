#!/usr/bin/env bash
# =============================================================================
# script_raytrace.sh — full analysis pipeline for the `raytrace` benchmark.
#
# Deliverable for the HWSW project (file name mandated by the brief:
# "script_<name_of_benchmark>.sh").
#
# WHAT THIS BENCHMARK IS
#   A recursive ray tracer: 4 spheres + a checkerboard plane, Lambertian
#   shading, hard shadows, and reflection rays to depth 3. Pure Python floats.
#
# WHY IT WAS CHOSEN
#   * Compute-bound and FP-heavy -> the profile is dominated by arithmetic
#     wrapped in interpreter dispatch, which is the cleanest possible motivation
#     for the multiply-accumulate / vector-ALU hardware proposal in stage 7.
#   * The Vector class makes the "abstraction costs allocations" story visible
#     in a flame graph, not just arguable in prose.
#   * Deterministic output -> a SHA-256 image checksum is an exact correctness
#     oracle, so an optimization cannot silently trade accuracy for speed.
#
# WHAT IT PRODUCES (under results/<tag>/)
#   timing/clean_*_summary.txt   median/stdev from UNPROFILED runs  <-- quote
#   perf/stat_*.txt              IPC, cache misses, branch misses
#   perf/report_*.txt            the brief's `perf report --stdio` output
#   flame/*.svg                  flame graph + icicle + Python-only + py-spy
#   raw/cprofile_*.txt           exact call counts
#   raw/pyperf_*_stats.txt       pyperformance mean +- stdev
#   manifest.txt                 full environment capture
#
# MEASUREMENT INTEGRITY
#   Profilers perturb what they measure, so no profiler is ever attached to a
#   run whose timing we quote. See the PHASE PLAN in --help and the rationale
#   block in config/bench.env.
# =============================================================================
set -Eeuo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "$HERE/lib/common.sh"
# shellcheck source=lib/pipeline.sh
source "$HERE/lib/pipeline.sh"

BENCH_NAME="raytrace"
# Workload selection. USE_UPSTREAM=1 (the default) measures the REAL
# pyperformance kernel, imported unmodified from upstream/. USE_UPSTREAM=0
# measures the independently written stand-in kept for comparison.
if [[ "${USE_UPSTREAM:-1}" == "1" ]]; then
  BASELINE="$HERE/bench/bm_raytrace_upstream.py"
  OPTIMIZED="$HERE/variants/bm_raytrace_upstream_opt.py"
  WORKLOAD_KIND="UPSTREAM pyperformance kernel (unmodified)"
  [[ -f "$HERE/upstream/bm_raytrace_upstream.py" ]] || die \
    "upstream kernel missing -> run ./setup/05_get_upstream.sh
     (or set USE_UPSTREAM=0 to measure the custom stand-in instead)"
else
  BASELINE="$HERE/bench/bm_raytrace.py"
  OPTIMIZED="$HERE/variants/bm_raytrace_opt.py"
  WORKLOAD_KIND="custom stand-in (NOT the upstream benchmark)"
fi

pipeline_parse_args "$@" || { pipeline_usage "$BENCH_NAME"; exit 2; }
[[ "${PIPELINE_HELP:-0}" == "1" ]] && { pipeline_usage "$BENCH_NAME"; exit 0; }

if [[ "${PIPELINE_LIST_ONLY:-0}" == "1" ]]; then
  pipeline_usage "$BENCH_NAME"; exit 0
fi

# Kernel selection applies only to the optimized wrapper, in every phase.
# The baseline wrapper always runs the unmodified upstream benchmark.
OPT_ARGS=()
if [[ "${USE_UPSTREAM:-1}" == "1" ]]; then
  RAYTRACE_KERNEL="${PIPELINE_KERNEL:-full}"
  OPT_ARGS=(--kernel "$RAYTRACE_KERNEL")
fi

[[ -f "$BASELINE"  ]] || die "missing baseline: $BASELINE"
[[ -f "$OPTIMIZED" ]] || die "missing optimized variant: $OPTIMIZED"
# STAGE 0: verify the measured workload is the genuine benchmark before any
# measurement happens. Skipped only when deliberately measuring the stand-ins.
if [[ "${USE_UPSTREAM:-1}" == "1" && "${SKIP_WORKLOAD_VERIFY:-0}" != "1" ]]; then
  "$HERE/tools/verify_upstream.sh" --quiet \
    || die "workload verification failed — refusing to produce numbers"
fi

mkdir -p "$RESULTS_DIR"
prepare_benchmark_session

hdr "raytrace — HWSW benchmark analysis pipeline"
log "variant selection : $VARIANT_SEL"
log "workload          : $WORKLOAD_KIND"
log "baseline          : ${BASELINE#$HERE/}"
log "optimized         : ${OPTIMIZED#$HERE/}"
if [[ "${USE_UPSTREAM:-1}" == "1" ]]; then
  log "optimized kernel  : $RAYTRACE_KERNEL"
fi

if [[ "$VARIANT_SEL" == "baseline" || "$VARIANT_SEL" == "both" ]]; then
  run_variant "$BENCH_NAME" "baseline" "$BASELINE"
  BASE_RUN_DIR="$LAST_RUN_DIR"
  record_session_run baseline
fi

if [[ "$VARIANT_SEL" == "optimized" || "$VARIANT_SEL" == "both" ]]; then
  run_variant "$BENCH_NAME" "optimized" "$OPTIMIZED" ${OPT_ARGS[@]+"${OPT_ARGS[@]}"}
  OPT_RUN_DIR="$LAST_RUN_DIR"
  record_session_run optimized
fi

# Auto-compare when both halves exist in this session.
if [[ "$VARIANT_SEL" == "both" ]]; then
  hdr "before/after comparison"
  "$HERE/tools/compare.sh" "$BENCH_NAME" "$BASE_RUN_DIR" "$OPT_RUN_DIR" "$SESSION_DIR/comparison_${BENCH_NAME}" || die "comparison failed"
  printf 'comparison\t%s\n' "$SESSION_DIR/comparison_${BENCH_NAME}" >> "$SESSION_DIR/${BENCH_NAME}.tsv"
fi

ok "raytrace pipeline complete"
