#!/usr/bin/env bash
# Build a node test environment for apps/desktop OUTSIDE the baseline clone.
#
# The baseline is read-only and is the reference for every `path:line @ 863e313`
# citation in this project, so npm must never run inside it: npm rewrites
# package-lock.json on resolve (R8A caught exactly that). `git archive` gives a
# byte-identical export of the pinned tree to work in instead.
#
# R10 reported apps/desktop's 490 test files as un-runnable ("needs the Electron
# runtime"). apps/desktop/vitest.config.ts declares two projects and neither is
# an Electron binary: `ui` is environment 'jsdom' over src/**/*.test.{ts,tsx},
# `electron` is environment 'node' over electron/**/*.test.ts + scripts/**.test.
# Only the 25 Playwright specs under e2e/ need a real Electron+browser. This
# script exists to settle that by running them rather than arguing about it.
#
#   bash data/r10b/probes/ts_test_env.sh [dest]      # default /home/user/r10b-ts
set -euo pipefail
BASE=${BASE:-/home/user/hermes-agent}
DEST=${1:-/home/user/r10b-ts}
PIN=863e31318553cda8ad61df681d08175364d4164b

test "$(git -C "$BASE" rev-parse HEAD)" = "$PIN" || { echo "baseline not at $PIN"; exit 1; }
test -z "$(git -C "$BASE" status --porcelain)" || { echo "baseline not clean"; exit 1; }

rm -rf "$DEST"; mkdir -p "$DEST/hermes-agent"
git -C "$BASE" archive "$PIN" | tar -x -C "$DEST/hermes-agent"
cd "$DEST/hermes-agent"
echo "### exported $(find . -type f | wc -l) files to $DEST/hermes-agent"

# Electron's postinstall downloads a ~100MB binary we cannot use headless anyway;
# skip it so the install can finish. The jsdom/node projects do not need it.
export ELECTRON_SKIP_BINARY_DOWNLOAD=1
export PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
export npm_config_fund=false npm_config_audit=false
npm install --no-fund --no-audit 2>&1 | tail -20
echo "### npm packages installed: $(find node_modules -maxdepth 2 -name package.json | wc -l)"
