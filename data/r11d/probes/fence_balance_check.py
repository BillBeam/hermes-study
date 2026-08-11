#!/usr/bin/env python3
"""R11D · 围栏配平自检:一句以 ``` 开头的散文会把整份文件的后半段从检查面上抹掉。

`verify_citations.py` 与 `verify_evidence_commands.py` 都用「行首 ``` 就翻转围栏状态」
来跳过代码块。于是**任何一行只要以 ``` 开头就会翻转状态**,哪怕它是一句在**谈论**围栏的散文。
奇数个翻转 = 文件后半段被永久当成「在围栏里」= **一条锚点都不再被扫**。

本探针只回答一件事:每份文件的行首围栏标记是不是偶数个;不是的,点名。

**并案说明(主线并,案号 `H-R11D-A-a`)。** 片 A 独立撞见同一个缺陷,写了
`data/r11d/probes/fence_parity_r11d.py`,判据不同:它**逐行判**「宽口径认它是围栏、
但它明显是散文」(含中日韩字符,或反引号串之后还有反引号串)。两条判据**不等价**,
并案保留的是判据本身,不是其中一份:

  - 本探针(奇偶计数)抓不到:一份文件里有**两句**这样的散文时,奇偶又变回偶数,
    但两句**之间**那一整段仍然是反的。
  - 片 A 那条(逐行判散文)抓不到:一句**纯英文**、又没用四反引号转义的散文围栏行。

两个读数确实不同:本探针 **4 份**(奇偶口径),片 A **3 份**(散文口径)。
差的那一份是 `notes/r7-raw-run-12-watch-lease-cache.md`,它属于**第三种触发形态**,
两条判据当初都没想到:**触发行既不是散文,也不是作者写的围栏 —— 它是逐字摘录的源码本身**。
`gateway/run.py` 那段 docstring 里有一行缩进的 ``` ,摘录逐字照抄(照抄是对的,
围栏块的契约就是逐字),于是**摘录的内容**把外层围栏提前关掉了(触发对:`:659` 开、
`:700` 是下一个 ```python 而不是配对的收尾)。

所以这个缺陷至少有三类触发:**(a) 谈论围栏的散文;(b) 两句这样的散文互相抵消;
(c) 逐字摘录里自带围栏标记。** (c) 尤其要紧,因为它**不是任何人写错了** ——
遵守逐字契约就会产生它。修法只能在关卡侧(例如记录开栏的语言标记与缩进、
只让同形收尾闭合),不能靠约束作者。

用法:
    python3 data/r11d/probes/fence_balance_check.py [文件...]     # 默认全语料
"""
import re
import subprocess
import sys
from pathlib import Path

STUDY = Path(__file__).resolve().parents[3]
FENCE = re.compile(r"^\s*```")


def corpus():
    out = subprocess.run(["git", "-C", str(STUDY), "ls-files"],
                         capture_output=True, text=True, check=True).stdout
    return [p for p in out.split("\n")
            if p.endswith(".md") and p.split("/")[0] in
            ("chapters", "notes", "reports", "reviews")]


def main(argv):
    targets = argv[1:] or corpus()
    bad = []
    for rel in targets:
        p = Path(rel) if Path(rel).is_absolute() else STUDY / rel
        try:
            lines = p.read_text(encoding="utf-8").split("\n")
        except OSError:
            continue
        marks = [i for i, l in enumerate(lines, 1) if FENCE.match(l)]
        if len(marks) % 2:
            bad.append((rel, len(marks), marks[-1], len(lines)))
    print(f"扫描 {len(targets)} 份;围栏标记为奇数的文件 {len(bad)} 份")
    for rel, n, last, total in bad:
        blind = total - last
        print(f"  [ODD-FENCE] {rel}  标记 {n} 个,最后一个在 :{last},"
              f"其后 {blind} 行处于「永远在围栏里」的盲区")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
