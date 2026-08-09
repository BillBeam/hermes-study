#!/usr/bin/env python3
"""Anchors pointing at EXTENSIONLESS files — the residue H-R10-a's fix cannot reach.

R10B widened `verify_citations.py`'s extension whitelist (H-R10-a). That fix is
structurally incapable of covering `.gitignore:3`, `Dockerfile:12`, `Makefile:40`
and friends: they have no extension to whitelist. Such an anchor is in exactly
the state H-R10-a described as "more hidden than UNCHECKED" — not verified, and
not counted either.

Widening the regex to accept any bare word is NOT the fix: `word:number` occurs
constantly in prose. The fix, when someone takes it, is an explicit list of
extensionless filenames — declared, not sniffed, same principle as
NON_SOURCE_LANGS and the ccTLD guard.

This probe measures the backlog so the handover is a number, not a worry. It
counts only anchors that RESOLVE against the baseline, so it cannot inflate
itself with prose that merely looks like `name:12`.

    python3 data/r10b/probes/extless_anchor_scan.py [baseline_repo]
"""
import re
import sys
from pathlib import Path

STUDY = Path(__file__).resolve().parents[3]
_pos = [a for a in sys.argv[1:] if not a.startswith("-")]
REPO = Path(_pos[0] if _pos else "/home/user/hermes-agent")
sys.path.insert(0, str(STUDY / "scripts"))
from verify_citations import CITE  # noqa: E402

# Extensionless files that really exist in trees like this one. Explicit list,
# because the alternative — "any bare word followed by :digits" — matches prose.
KNOWN = {
    ".gitignore", ".gitattributes", ".dockerignore", ".editorconfig",
    ".npmrc", ".nvmrc", ".env", "Dockerfile", "Makefile", "LICENSE", "CODEOWNERS",
}

TOKEN = re.compile(
    r"(?<![A-Za-z0-9_./-])((?:[A-Za-z0-9_.-]+/)*(?:\.?[A-Za-z][A-Za-z0-9_-]*)):(\d+)\b"
)


def main() -> None:
    # Measurement pollution (the general form of H-R9D-e): a probe that scans the
    # corpus is polluted by the round that WRITES UP the probe -- this file's own
    # ruling quotes `apps/bootstrap-installer/.gitignore:1-3`, which the census
    # then counts. Third instance in R10B alone (named_coverage, cite_ext_scan,
    # here), so it is a property of corpus-scanning probes, not a one-off.
    # Default: exclude this round's write-up by prefix; --no-exclude for the raw.
    prefixes = ("r10b-", "round-10b-")
    raw_mode = "--no-exclude" in sys.argv
    print("corpus excludes: " + ("(none, --no-exclude)" if raw_mode else str(prefixes)))

    hits: dict[str, tuple[int, set]] = {}
    for d in ("chapters", "notes", "reports", "reviews"):
        for f in sorted((STUDY / d).glob("*.md")):
            if not raw_mode and f.name.startswith(prefixes):
                continue
            for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
                for m in TOKEN.finditer(line):
                    path = m.group(1)
                    if CITE.search(m.group(0)):
                        continue  # already a recognised anchor
                    if path.rsplit("/", 1)[-1] not in KNOWN:
                        continue
                    if not (REPO / path).is_file():
                        continue
                    n, files = hits.get(path, (0, set()))
                    hits[path] = (n + 1, files | {f.name})

    print("resolvable extensionless anchors NOT recognised by the whitelist:")
    for path, (n, files) in sorted(hits.items()):
        where = ", ".join(sorted(files)) if len(files) <= 3 else f"{len(files)} 个文件"
        print(f"  x{n}  {path}   in: {where}")
    print(f"total occurrences: {sum(v[0] for v in hits.values())} "
          f" distinct paths: {len(hits)}")


if __name__ == "__main__":
    main()
