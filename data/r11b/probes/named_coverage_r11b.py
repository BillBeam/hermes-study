#!/usr/bin/env python3
"""点名覆盖率(R11B 版):同时报「剔除承载清单的文件」与「不剔除」两个读数。

这个测量对「报告它」这个动作**不幂等**:判据是「该路径字符串在语料里出现过没有」,
而为了履行"逐个点名"把清单写进底稿,**点名这个动作本身就把被点名文件变成了已命中**。
R9D 差一点把污染后的 18/0 当成成绩(是"这个数好得不合常理"这一下犹豫拦住的,
不是任何脚本)。H-R9D-e / H-R10B-b 已就此入册:**两个读数都报,不合并。**

默认剔除的是**只列清单、不含可溯源断言**的文件:R9D 的积压清单那一份。
本轮各片的底稿**不剔除**——它们引用这些路径正是因为真的读了,那是要测的东西。

    python3 data/r11b/probes/named_coverage_r11b.py [--list] [--exclude a.md,b.md]
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(subprocess.run(["git", "-C", str(Path(__file__).resolve().parent),
                            "rev-parse", "--show-toplevel"],
                           capture_output=True, check=True).stdout.decode().strip())
SCOPE = ("notes", "chapters", "reports")
# 只列清单、不含可溯源断言的文件。加一份到这里之前先问:它是"研究了这些文件"
# 还是"抄了一遍文件名"?只有后者才该剔除。
DEFAULT_EXCLUDE = ("r9d-01-scope-and-l1-closeout.md",)


def ledger_l1_deep_read():
    rows = []
    with open(ROOT / "data" / "ledger.tsv", encoding="utf-8") as fh:
        fh.readline()
        for line in fh:
            p = line.rstrip("\n").rstrip("\r").split("\t")
            if len(p) >= 6 and p[3].strip() == "L1" and p[5].strip().endswith("-deep-read"):
                rows.append({"path": p[0], "lines": int(p[2]), "round": p[4].strip()})
    return rows


def corpus(exclude: set[str]) -> str:
    return "\n".join(
        f.read_text(encoding="utf-8", errors="replace")
        for d in SCOPE for f in sorted((ROOT / d).glob("*.md"))
        if f.name not in exclude)


def measure(rows, text):
    pm = [r for r in rows if r["path"] not in text]
    nm = [r for r in pm if Path(r["path"]).name not in text]
    return pm, nm


def main(argv: list[str]) -> int:
    extra = argv[argv.index("--exclude") + 1].split(",") if "--exclude" in argv else []
    exclude = set(DEFAULT_EXCLUDE) | {e.strip() for e in extra if e.strip()}
    rows = ledger_l1_deep_read()

    for label, ex in (("不剔除(朴素)", set()), ("剔除承载清单(以此为准)", exclude)):
        pm, nm = measure(rows, corpus(ex))
        print(f"{label}: 全路径零命中 {len(pm)} 文件 / {sum(r['lines'] for r in pm)} 行;"
              f"裸名零命中 {len(nm)} 文件 / {sum(r['lines'] for r in nm)} 行")
    print(f"被测 L1(status=*-deep-read)= {len(rows)} 个;剔除的文件:{sorted(exclude)}")

    if "--list" in argv:
        pm, nm = measure(rows, corpus(exclude))
        names = {r["path"] for r in nm}
        for r in sorted(pm, key=lambda x: x["path"]):
            print(f"  {r['path']}\t{r['lines']}\t{r['round']}"
                  f"{'  [连裸名也零命中]' if r['path'] in names else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
