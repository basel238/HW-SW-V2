#!/usr/bin/env bash
# =============================================================================
# script_nbody.sh — full analysis pipeline for the `nbody` benchmark.
#
# Deliverable for the HWSW project (file name mandated by the brief:
# "script_<name_of_benchmark>.sh").
#
# WHAT THIS BENCHMARK IS
#   Symplectic integration of the Sun + 4 Jovian planets (the classic Computer
#   Language Benchmarks Game n-body). O(n^2) pairwise gravitational force
#   accumulation, 20000 timesteps per simulation.
#
# WHY IT WAS CHOSEN
#   * Ten pair interactions repeat on every timestep, making recurring Python
#     arithmetic, container access and loop overhead useful optimization targets.
#   * Five bodies are a small numerical workload, but Python objects occupy
#     more than their raw doubles. Cache and instruction counters must be
#     measured; source size alone does not establish a hardware bottleneck.
#   * Correctness compares energy AND every final position/velocity component
#     against upstream at the same step count. Grouped and flat_pow require
#     bit-identical results; sqrt-based candidates use numerical tolerances.
#     The integrator does not conserve physical energy exactly.
#
# COMPLEMENTARITY WITH raytrace
#   Raytrace performs many small method calls and constructs geometry objects.
#   Nbody concentrates work in a repeated numerical loop, but still executes
#   interpreter branches and produces Python float objects. Their profiles
#   distinguish the costs and support separate, measured optimization choices.
#
# WHAT IT PRODUCES / MEASUREMENT INTEGRITY
#   Identical to script_raytrace.sh; see that file's header and --help.
# =============================================================================
set -Eeuo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "$HERE/lib/common.sh"
# shellcheck source=lib/pipeline.sh
source "$HERE/lib/pipeline.sh"

BENCH_NAME="nbody"
# Workload selection. USE_UPSTREAM=1 (the default) measures the REAL
# pyperformance kernel, imported unmodified from upstream/. USE_UPSTREAM=0
# measures the independently written stand-in kept for comparison.
if [[ "${USE_UPSTREAM:-1}" == "1" ]]; then
  BASELINE="$HERE/bench/bm_nbody_upstream.py"
  OPTIMIZED="$HERE/variants/bm_nbody_upstream_opt.py"
  WORKLOAD_KIND="UPSTREAM pyperformance kernel (unmodified)"
  [[ -f "$HERE/upstream/bm_nbody_upstream.py" ]] || die \
    "upstream kernel missing -> run ./setup/05_get_upstream.sh
     (or set USE_UPSTREAM=0 to measure the custom stand-in instead)"
else
  BASELINE="$HERE/bench/bm_nbody.py"
  OPTIMIZED="$HERE/variants/bm_nbody_opt.py"
  WORKLOAD_KIND="custom stand-in (NOT the upstream benchmark)"
fi

pipeline_parse_args "$@" || { pipeline_usage "$BENCH_NAME"; exit 2; }
[[ "${PIPELINE_HELP:-0}" == "1" ]] && { pipeline_usage "$BENCH_NAME"; exit 0; }

if [[ "${PIPELINE_LIST_ONLY:-0}" == "1" ]]; then
  pipeline_usage "$BENCH_NAME"; exit 0
fi

# Apply selection only to the optimized wrapper, consistently in every phase.
OPT_ARGS=()
if [[ "${USE_UPSTREAM:-1}" == "1" ]]; then
  NBODY_KERNEL="${PIPELINE_KERNEL:-flat_pow}"
  OPT_ARGS=(--kernel "$NBODY_KERNEL")
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

hdr "nbody — HWSW benchmark analysis pipeline"
log "variant selection : $VARIANT_SEL"
log "workload          : $WORKLOAD_KIND"
log "baseline          : ${BASELINE#$HERE/}"
log "optimized         : ${OPTIMIZED#$HERE/}"
if [[ "${USE_UPSTREAM:-1}" == "1" ]]; then
  log "optimized kernel  : $NBODY_KERNEL"
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

if [[ "$VARIANT_SEL" == "both" ]]; then
  hdr "before/after comparison"
  "$HERE/tools/compare.sh" "$BENCH_NAME" "$BASE_RUN_DIR" "$OPT_RUN_DIR" "$SESSION_DIR/comparison_${BENCH_NAME}" || die "comparison failed"
  printf 'comparison\t%s\n' "$SESSION_DIR/comparison_${BENCH_NAME}" >> "$SESSION_DIR/${BENCH_NAME}.tsv"
fi

ok "nbody pipeline complete"
