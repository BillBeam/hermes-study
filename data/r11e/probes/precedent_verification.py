#!/usr/bin/env python3
"""R11E · 回源核对本轮引用的仓库历史统计(验收项 12),并记录一次更正。

CLAUDE.md 要求:凡引用仓库历史的统计数字,须给出**可重跑计数命令**、**口径定义**,
以及**该命令所在仓库的可达提交总数**(分母)。本脚本是那三样的落库形式。

## 被核对的三条

  A. 「跨章原则清单曾实测 15/17 失同步」 —— **未通过**。R11E 开工时把它写进了
     CLAUDE.md 与 `scripts/build_reading_layer.py` 的模块 docstring,当作立关卡的依据之一;
     回源核对**在本仓库里找不到出处**,已就地更正。全语料唯一的 `15/17` 是
     `notes/r11b-raw-chapter-anchors.md:617` 的 `H-R11B-C-a`,量的是 `chapters/r3`
     的**引用 UNCHECKED 占比**(15/17 = 88.2%),与「原则清单失同步」不是同一件事。
  B. 「成品章里未同步的过期结论 4 条」 —— **通过**,出处
     `notes/r11c-raw-pre-binding-inventory.md:35`。
  C. 「`chapters/r1` 的分层手抄数字修过一次、六轮后原样复发」 —— **通过**,同上 §4.1。

## 口径

  - **语料**:本仓库 `*.md`,即 `chapters/ notes/ reports/ reviews/ reading/ data/` 与仓库根
    (含 `CLAUDE.md` 自己)。本脚本**排除 `reading/` 与本轮 R11E 自己的产物**再报一次,
    因为「写一份点名清单就会改变下一次的读数」是本项目已经栽过的坑
    (CLAUDE.md「搜过没有类测量必须报两个读数」)。
  - **命中**:字面量 `15/17` 或 `15 / 17`。
  - **分母**:`git rev-list --count HEAD` —— 本命令所在仓库从 HEAD 可达的提交总数。
    没有它,「全语料只有一处」这种话没有基准:浅克隆会给出同样自信、但完全不同的答案。

用法:
    python3 data/r11e/probes/precedent_verification.py
"""
import re
import subprocess
import sys
from pathlib import Path

STUDY = Path(__file__).resolve().parents[3]
PATTERN = re.compile(r"15\s*/\s*17")
# 本轮自己的产物:它们会因为**报告了这件事**而命中,那是污染不是证据。
SELF = ("reading/", "data/r11e/", "reports/round-11e-", "notes/r11e-")


def md_files():
    for p in sorted(STUDY.rglob("*.md")):
        rel = p.relative_to(STUDY).as_posix()
        if rel.startswith(".git/"):
            continue
        yield rel, p


def scan():
    raw, filtered = [], []
    for rel, p in md_files():
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for i, line in enumerate(text.split("\n"), 1):
            if PATTERN.search(line):
                raw.append((rel, i, line.strip()[:110]))
                if not rel.startswith(SELF) and rel != "CLAUDE.md":
                    filtered.append((rel, i, line.strip()[:110]))
    return raw, filtered


def main():
    total_commits = subprocess.run(
        ["git", "-C", str(STUDY), "rev-list", "--count", "HEAD"],
        capture_output=True, text=True, check=True).stdout.strip()
    n_files = sum(1 for _ in md_files())

    raw, filtered = scan()
    print(f"语料:{n_files} 份 *.md;仓库可达提交总数(分母):{total_commits}")
    print(f"字面量 15/17 命中:朴素读数 {len(raw)} 处 / 剔除本轮产物与 CLAUDE.md 后 {len(filtered)} 处")
    for rel, i, line in filtered:
        print(f"  {rel}:{i}  {line}")

    ok = True
    # A:那个数不该有一个「原则清单失同步」的出处
    bad = [r for r in filtered if "原则" in r[2] and ("同步" in r[2] or "漂" in r[2])]
    if bad:
        print("  [BAD] 竟然找到了「原则清单失同步」的出处,本脚本的结论需要重写:")
        for b in bad:
            print("   ", b)
        ok = False
    else:
        print("A 结论成立:全语料没有任何一处把 15/17 用作「跨章原则清单失同步」。")

    # B / C:两条通过的出处必须仍在原位
    for rel, needle, label in (
        ("notes/r11c-raw-pre-binding-inventory.md", "成品章里未同步的过期结论确认 4 条", "B"),
        ("notes/r11c-raw-pre-binding-inventory.md", "于是六轮后原样复发", "C"),
    ):
        text = (STUDY / rel).read_text(encoding="utf-8")
        hit = needle in text
        print(f"{label} 出处 {'在位' if hit else '**不在位**'}:{rel} 含「{needle}」")
        ok &= hit

    print("OK" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
