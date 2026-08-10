#!/usr/bin/env python3
"""全语料可跑性普查:未配对的只读 verify 块里,有多少条根本跑不起来。

与 `scripts/verify_evidence_commands.py` 的关系:**同一套判据,不同的作用面**。
关卡的强制范围是 `chapters/` + 当轮 notes/reports(与 verify_citations.py 同口径);
本探针把同一条判据铺到全语料,用来报「历史积压还剩多少」。判据从关卡 import,
不另起口径 —— R11B 量配对率时踩过的正是这个坑:同一个指标两个口径,
两个数都对,而读者不知道看的是哪一个。

只跑未配对块中的非 MUTATING 型(关卡怎么分类,这里就怎么分类)。已配对块不跑:
它们归比对腿管,而重跑全语料的已配对 MUTATING 块会往基线里装包。

    python3 data/r11c/probes/runnability_census.py            # 计数
    python3 data/r11c/probes/runnability_census.py --list     # 逐条明细(TSV)

不依赖会话专属路径:仓库根从本文件位置推出。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(subprocess.run(["git", "-C", str(Path(__file__).resolve().parent),
                            "rev-parse", "--show-toplevel"],
                           capture_output=True, check=True).stdout.decode().strip())
sys.path.insert(0, str(ROOT / "scripts"))
from verify_evidence_commands import (  # noqa: E402
    PAIR, ANY_VERIFY, TIMEOUT, is_mutating, baseline_porcelain,
)

SCOPE = ("notes", "chapters", "reports", "reviews", "data")


def classify_failure(rc: int, err: str) -> str:
    """把一次失败归到 R11B 手工分的那三类里,判据只用 stderr 的形状。

    R11B 是人工读 stderr 分的 A/B/E;这里给出机械版本,好让「63 是哪 63」
    每轮可重算而不是每轮重读一遍。归不进三类的记 OTHER 而不是硬塞。
    """
    last = err.strip().splitlines()[-1] if err.strip() else ""
    low = last.lower()
    if "no such file or directory" in low or "cannot access" in low:
        return "B-deadpath"
    if ("command not found" in low or "syntax error near" in low
            or "unexpected token" in low or "unexpected end of file" in low):
        return "A-spliced"
    if any(k in last for k in ("Error", "error:", "Traceback", "Exception",
                               "Node.js v")):
        return "E-runtime"
    return "OTHER"


def main(argv: list[str]) -> int:
    listing = "--list" in argv
    before = baseline_porcelain()
    counts: dict[str, int] = {}
    ran = mut = silent = ok = 0
    rows = []
    for d in SCOPE:
        for p in sorted((ROOT / d).rglob("*.md")):
            text = p.read_text(encoding="utf-8", errors="replace")
            paired = {m.group("cmd") for m in PAIR.finditer(text)}
            for m in ANY_VERIFY.finditer(text):
                body = m.group(0)[len("```verify\n"):-3]
                if body in paired:
                    continue
                cmd = body.strip()
                if not cmd:
                    continue
                if is_mutating(cmd):
                    mut += 1
                    continue
                ran += 1
                try:
                    r = subprocess.run(["bash", "-c", cmd], cwd=ROOT,
                                       capture_output=True, text=True,
                                       timeout=TIMEOUT)
                except subprocess.TimeoutExpired:
                    counts["D-timeout"] = counts.get("D-timeout", 0) + 1
                    rows.append((p.relative_to(ROOT).as_posix(), "D-timeout",
                                 "", " ".join(cmd.split())[:150]))
                    continue
                if r.returncode == 0:
                    ok += 1
                    continue
                if not r.stderr.strip():
                    silent += 1          # C 类:正当性未判,不计入坏证据
                    continue
                kind = classify_failure(r.returncode, r.stderr)
                counts[kind] = counts.get(kind, 0) + 1
                rows.append((p.relative_to(ROOT).as_posix(), kind,
                             r.stderr.strip().splitlines()[-1][:110],
                             " ".join(cmd.split())[:150]))
    after = baseline_porcelain()
    if listing:
        for row in rows:
            print("\t".join(row))
    bad = sum(counts.values())
    print(f"readonly_unpaired={ran} exit0={ok} "
          f"silent_exit1={silent} bad={bad} skipped_mutating={mut}")
    print("bad_by_kind=" + " ".join(f"{k}={v}" for k, v in sorted(counts.items()))
          if counts else "bad_by_kind=(none)")
    print(f"baseline_porcelain_changed={before != after}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
