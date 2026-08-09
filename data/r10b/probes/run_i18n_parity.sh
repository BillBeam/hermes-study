#!/usr/bin/env bash
# Mainline cross-check of slice I's key-parity claim. Runs in the node copy,
# never in the baseline.
set -euo pipefail
STUDY=$(cd "$(dirname "$0")/../../.." && pwd)
ENVDIR=${ENVDIR:-/home/user/r10b-ts/hermes-agent}
test -d "$ENVDIR/node_modules" || { echo "run ts_test_env.sh first"; exit 1; }
cp "$STUDY/data/r10b/probes/i18n_leaf_parity.test.ts" \
   "$ENVDIR/apps/desktop/src/i18n_leaf_parity.test.ts"
cd "$ENVDIR/apps/desktop"
npx vitest run --project ui src/i18n_leaf_parity.test.ts --reporter=default 2>&1 \
  | grep -E "LEAF_COUNTS|DIFF_VS_EN|LOCALE_OPTIONS=|Test Files|Tests  |FAIL"
