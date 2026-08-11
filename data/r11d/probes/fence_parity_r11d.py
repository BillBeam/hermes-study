#!/usr/bin/env python3
"""R11D 片 A 副产物:普查「散文里提到围栏标记 → 关卡把整份文件的奇偶翻掉」。

`scripts/verify_citations.py:318` 认围栏靠 `FENCE = re.compile(r"^\\s*```")`,
而 markdown 里**缩进一格、用四反引号转义**去谈论一个围栏(```` ```verify ````)是
本项目 `CLAUDE.md` 自己在用的标准写法。这两件事撞在一起:那句散文被当成**围栏开头**,
其后整份文件的围栏奇偶被翻转,于是

  - 本该被扫的正文,关卡当成「在围栏内」**一条锚点都不扫**;
  - 本该被跳过的 ```` ```text ```` 声明式非源码块,反而被当散文扫。

后一种是**声明式豁免在这里失效**,与 R10B「白名单外的锚点连分母都进不去」同一物种:
不是判错,是**根本没进检查面**,而输出里没有任何一个数会变红。

判据。宽口径 = 关卡自己的 `^\\s*```。命中 = 宽口径认、但这一行**明显是散文**:

  (a) 行内含中日韩字符 —— 信息串(info string)里不会有中文;或
  (b) 开头那串反引号之后**还有一串反引号** —— 正是 ```` ```x ```` 这种四反引号转义写法。

**不用「整行只有反引号 + 语言标记」当严格口径**:实测那样会把列表里缩进 4 格的正常围栏、
以及 `` ```356:365:/path/to.py `` 这种带行号信息串的正常围栏一并算成命中(22 处里 20 处是这么来的),
**普查一旦把正常写法算成缺陷,读者就会开始忽略它** —— 与本项目「声明,不靠嗅探」同一条理由。

命中行之后到「下一个宽口径围栏行」为止,关卡什么都不扫。

    python3 data/r11d/probes/fence_parity_r11d.py
"""
import re
import subprocess
import sys
from pathlib import Path

STUDY = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(STUDY / "scripts"))
import verify_citations as vc  # noqa: E402

LOOSE = vc.FENCE
CJK = re.compile(r"[　-鿿＀-￯]")
OPENER = re.compile(r"^\s*(`{3,})")
DIRS = ("chapters", "notes", "reports", "reviews")


def prosey(line: str) -> bool:
    """宽口径认它是围栏行,但它其实是一句谈论围栏的散文。"""
    m = OPENER.match(line)
    if not m:
        return False
    return bool(CJK.search(line)) or "`" in line[m.end():]


def real_fence(line: str) -> bool:
    return bool(LOOSE.match(line)) and not prosey(line)


def gate_skipped(lines):
    """关卡按其主循环真正跳过的行号集合(1 起)。照抄 check_note 的跳法。"""
    skipped, i = set(), 0
    while i < len(lines):
        if LOOSE.match(lines[i]):
            skipped.add(i + 1)
            i += 1
            while i < len(lines) and not LOOSE.match(lines[i]):
                skipped.add(i + 1)
                i += 1
            if i < len(lines):
                skipped.add(i + 1)
            i += 1
            continue
        i += 1
    return skipped


def read_at(rev, rel):
    """rev 为 None 读工作树,否则读该提交那一版 —— 让「改之前是多少」可复现。"""
    if rev is None:
        return (STUDY / rel).read_text(encoding="utf-8", errors="replace")
    out = subprocess.run(["git", "show", f"{rev}:{rel}"], cwd=STUDY,
                         capture_output=True, text=True)
    return out.stdout if out.returncode == 0 else None


def list_at(rev, d):
    if rev is None:
        return [f"{d}/{f.name}" for f in sorted((STUDY / d).glob("*.md"))]
    out = subprocess.run(["git", "ls-tree", "--name-only", f"{rev}:{d}"], cwd=STUDY,
                         capture_output=True, text=True, check=True).stdout
    return sorted(f"{d}/{n}" for n in out.split("\n") if n.endswith(".md"))


def main():
    rev = None
    if "--rev" in sys.argv:
        rev = sys.argv[sys.argv.index("--rev") + 1]
    resolve = lambda p: STUDY.parent / "hermes-agent" / p  # noqa: E731
    files = 0
    hits = 0
    blind_lines = 0
    blind_anchors = 0
    detail = []
    for d in DIRS:
        for rel in list_at(rev, d):
            text = read_at(rev, rel)
            if text is None:
                continue
            lines = text.splitlines()
            bad = [(n, l) for n, l in enumerate(lines, 1) if prosey(l)]
            if not bad:
                continue
            files += 1
            hits += len(bad)
            skipped = gate_skipped(lines)
            real_in = False
            n_blind, n_anch = 0, 0
            for n, line in enumerate(lines, 1):
                if real_fence(line):
                    real_in = not real_in
                    continue
                # 真实口径下是正文、关卡却跳过了 —— 这就是盲区。
                # 引用块行不计入锚点数:`>` 本来就被关卡整段跳过,那里的锚点
                # **不是被奇偶 bug 弄丢的**,把它算进来会把这个数说大。
                if not real_in and n in skipped:
                    n_blind += 1
                    if not vc.QUOTE.match(line):
                        n_anch += len(vc.citations(line, resolve))
            blind_lines += n_blind
            blind_anchors += n_anch
            detail.append((rel, bad, n_blind, n_anch))

    print(f"命中文件 {files} 份,散文误判为围栏的行 {hits} 处;"
          f"盲区正文行 {blind_lines} 行,其中锚点 {blind_anchors} 处")
    show = "--show-lines" in sys.argv
    for rel, bad, nb, na in detail:
        print(f"{rel}  触发行 {','.join(str(n) for n, _ in bad)}  "
              f"盲区 {nb} 行 / 锚点 {na} 处")
        # 命中行的**原文含三反引号**,默认不打印:把它贴进 ```text 配对块会当场把块截断
        # (`verify_evidence_commands.py` 见到 ``` 即收块)。要看原文加 --show-lines。
        if show:
            for n, line in bad:
                print(f"  :{n}  {line.strip()[:72]}")


if __name__ == "__main__":
    main()
