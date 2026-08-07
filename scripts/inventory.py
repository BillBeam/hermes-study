#!/usr/bin/env python3
"""Inventory every git-tracked file in the hermes-agent baseline checkout.

Produces a TSV: path <TAB> kind <TAB> lines <TAB> bytes
  kind: text | binary
  lines: line count for text files (0 for binary)

Usage: python3 inventory.py /path/to/hermes-agent > inventory.tsv
The line-count rule is fixed: text = file decodable as UTF-8 (errors<1%),
lines = number of '\n' plus one if file nonempty and doesn't end with '\n'.
This rule is the single source of truth for the coverage ledger totals.
"""
import subprocess
import sys
from pathlib import Path


def count_lines(data: bytes) -> int:
    if not data:
        return 0
    n = data.count(b"\n")
    if not data.endswith(b"\n"):
        n += 1
    return n


def is_text(data: bytes) -> bool:
    if b"\x00" in data[:8192]:
        return False
    try:
        data.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def main(repo: str) -> None:
    root = Path(repo)
    files = subprocess.run(
        ["git", "-C", repo, "ls-files", "-z"],
        capture_output=True, check=True,
    ).stdout.decode().split("\0")
    files = [f for f in files if f]
    total_lines = 0
    for f in sorted(files):
        p = root / f
        if p.is_symlink():
            print(f"{f}\tsymlink\t0\t0")
            continue
        data = p.read_bytes()
        if is_text(data):
            n = count_lines(data)
            total_lines += n
            print(f"{f}\ttext\t{n}\t{len(data)}")
        else:
            print(f"{f}\tbinary\t0\t{len(data)}")
    print(f"# files={len(files)} total_text_lines={total_lines}", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1])
