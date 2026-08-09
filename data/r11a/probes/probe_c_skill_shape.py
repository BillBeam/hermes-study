#!/usr/bin/env python3
"""Shape checks on the bundled + optional skill trees (R11A slice C, L3).

Three numbers the 形态账 rests on, all recomputed from the baseline:

1. How many SKILL.md files each tree holds, and how many of their frontmatter
   descriptions exceed the 60-char system-prompt budget
   (`SKILL_PROMPT_DESC_LIMIT`, agent/skill_utils.py:849) and therefore render
   truncated to 57 chars + "..." in the index.
2. Whether any SKILL.md is nested inside another skill's directory — and if so
   whether the support-dir prune (`SKILL_SUPPORT_DIRS`) shields it from being
   indexed as a second, independent skill.
3. How many skills `sync_skills()` would actually copy into HERMES_HOME
   (bundled only) versus how many exist in total (bundled + optional).

Run from the baseline checkout:

    cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 \
        python3 /home/user/hermes-study/data/r11a/probes/probe_c_skill_shape.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.getcwd())

from agent.skill_utils import (  # noqa: E402
    SKILL_PROMPT_DESC_LIMIT,
    SKILL_SUPPORT_DIRS,
    is_skill_description_truncated_for_prompt,
    parse_frontmatter,
)

TREES = ("skills", "optional-skills")


def main() -> None:
    total = 0
    for root in TREES:
        files = sorted(Path(root).rglob("SKILL.md"))
        trunc = [
            p for p in files
            if is_skill_description_truncated_for_prompt(
                parse_frontmatter(p.read_text(encoding="utf-8"))[0])
        ]
        total += len(files)
        print(f"{root:16s} SKILL.md={len(files):4d}  "
              f"desc>{SKILL_PROMPT_DESC_LIMIT}chars={len(trunc):2d}")
    print(f"{'TOTAL':16s} SKILL.md={total:4d}")

    nested = 0
    for root in TREES:
        dirs = {str(p)[: -len("/SKILL.md")] for p in Path(root).rglob("SKILL.md")}
        for d in dirs:
            for other in dirs:
                if d != other and d.startswith(other + "/"):
                    seg = d[len(other) + 1:].split("/")[0]
                    nested += 1
                    print(f"  nested: {d} inside {other} "
                          f"(shielded={seg in SKILL_SUPPORT_DIRS})")
    print(f"nested SKILL.md  = {nested}")


if __name__ == "__main__":
    main()
