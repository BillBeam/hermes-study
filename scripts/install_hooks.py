#!/usr/bin/env python3
"""Install this repo's git hooks. Idempotent; safe to run every session.

`.git/hooks/` is not versioned, so a hook is not a mechanism until something
mandatory installs it. `verify_ledger.py` — the one script CLAUDE.md tells every
session to run before anything else — imports `ensure_hooks()` from here and
installs on the spot. A hook that a human has to remember to install would just
be 自觉 wearing a shell script.

The hook body is stamped with HOOK_VERSION. If the installed hook carries a
different stamp it is overwritten and the fact is printed; if it carries no stamp
at all it was written by someone else and is left alone with a loud warning
rather than silently clobbered.

Usage: python3 scripts/install_hooks.py [repo_root]
"""
import subprocess
import sys
from pathlib import Path

HOOK_VERSION = "r11b.1"
STAMP = f"# hermes-study-hook-version: {HOOK_VERSION}"

PRE_COMMIT = f"""#!/bin/sh
{STAMP}
# Installed by scripts/install_hooks.py — do not edit by hand.
# Refuses commits containing files under an OPEN claim in data/inflight/,
# i.e. files whose producer has not signalled completion (CLAUDE.md).
root=$(git rev-parse --show-toplevel) || exit 1
exec python3 "$root/scripts/verify_commit_safety.py" --staged
"""


def ensure_hooks(root: Path) -> list[str]:
    """Install/refresh hooks. Returns human-readable notes about what happened."""
    notes: list[str] = []
    try:
        hooks_dir = Path(subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--git-path", "hooks"],
            capture_output=True, check=True).stdout.decode().strip())
    except subprocess.CalledProcessError:
        return ["hooks: not a git repo, skipped"]
    if not hooks_dir.is_absolute():
        hooks_dir = root / hooks_dir
    hooks_dir.mkdir(parents=True, exist_ok=True)

    target = hooks_dir / "pre-commit"
    if target.exists():
        body = target.read_text(encoding="utf-8", errors="replace")
        if STAMP in body:
            return notes  # current, nothing to say
        if "hermes-study-hook-version:" in body:
            target.write_text(PRE_COMMIT, encoding="utf-8")
            target.chmod(0o755)
            notes.append(f"hooks: refreshed pre-commit to {HOOK_VERSION}")
            return notes
        notes.append(
            "hooks: WARNING — .git/hooks/pre-commit exists but was not written by "
            "install_hooks.py; left untouched. The in-flight commit guard is NOT "
            "active. Inspect it, then re-run scripts/install_hooks.py.")
        return notes

    target.write_text(PRE_COMMIT, encoding="utf-8")
    target.chmod(0o755)
    notes.append(f"hooks: installed pre-commit ({HOOK_VERSION})")
    return notes


def main(argv: list[str]) -> int:
    root = Path(argv[0]) if argv else Path(subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, check=True).stdout.decode().strip())
    notes = ensure_hooks(root)
    for n in notes:
        print(n)
    if not notes:
        print(f"hooks: pre-commit already at {HOOK_VERSION}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
