#!/usr/bin/env bash
# Wrapper for slice I's AST leaf-key probe.
#
# probe_i_leafkeys.mjs needs the `typescript` package, which is not installed in
# this study repo — it lives in the node copy built by ts_test_env.sh. Run
# straight from the repo root and it dies with MODULE_NOT_FOUND, i.e. the
# evidence is not reproducible by "clone and run" even though the probe itself
# is committed. This wrapper supplies NODE_PATH so it is.
set -euo pipefail
STUDY=$(cd "$(dirname "$0")/../../.." && pwd)
ENVDIR=${ENVDIR:-/home/user/r10b-ts/hermes-agent}
BASE=${BASE:-/home/user/hermes-agent}
test -d "$ENVDIR/node_modules/typescript" || {
  echo "need a checkout with typescript installed; run data/r10b/probes/ts_test_env.sh"; exit 1; }
NODE_PATH="$ENVDIR/node_modules" node "$STUDY/data/r10b/probes/probe_i_leafkeys.mjs" "$BASE" "$@"
