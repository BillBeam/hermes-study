#!/usr/bin/env python3
"""R11C 片 C 工作台:把「跑不起来的未配对 verify 块」连同**行号与整块原文**列出来。

与 `data/r11c/probes/runnability_census.py` 的关系:同一套判据(都从关卡 import),
但普查报的是**计数**,而修块需要知道**块在文件的第几行、正文逐字是什么**。
普查的 TSV 把命令压成一行、截到 150 字符,照着它改会改错块。

    python3 data/r11c/c-bad-evidence-scan.py            # 计数 + 一行摘要
    python3 data/r11c/c-bad-evidence-scan.py --json OUT # 整块原文与行号写 JSON
    python3 data/r11c/c-bad-evidence-scan.py --files a.md b.md   # 只扫指定文件

默认扫 `data/r11c/slice-c-files.txt` 里那 31 个文件(片 C 的可改面)。
不依赖会话专属路径:仓库根从本文件位置推出。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from verify_evidence_commands import (  # noqa: E402
    PAIR, ANY_VERIFY, TIMEOUT, is_mutating, baseline_porcelain,
)
sys.path.insert(0, str(ROOT / "data" / "r11c" / "probes"))
from runnability_census import classify_failure  # noqa: E402


def scan(files: list[Path]) -> list[dict]:
    out = []
    for p in files:
        text = p.read_text(encoding="utf-8", errors="replace")
        paired = {m.group("cmd") for m in PAIR.finditer(text)}
        for m in ANY_VERIFY.finditer(text):
            body = m.group(0)[len("```verify\n"):-3]
            if body in paired:
                continue
            cmd = body.strip()
            if not cmd:
                continue
            line = text[:m.start()].count("\n") + 1
            rec = {"file": p.relative_to(ROOT).as_posix(), "line": line,
                   "mutating": is_mutating(cmd), "body": body}
            if not rec["mutating"]:
                try:
                    r = subprocess.run(["bash", "-c", cmd], cwd=ROOT,
                                       capture_output=True, text=True,
                                       timeout=TIMEOUT)
                    rec["rc"] = r.returncode
                    rec["stderr"] = r.stderr.strip()
                    rec["stdout"] = r.stdout
                    rec["kind"] = ("OK" if r.returncode == 0
                                   else "SILENT" if not r.stderr.strip()
                                   else classify_failure(r.returncode, r.stderr))
                except subprocess.TimeoutExpired:
                    rec["rc"], rec["stderr"], rec["stdout"] = -1, "", ""
                    rec["kind"] = "D-timeout"
            else:
                rec["kind"] = "MUTATING"
            out.append(rec)
    return out


def main(argv: list[str]) -> int:
    if "--files" in argv:
        i = argv.index("--files")
        files = [ROOT / a for a in argv[i + 1:] if not a.startswith("--")]
    else:
        listing = (ROOT / "data/r11c/slice-c-files.txt").read_text().split()
        files = [ROOT / f for f in listing]
    before = baseline_porcelain()
    recs = scan(files)
    after = baseline_porcelain()
    if "--json" in argv:
        dest = Path(argv[argv.index("--json") + 1])
        dest.write_text(json.dumps(recs, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    counts: dict[str, int] = {}
    for r in recs:
        counts[r["kind"]] = counts.get(r["kind"], 0) + 1
    for r in recs:
        if r["kind"] not in ("OK", "SILENT", "MUTATING"):
            print(f'{r["file"]}:{r["line"]}\t{r["kind"]}\t'
                  f'{(r.get("stderr") or "").splitlines()[-1][:100] if r.get("stderr") else ""}')
    print("blocks=" + str(len(recs)) + " "
          + " ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    print(f"baseline_porcelain_changed={before != after}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
