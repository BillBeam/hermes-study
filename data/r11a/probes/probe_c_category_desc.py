#!/usr/bin/env python3
"""End-to-end check: which bundled skill categories get a description line in
the system-prompt skill index, and which are silently dropped.

Runs the real chain in a throwaway HERMES_HOME (never touches the baseline):

    tools.skills_sync.sync_skills()          # skills/ -> $HERMES_HOME/skills/
    agent.prompt_builder.build_skills_system_prompt()

`build_skills_system_prompt` reads each category's DESCRIPTION.md through
`parse_frontmatter` and drops the file when the YAML frontmatter has no
`description` key (agent/prompt_builder.py:1740-1742). A DESCRIPTION.md written
as plain prose therefore produces no error, no log line at default level, and
no description in the index.

Must be run from the baseline checkout with HERMES_HOME pointing somewhere
disposable, e.g.

    cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 \
        HERMES_HOME=$(mktemp -d) /home/user/hermes-venv/bin/python \
        /home/user/hermes-study/data/r11a/probes/probe_c_category_desc.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.getcwd())


def main() -> None:
    from tools.skills_sync import sync_skills
    from agent.prompt_builder import build_skills_system_prompt
    from agent.skill_utils import parse_frontmatter

    sync_skills(quiet=True)
    out = build_skills_system_prompt()

    described = set()
    for line in out.splitlines():
        stripped = line.strip()
        if line.startswith("  ") and ":" in stripped and not stripped.startswith("-"):
            described.add(stripped.split(":", 1)[0])

    bundled = sorted(p for p in Path("skills").rglob("DESCRIPTION.md"))
    missing_fm = []
    for p in bundled:
        fm, _ = parse_frontmatter(p.read_text(encoding="utf-8"))
        if not fm.get("description"):
            missing_fm.append(str(p))

    print(f"bundled DESCRIPTION.md files            : {len(bundled)}")
    print(f"  without a frontmatter 'description'   : {len(missing_fm)}")
    for m in missing_fm:
        cat = m[len("skills/"):-len("/DESCRIPTION.md")]
        print(f"    {m}  -> category '{cat}' in index with description: "
              f"{cat in described}")


if __name__ == "__main__":
    main()
