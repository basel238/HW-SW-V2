#!/usr/bin/env bash
# =============================================================================
# lib/pipeline.sh — the generic 6-phase pipeline shared by every script_*.sh.
#
# Sourced AFTER lib/common.sh. Keeps script_raytrace.sh / script_nbody.sh thin
# and declarative so a reader can see the benchmark-specific facts immediately
# without wading through plumbing.
# =============================================================================

# run_variant <bench> <variant> <script> <extra_args...>
# Executes all enabled phases for ONE variant, in strict order.
run_variant() {
  local bench="$1" variant="$2" script="$3"; shift 3
  local extra=("$@")

  init_run "$bench" "$variant"
  # Only demand perf if a phase that USES perf is enabled. Previously
  # --time-only still failed without perf, contradicting its own purpose.
  if [[ "$ENABLE_PERF_STAT" == "1" || "$ENABLE_PERF_RECORD" == "1" \
        || "$ENABLE_CACHE_PROFILE" == "1" ]]; then
    require_perf
    require_python_dbg
    probe_pmu
  else
    log "perf phases disabled -> skipping perf preconditions and PMU probe"
    PMU_OK=0; PERF_EVENTS=""; export PMU_OK PERF_EVENTS
  fi
  capture_env "$script" ${extra[@]+"${extra[@]}"}

  local loops
  loops="$(calibrate_loops "$script" ${extra[@]+"${extra[@]}"})"
  log "loops=$loops (target ~${TARGET_SEC}s per pass)"
  echo "$loops" > "$RUN_DIR/timing/loops.txt"
  # Verify the complete timed batch, not a default one-loop smoke test.
  [[ "$ENABLE_VERIFY" == "1" ]] || die "correctness verification cannot be disabled in this pipeline"
  run_verify "$script" --loops "$loops" ${extra[@]+"${extra[@]}"}
  phase_status verify passed "loops=$loops"
  local p flag
  for p in CLEAN_TIMING PERF_STAT PERF_RECORD CACHE_PROFILE CPROFILE PYSPY PYPERFORMANCE; do
    flag="ENABLE_$p"
    if [[ "${!flag}" == "1" ]]; then phase_status "$p" requested; else phase_status "$p" disabled; fi
  done

  # --- Phases 2-6 -----------------------------------------------------------
  run_clean_timing  "$script" "$loops" ${extra[@]+"${extra[@]}"}  # QUOTABLE
  run_perf_stat     "$script" "$loops" ${extra[@]+"${extra[@]}"}
  run_perf_record   "$script" "$loops" "$variant" ${extra[@]+"${extra[@]}"}
  run_cache_profile "$script" "$loops" "$variant" ${extra[@]+"${extra[@]}"}
  run_cprofile      "$script" "$loops" ${extra[@]+"${extra[@]}"}
  run_pyspy         "$script" "$loops" ${extra[@]+"${extra[@]}"}

  # Only the upstream benchmark name is meaningful to pyperformance, and only
  # for the baseline: our optimized variant is not an upstream benchmark.
  if [[ "$variant" == "baseline" ]]; then
    run_pyperformance "$bench" "$variant"
  else
    phase_status pyperformance not_applicable "optimized wrapper is outside upstream harness"
    log "skipping pyperformance for '$variant' (not an upstream benchmark)"
  fi

  phase_status workflow completed "review unavailable phases separately"
  finish_run
  LAST_RUN_DIR="$RUN_DIR"
}

# Standard CLI shared by all script_*.sh files.
pipeline_usage() {
  local bench="$1"
  local kernel_help=""
  if [[ "$bench" == "raytrace" ]]; then
    kernel_help="  --kernel K      upstream | guards | shadow_ray | combined | sphere_scalar | camera | nearest_hit | checkerboard | full | slots | full_slots
                  optimized arm only, USE_UPSTREAM=1 (default: full)"
  elif [[ "$bench" == "nbody" ]]; then
    kernel_help="  --kernel K      upstream | grouped | flat_pow | flat_sqrt | sqrt | hoist | full
                  optimized arm only, USE_UPSTREAM=1 (default: flat_pow)"
  fi
  cat <<EOF
Usage: ./script_${bench}.sh [OPTIONS]

Runs the full profiling pipeline for the '${bench}' benchmark.

OPTIONS
  --variant V     baseline | optimized | both     (default: both)
  --quick         fast smoke test: fewer reps, no cProfile/py-spy/pyperformance
  --profile-only  skip clean timing; only collect perf data + flame graphs
  --time-only     only clean timing (no profilers at all) — fastest path to a
                  defensible speedup number
  --loops N       force the loop count instead of auto-calibrating
${kernel_help}
  --list-phases   print the phase plan and exit
  -h, --help      this message

PHASE PLAN (see config/bench.env for the rationale)
  1  verify          correctness gate           hard-fail on mismatch
  2  clean timing    NO profiler                <-- the only quotable numbers
  3  perf stat       separate counter runs     IPC, cache, branch misses
  4  perf record     sampling, high ovh         flame graphs  (timing discarded)
  5  cProfile        tracing, 2-5x ovh          exact call counts
  6  pyperformance   upstream-only cross-check   independent harness mean +- stdev

EXAMPLES
  ./script_${bench}.sh                     # everything, both variants
  ./script_${bench}.sh --quick             # ~1 min smoke test
  ./script_${bench}.sh --variant baseline  # baseline only
  ./script_${bench}.sh --time-only         # just the speedup number
  SAMPLE_FREQ=499 CALLGRAPH=fp ./script_${bench}.sh   # cheaper sampling
EOF
}

# Parses the shared flags. Sets VARIANT_SEL and mutates the ENABLE_* toggles.
pipeline_parse_args() {
  VARIANT_SEL="both"
  PIPELINE_KERNEL=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --variant)      VARIANT_SEL="${2:?--variant needs a value}"; shift 2 ;;
      --loops)        LOOPS="${2:?--loops needs a value}"; export LOOPS; shift 2 ;;
      --kernel)
        if [[ "${USE_UPSTREAM:-1}" != "1" ]]; then
          err "--kernel requires USE_UPSTREAM=1"; return 2
        fi
        case "${BENCH_NAME:-}" in
          raytrace)
            case "${2:-}" in
              upstream|guards|shadow_ray|combined|sphere_scalar|camera|nearest_hit|checkerboard|full|slots|full_slots) PIPELINE_KERNEL="$2" ;;
              *) err "--kernel needs one of: upstream, guards, shadow_ray, combined, sphere_scalar, camera, nearest_hit, checkerboard, full, slots, full_slots"; return 2 ;;
            esac ;;
          nbody)
            case "${2:-}" in
              upstream|grouped|flat_pow|flat_sqrt|sqrt|hoist|full) PIPELINE_KERNEL="$2" ;;
              *) err "--kernel needs one of: upstream, grouped, flat_pow, flat_sqrt, sqrt, hoist, full"; return 2 ;;
            esac ;;
          *) err "--kernel is supported only for raytrace or nbody with USE_UPSTREAM=1"; return 2 ;;
        esac
        shift 2 ;;
      --quick)
        # Smoke test: keep the cheap, high-signal phases; drop the slow ones.
        CLEAN_REPS=3; REPS=2; TARGET_SEC=1.0
        ENABLE_CPROFILE=0; ENABLE_PYSPY=0; ENABLE_PYPERFORMANCE=0
        ENABLE_CACHE_PROFILE=0
        export CLEAN_REPS REPS TARGET_SEC ENABLE_CPROFILE ENABLE_PYSPY \
               ENABLE_PYPERFORMANCE ENABLE_CACHE_PROFILE
        log "--quick: 3 reps, no cProfile/py-spy/pyperformance"; shift ;;
      --profile-only)
        ENABLE_CLEAN_TIMING=0; ENABLE_PYPERFORMANCE=0
        export ENABLE_CLEAN_TIMING ENABLE_PYPERFORMANCE
        log "--profile-only: skipping clean timing"; shift ;;
      --time-only)
        ENABLE_PERF_STAT=0; ENABLE_PERF_RECORD=0; ENABLE_FLAMEGRAPH=0
        ENABLE_CPROFILE=0; ENABLE_PYSPY=0; ENABLE_CACHE_PROFILE=0
        ENABLE_PYPERFORMANCE=0
        export ENABLE_PERF_STAT ENABLE_PERF_RECORD ENABLE_FLAMEGRAPH \
               ENABLE_CPROFILE ENABLE_PYSPY ENABLE_CACHE_PROFILE ENABLE_PYPERFORMANCE
        log "--time-only: clean timing only, zero instrumentation"; shift ;;
      --list-phases)  PIPELINE_LIST_ONLY=1; shift ;;
      -h|--help)      PIPELINE_HELP=1; shift ;;
      *)              err "unknown option: $1"; return 2 ;;
    esac
  done
  case "$VARIANT_SEL" in
    baseline|optimized|both) ;;
    *) err "--variant must be baseline, optimized, or both"; return 2 ;;
  esac
  [[ -z "$LOOPS" || "$LOOPS" =~ ^[1-9][0-9]*$ ]] || { err "--loops must be a positive integer"; return 2; }
  export VARIANT_SEL
}

# A paired script invocation shares baseline-calibrated work and records exact
# directories. latest_* remains a convenience for humans, never session input.
prepare_benchmark_session() {
  if [[ -z "${SESSION_DIR:-}" ]]; then
    SESSION_DIR="$RESULTS_DIR/session_${BENCH_NAME}_$(date +%Y%m%d-%H%M%S)_$$"
    export SESSION_DIR
  fi
  mkdir -p "$SESSION_DIR"
  LOOPS="$(calibrate_loops "$BASELINE")"
  export LOOPS
  printf 'benchmark\t%s\nloops\t%s\n' "$BENCH_NAME" "$LOOPS" > "$SESSION_DIR/${BENCH_NAME}.tsv"
}
record_session_run() {
  printf '%s\t%s\n' "$1" "$LAST_RUN_DIR" >> "$SESSION_DIR/${BENCH_NAME}.tsv"
}
