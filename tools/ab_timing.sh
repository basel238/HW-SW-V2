#!/usr/bin/env bash
# =============================================================================
# tools/ab_timing.sh — INTERLEAVED A/B timing, a controlled way to
# establish a speedup.
#
# WHY THIS EXISTS
# ---------------
# The main pipeline measures baseline fully, then optimized fully, minutes later.
# An external review correctly noted that sequential blocks cannot separate the
# code change from host drift, thermal effects, or any other slow-moving
# systematic difference — and that "improvement > 2 x stdev" is a rule of thumb,
# not a confidence interval.
#
# This tool addresses both:
#   * ALTERNATES baseline/optimized process by process (A B A B ...), optionally
#     randomizing the order within each round, so drift affects both arms
#     more evenly rather than loading onto one.
#   * Reports a bootstrap confidence interval for the speedup, not just a
#     point estimate and a heuristic.
#
# Usage:
#   ./tools/ab_timing.sh raytrace [rounds]
#   ./tools/ab_timing.sh nbody 15
#   ./tools/ab_timing.sh raytrace 11 --shuffle
#
# Output: results/abtiming_<bench>_<ts>/{summary.txt,samples.csv}
# =============================================================================
set -Eeuo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$HERE/../lib/common.sh"

BENCH="${1:?usage: ab_timing.sh <raytrace|nbody> [rounds] [--shuffle]}"
ROUNDS="${2:-11}"
shift $(( $# > 1 ? 2 : 1 ))
SHUFFLE=0; KERNEL=""
while (( $# )); do
  case "$1" in
    --shuffle) SHUFFLE=1; shift;;
    --kernel) KERNEL="${2:?missing kernel}"; shift 2;;
    *) die "unknown option $1";;
  esac
done
[[ "$ROUNDS" =~ ^[1-9][0-9]*$ && "$ROUNDS" -ge 3 ]] || die "rounds must be >=3"
if [[ -z "$KERNEL" ]]; then
  case "$BENCH" in nbody) KERNEL=flat_pow;; raytrace) KERNEL=full;; esac
fi
OPT_ARGS=()
if [[ "${USE_UPSTREAM:-1}" == "1" ]]; then OPT_ARGS=(--kernel "$KERNEL"); fi

case "$BENCH" in
  raytrace|nbody) ;;
  *) die "unknown benchmark '$BENCH' (expected raytrace or nbody)" ;;
esac
# Same workload selection as the deliverable scripts.
if [[ "${USE_UPSTREAM:-1}" == "1" ]]; then
  BASE="$REPO_ROOT/bench/bm_${BENCH}_upstream.py"
  OPT="$REPO_ROOT/variants/bm_${BENCH}_upstream_opt.py"
  log "workload: UPSTREAM pyperformance kernel"
else
  BASE="$REPO_ROOT/bench/bm_${BENCH}.py"
  OPT="$REPO_ROOT/variants/bm_${BENCH}_opt.py"
  log "workload: custom stand-in"
fi
[[ -f "$BASE" && -f "$OPT" ]] || die "benchmark sources missing"
if [[ "${USE_UPSTREAM:-1}" == "1" && "${SKIP_WORKLOAD_VERIFY:-0}" != "1" ]]; then
  "$REPO_ROOT/tools/verify_upstream.sh" --quiet || die "upstream verification failed"
fi

OUT="$RESULTS_DIR/abtiming_${BENCH}_$(date +%Y%m%d-%H%M%S)_$$"
mkdir -p "$OUT"
( cd "$RESULTS_DIR" && ln -sfn "$(basename "$OUT")" "latest_abtiming_${BENCH}" )

hdr "interleaved A/B timing — $BENCH"
log "rounds=$ROUNDS  shuffle=$SHUFFLE  (2 processes per round)"

# CRITICAL: both arms must do IDENTICAL work. Calibrate ONCE on the baseline and
# force that loop count on both, rather than letting each self-calibrate to a
# different value.
py_env
LOOPS_FIXED="${LOOPS:-}"
if [[ -z "$LOOPS_FIXED" ]]; then
  log "calibrating once on the baseline (both arms will use this value)"
  LOOPS_FIXED="$("$PY_REL" "$BASE" --mode calibrate 2>/dev/null | tail -1 | tr -dc '0-9')"
  [[ -n "$LOOPS_FIXED" && "$LOOPS_FIXED" -gt 0 ]] 2>/dev/null || die "calibration failed"
fi
ok "fixed loops = $LOOPS_FIXED for BOTH variants (equal work by construction)"

[[ "$LOOPS_FIXED" =~ ^[1-9][0-9]*$ ]] || die "LOOPS must be positive"
RUN_DIR="$OUT"; RUN_TAG="$(basename "$OUT")"; VARIANT=paired
mkdir -p "$OUT/logs"
capture_env "$BASE" "$OPT" ${OPT_ARGS[@]+"${OPT_ARGS[@]}"}
"$PY_REL" "$BASE" --mode verify --loops "$LOOPS_FIXED" > "$OUT/logs/verify_baseline.log" 2>&1 || die "baseline verification failed"
"$PY_REL" "$OPT" --mode verify --loops "$LOOPS_FIXED" ${OPT_ARGS[@]+"${OPT_ARGS[@]}"} > "$OUT/logs/verify_optimized.log" 2>&1 || die "optimized verification failed"
printf '%s\n' "$LOOPS_FIXED" > "$OUT/loops.txt"
build_pin
CSV="$OUT/samples.csv"
echo "round,order,variant,total_sec" > "$CSV"

run_one() { # run_one <variant> <script> <round> <order>
  local variant="$1" script="$2" round="$3" order="$4" out t
  local args=("$script" --mode raw --loops "$LOOPS_FIXED")
  if [[ "$DISABLE_GC" == "1" ]]; then args+=(--no-gc); fi
  if [[ "$variant" == "optimized" ]]; then args+=(${OPT_ARGS[@]+"${OPT_ARGS[@]}"}); fi
  out="$(${PIN[@]+"${PIN[@]}"} "$PY_REL" "${args[@]}" 2>&1)" || {
    printf '%s\n' "$out" >&2; die "round $round $variant failed"; }
  t="$(printf '%s' "$out" | grep -oE 'total_sec=[0-9.]+' | head -1 | cut -d= -f2)"
  [[ -n "$t" && "$t" != "0.000000" ]] || die "missing or zero timing"
  printf '%s\n' "$out" > "$OUT/logs/${round}_${variant}.log"
  [[ -n "$t" ]] && echo "$round,$order,$variant,$t" >> "$CSV"
  printf '%s' "$t"
}

for (( r=1; r<=ROUNDS; r++ )); do
  # Alternate which arm goes first. With --shuffle the order is random; without
  # it, it strictly alternates by round parity. Either way neither variant
  # systematically occupies the "first" (cold) or "second" (warm) slot.
  if (( SHUFFLE )); then
    (( RANDOM % 2 )) && first=base || first=opt
  else
    (( r % 2 )) && first=base || first=opt
  fi

  if [[ "$first" == "base" ]]; then
    tb="$(run_one baseline  "$BASE" "$r" 1)"
    to="$(run_one optimized "$OPT"  "$r" 2)"
  else
    to="$(run_one optimized "$OPT"  "$r" 1)"
    tb="$(run_one baseline  "$BASE" "$r" 2)"
  fi
  printf '  round %2d (%s first): base=%-10s opt=%-10s\n' "$r" "$first" "${tb:-fail}" "${to:-fail}"
done

hdr "analysis"
"$PY_REL" - "$CSV" "$LOOPS_FIXED" "$BENCH" <<'PYEOF' | tee "$OUT/summary.txt"
import csv, random, statistics, sys

path, loops, bench = sys.argv[1], int(sys.argv[2]), sys.argv[3]
rows = list(csv.DictReader(open(path)))
b = [float(r["total_sec"]) / loops for r in rows if r["variant"] == "baseline"]
o = [float(r["total_sec"]) / loops for r in rows if r["variant"] == "optimized"]

W = 72
print("=" * W)
print(f" INTERLEAVED A/B TIMING — {bench}".center(W))
print("=" * W)
print()
print(f"Design: processes alternated A/B/A/B, {loops} unit(s) of work each,")
print("        identical loop count for both arms, no profiler attached.")
print("        This reduces confounding by slow host drift; it does not eliminate it.\n        Separate")
print("        sequential baseline-then-optimized blocks cannot do.")
print()

if len(b) < 3 or len(o) < 3:
    print(f"!! too few samples (baseline {len(b)}, optimized {len(o)})")
    raise SystemExit(1)

def st(v):
    m = statistics.mean(v); sd = statistics.stdev(v) if len(v) > 1 else 0.0
    return m, statistics.median(v), sd, (sd / m * 100 if m else 0.0)

mb, medb, sdb, rsb = st(b)
mo, medo, sdo, rso = st(o)
print(f"{'':<14}{'n':>5}{'median/unit':>15}{'mean/unit':>13}{'rel sd':>10}")
print("-" * W)
print(f"{'baseline':<14}{len(b):>5}{medb:>15.6f}{mb:>13.6f}{rsb:>9.2f}%")
print(f"{'optimized':<14}{len(o):>5}{medo:>15.6f}{mo:>13.6f}{rso:>9.2f}%")
print()

speedup = medb / medo
timered = (1 - medo / medb) * 100

# Bootstrap CI: resample both arms with replacement and recompute. This makes no
# normality assumption, which matters because timing distributions are
# right-skewed (a run can be slowed by interference, never sped up).
random.seed(12345)
paired_rows = {}
for row in rows:
    paired_rows.setdefault(row["round"], {})[row["variant"]] = float(row["total_sec"]) / loops
pairs = [(v["baseline"], v["optimized"]) for v in paired_rows.values()]
boots = []
for _ in range(20000):
    draw = random.choices(pairs, k=len(pairs))
    rb = statistics.median(p[0] for p in draw)
    ro = statistics.median(p[1] for p in draw)
    boots.append((1 - ro / rb) * 100)
boots.sort()
lo = boots[int(0.025 * len(boots))]
hi = boots[int(0.975 * len(boots))]

print("=" * W)
print(f"  SPEEDUP        : {speedup:.4f}x")
print(f"  TIME REDUCTION : {timered:.2f} %")
print(f"  95% paired boot  : [{lo:.2f} %, {hi:.2f} %]   (20000 round resamples; assumes independent rounds)")
print(f"  PROJECT BAR    : 7.00 % time reduction")
print()

# The decision rule: the ENTIRE interval must clear the bar. A point estimate
# above 7% with a CI straddling it does not establish the result.
if lo >= 7.0:
    print("  VERDICT        : PASS — the whole 95% CI is above the 7% bar.")
elif timered >= 7.0:
    print("  VERDICT        : INCONCLUSIVE — point estimate clears the bar but")
    print("                   the CI straddles it. Collect more rounds.")
else:
    print("  VERDICT        : BELOW BAR.")
print("=" * W)
print()

# Paired analysis: nearby processes may share slow environmental effects.
# Pairing reduces some drift sensitivity; it cannot guarantee equal state.
rounds = {}
for r in rows:
    rounds.setdefault(r["round"], {})[r["variant"]] = float(r["total_sec"]) / loops
paired = [(v["baseline"] - v["optimized"]) / v["baseline"] * 100
          for v in rounds.values() if "baseline" in v and "optimized" in v]
if len(paired) >= 3:
    pm = statistics.mean(paired); psd = statistics.stdev(paired)
    print(f"Paired within-round analysis (n={len(paired)}):")
    print(f"  mean time reduction = {pm:.2f} %  (sd {psd:.2f})")
    print(f"  per-round range     = [{min(paired):.2f} %, {max(paired):.2f} %]")
    print("  All rounds agree in sign."
          if all(p > 0 for p in paired) else
          "  WARNING: some rounds show the optimized variant SLOWER.")
PYEOF

ok "output: $OUT"
printf '  %-18s %s\n' "summary:" "$OUT/summary.txt"
printf '  %-18s %s\n' "raw samples:" "$OUT/samples.csv"
