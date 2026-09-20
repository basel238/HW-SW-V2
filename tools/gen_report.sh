#!/usr/bin/env bash
# Assemble an evidence appendix from explicitly selected runs; never overwrite
# the authored six-section submission reports.
set -Eeuo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$HERE/../lib/common.sh"
BENCH="${1:?usage: gen_report.sh bench baseline_dir optimized_dir comparison_dir [output]}"
BASE_DIR="${2:?explicit baseline directory required}"
OPT_DIR="${3:?explicit optimized directory required}"
CMP_DIR="${4:?explicit comparison directory required}"
OUT="${5:-$CMP_DIR/evidence_appendix.txt}"
[[ "$OUT" != "$REPO_ROOT/report_${BENCH}.txt" ]] || die "refusing to overwrite authored report"
[[ ! -e "$OUT" ]] || die "output already exists: $OUT"
[[ -d "$BASE_DIR" && -d "$OPT_DIR" && -d "$CMP_DIR" ]] || die "input directory missing"
{
  echo "EVIDENCE APPENDIX — $BENCH"
  echo "Generated evidence; interpretation belongs in the authored report."
  for f in "$CMP_DIR/inputs.tsv" "$CMP_DIR/summary.txt" "$CMP_DIR/counters.txt" \
           "$BASE_DIR/manifest.txt" "$BASE_DIR/phases.tsv" "$BASE_DIR/logs/verify.log" \
           "$OPT_DIR/manifest.txt" "$OPT_DIR/phases.tsv" "$OPT_DIR/logs/verify.log"; do
    printf '\nSOURCE: %s\n' "$f"
    if [[ -s "$f" ]]; then cat "$f"; else echo "Unavailable / not collected."; fi
  done
} > "$OUT"
ok "evidence appendix: $OUT"
