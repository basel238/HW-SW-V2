#!/usr/bin/env bash
# Full workflow; authored reports are never regenerated or overwritten.
set -Eeuo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$HERE/lib/common.sh"
PASSTHRU=(); NBODY_KERNEL=flat_pow; RAYTRACE_KERNEL=full; DOCTOR_ARGS=()
while (( $# )); do
  case "$1" in
    --nbody-kernel) NBODY_KERNEL="${2:?missing kernel}"; shift 2 ;;
    --raytrace-kernel) RAYTRACE_KERNEL="${2:?missing kernel}"; shift 2 ;;
    --kernel) die "use --nbody-kernel and/or --raytrace-kernel" ;;
    --time-only) PASSTHRU+=("$1"); DOCTOR_ARGS=(--time-only); shift ;;
    -h|--help)
      echo "Usage: ./run_all.sh [--time-only|--quick|--profile-only] [--loops N]"
      echo "       [--nbody-kernel flat_pow] [--raytrace-kernel full]"
      echo "Default: both variants of both benchmarks, all configured phases."
      exit 0 ;;
    *) PASSTHRU+=("$1"); shift ;;
  esac
done
# Validate both selections before creating results or running expensive phases.
for b in $PROJECT_BENCHES; do
  case "$b" in nbody) k="$NBODY_KERNEL";; raytrace) k="$RAYTRACE_KERNEL";; *) die "unknown benchmark $b";; esac
  "$HERE/script_${b}.sh" ${PASSTHRU[@]+"${PASSTHRU[@]}"} --kernel "$k" --list-phases >/dev/null
done
if [[ "${USE_UPSTREAM:-1}" == "1" && "${SKIP_WORKLOAD_VERIFY:-0}" != "1" ]]; then
  "$HERE/tools/verify_upstream.sh" || die "upstream verification failed"
fi
"$HERE/tools/doctor.sh" ${DOCTOR_ARGS[@]+"${DOCTOR_ARGS[@]}"} || die "preflight failed"
SESSION_DIR="$RESULTS_DIR/session_all_$(date +%Y%m%d-%H%M%S)_$$"
export SESSION_DIR SKIP_WORKLOAD_VERIFY=1
mkdir -p "$SESSION_DIR"
printf 'nbody_kernel\t%s\nraytrace_kernel\t%s\ngit_metadata\t%s\n' "$NBODY_KERNEL" "$RAYTRACE_KERNEL" "$CAPTURE_GIT_METADATA" > "$SESSION_DIR/session.tsv"
FAILED=()
for b in $PROJECT_BENCHES; do
  case "$b" in nbody) k="$NBODY_KERNEL";; raytrace) k="$RAYTRACE_KERNEL";; esac
  # A subprocess invoked as an if condition would disable Bash errexit inside
  # its functions. Launch the script as an external command with its own -e.
  if bash "$HERE/script_${b}.sh" ${PASSTHRU[@]+"${PASSTHRU[@]}"} --kernel "$k"; then
    printf '%s\tcompleted\n' "$b" >> "$SESSION_DIR/session.tsv"
  else
    FAILED+=("$b"); printf '%s\tfailed\n' "$b" >> "$SESSION_DIR/session.tsv"
  fi
done
log "Exact result directories and comparisons: $SESSION_DIR"
printf 'New measurements require review before updating authored reports.\n' > "$SESSION_DIR/REPORT_UPDATE_REQUIRED.txt"
log "Authored reports preserved; review new session before updating their findings."
if (( ${#FAILED[@]} )); then die "failed benchmarks: ${FAILED[*]}"; fi
ok "workflow complete; inspect phases.tsv in each result for unavailable optional measurements"
