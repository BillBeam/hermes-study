#!/usr/bin/env python3
"""Verify the coverage ledger against the baseline checkout.

Checks:
 1. The checkout is at the baseline commit AND the working tree is pristine.
 2. Every git-tracked file in the baseline appears in the ledger exactly once.
 3. No extra files in the ledger.
 4. Ledger line counts match a fresh recount (same rule as inventory.py).
 5. Sum of per-layer lines == total text lines of the whole repo.

It also installs this repo's git hooks (R11B). That is not a ledger concern, but
it is the only place CLAUDE.md guarantees gets run at the start of every session,
and the in-flight commit guard is worthless unless something mandatory installs
it — see scripts/install_hooks.py.

Check 1's second half was added in R8A after a real incident: a subagent ran an
npm operation inside the baseline checkout, which rewrote package-lock.json
(npm re-resolved dependencies and stamped `"peer": true` onto ~30 entries). The
line-count check caught it only incidentally, and only because that file happens
to be in the ledger — a modification to any file whose line count did not change
would have passed silently and quietly invalidated every `path:line` citation
made afterwards. The baseline is the fixed point this whole project cites
against, so "is it still pristine?" deserves to be asserted directly rather than
inferred. Restore with `git -C <repo> checkout -- .` and re-run.

Usage: python3 scripts/verify_ledger.py /path/to/hermes-agent data/ledger.tsv
Exit 0 = ledger is total and consistent.
"""
import csv
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from inventory import count_lines, is_text  # noqa: E402
from install_hooks import ensure_hooks  # noqa: E402

BASELINE_SHA = "863e31318553cda8ad61df681d08175364d4164b"


def main(repo: str, ledger_path: str) -> None:
    head = subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"],
                          capture_output=True, check=True).stdout.decode().strip()
    if head != BASELINE_SHA:
        sys.exit(f"FAIL: checkout at {head}, expected baseline {BASELINE_SHA}")

    # The baseline must be byte-for-byte pristine: every `path:line @ 863e313`
    # citation in this repo is only meaningful against an unmodified tree.
    dirty = subprocess.run(["git", "-C", repo, "status", "--porcelain"],
                           capture_output=True, check=True).stdout.decode().strip()
    if dirty:
        sys.exit(
            "FAIL: baseline checkout is NOT pristine — citations cannot be trusted.\n"
            + "\n".join(f"  {ln}" for ln in dirty.splitlines()[:20])
            + f"\n\nRestore with: git -C {repo} checkout -- . && "
              f"git -C {repo} clean -fd"
        )

    tracked = set(subprocess.run(["git", "-C", repo, "ls-files", "-z"],
                                 capture_output=True, check=True)
                  .stdout.decode().split("\0")) - {""}

    ledger: dict[str, tuple[str, int, str]] = {}
    layer_lines: dict[str, int] = {}
    layer_files: dict[str, int] = {}
    with open(ledger_path) as f:
        for row in csv.DictReader(f, delimiter="\t"):
            p = row["path"]
            if p in ledger:
                sys.exit(f"FAIL: duplicate ledger entry {p}")
            ledger[p] = (row["kind"], int(row["lines"]), row["layer"])
            layer_lines[row["layer"]] = layer_lines.get(row["layer"], 0) + int(row["lines"])
            layer_files[row["layer"]] = layer_files.get(row["layer"], 0) + 1

    missing = tracked - set(ledger)
    extra = set(ledger) - tracked
    if missing:
        sys.exit(f"FAIL: {len(missing)} tracked files missing from ledger, e.g. {sorted(missing)[:5]}")
    if extra:
        sys.exit(f"FAIL: {len(extra)} ledger entries not tracked, e.g. {sorted(extra)[:5]}")

    root = Path(repo)
    recount_total = 0
    mismatches = []
    for p, (kind, lines, _layer) in ledger.items():
        fp = root / p
        if fp.is_symlink():
            actual = 0
        else:
            data = fp.read_bytes()
            actual = count_lines(data) if is_text(data) else 0
        recount_total += actual
        if actual != lines:
            mismatches.append((p, lines, actual))
    if mismatches:
        sys.exit(f"FAIL: {len(mismatches)} line-count mismatches, e.g. {mismatches[:5]}")

    ledger_total = sum(layer_lines.values())
    if ledger_total != recount_total:
        sys.exit(f"FAIL: layer sum {ledger_total} != recount {recount_total}")

    print(f"OK baseline={head[:9]} files={len(ledger)} total_lines={ledger_total}")
    for layer in sorted(layer_lines):
        print(f"  {layer}: files={layer_files[layer]} lines={layer_lines[layer]}")
    print(f"  SUM == repo total: {ledger_total}")

    # R11B: install the in-flight commit guard. Piggy-backed here because this is
    # the one script every session is told to run first; a hook nobody installs
    # is not a mechanism.
    study_root = Path(__file__).resolve().parent.parent
    for note in ensure_hooks(study_root):
        print(f"  {note}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/home/user/hermes-agent",
         sys.argv[2] if len(sys.argv) > 2 else "data/ledger.tsv")
