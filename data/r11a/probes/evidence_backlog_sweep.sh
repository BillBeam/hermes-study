#!/usr/bin/env bash
# Complete the evidence-command backlog census that a single gate run cannot.
#
# `scripts/verify_evidence_commands.py` runs each ```verify command with a
# 900-second per-command cap and does NOT catch subprocess.TimeoutExpired. One
# historical note (notes/r9d-*) pins the output of a full pytest selection; that
# command exceeds the cap, the exception propagates, and the whole run dies
# partway through. Everything after it is simply never examined — so the diff
# count from such a run is a LOWER BOUND, not a census.
#
# This wrapper runs the gate one file at a time under an external per-file
# bound, so a single pathological command costs one file instead of the rest of
# the corpus. Files that exceed the bound are reported by name rather than
# silently dropped.
#
#   bash data/r11a/probes/evidence_backlog_sweep.sh [per_file_seconds]
#
# Writes data/r11a/measurements/evidence-backlog-sweep.txt
set -uo pipefail
cd "$(dirname "$0")/../../.." || exit 1
BOUND=${1:-150}
OUT=data/r11a/measurements/evidence-backlog-sweep.txt
: > "$OUT"

paired=0; unpaired=0; differing=0; timedout=0; files=0
for f in notes/*.md reports/*.md chapters/*.md reviews/*.md; do
  [ -f "$f" ] || continue
  # Skip files with no verify block at all — nothing to run, and skipping them
  # keeps the sweep's wall time proportional to the actual evidence surface.
  grep -q '```verify' "$f" || continue
  files=$((files + 1))
  res=$(timeout "$BOUND" python3 scripts/verify_evidence_commands.py "$f" 2>&1)
  rc=$?
  if [ $rc -eq 124 ]; then
    timedout=$((timedout + 1))
    echo "[TIMEOUT >${BOUND}s] $f" >> "$OUT"
    continue
  fi
  line=$(printf '%s\n' "$res" | grep -E '^verify-blocks paired=' | tail -1)
  # Anchor the whole line and capture all three in one go. The first draft used
  # three separate `.*paired=\([0-9]*\).*` expressions; `.*` is greedy, so the
  # "paired" one matched the LAST occurrence of `paired=` on the line — which is
  # the tail of `unpaired=`. It silently reported unpaired as paired, i.e. the
  # measurement command itself was the failure mode this whole gate exists to
  # catch. Anchoring removes the ambiguity instead of relying on luck.
  read -r p u d <<<"$(printf '%s' "$line" | sed -n \
    's/^verify-blocks[[:space:]]*paired=\([0-9]*\)[[:space:]]*unpaired=\([0-9]*\)[[:space:]]*differing=\([0-9]*\).*/\1 \2 \3/p')"
  paired=$((paired + ${p:-0})); unpaired=$((unpaired + ${u:-0}))
  differing=$((differing + ${d:-0}))
  if [ "${d:-0}" -gt 0 ]; then
    echo "[DIFF x${d}] $f" >> "$OUT"
  fi
done

{
  echo
  echo "files with >=1 verify block : $files"
  echo "paired                      : $paired"
  echo "unpaired                    : $unpaired"
  echo "differing                   : $differing"
  echo "files exceeding ${BOUND}s   : $timedout"
} >> "$OUT"
cat "$OUT"
