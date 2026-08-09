#!/usr/bin/env bash
# Run the H-R10-f runtime probe against the pinned baseline, in the node copy
# built by data/r10b/probes/ts_test_env.sh (NEVER inside the baseline clone).
set -euo pipefail
STUDY=$(cd "$(dirname "$0")/../../.." && pwd)
ENVDIR=${ENVDIR:-/home/user/r10b-ts/hermes-agent}
test -d "$ENVDIR/node_modules" || { echo "run ts_test_env.sh first"; exit 1; }
cp "$STUDY/data/r10b/probes/h_r10f_resubscribe.test.ts" \
   "$ENVDIR/ui-tui/src/__tests__/h_r10f_resubscribe.test.ts"
cd "$ENVDIR/ui-tui"
npx vitest run src/__tests__/h_r10f_resubscribe.test.ts --reporter=default 2>&1 | tail -40
