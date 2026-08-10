#!/usr/bin/env python3
"""R11C 片 D:锚点解析面的真实缺口 —— 三个口径的同一份语料。

问题(H-R11B-D-d):关卡报的 UNCHECKED 不是"锚点解析不到"的度量。
一个锚点可以在三个不同的地方消失,而三处的**可见性完全不同**:

  甲  关卡口径   —— `verify_citations.py` 实际打印的**判决数**。
                    注意它不是"锚点数":一行上多个锚点只出一条判决,
                    围栏块 / 引用块**内部**的锚点被整段跳过,表格行另计。
  甲′ 关卡正则口径 —— `vc.citations()` 在**每一行**上的**命中数**(不跳块、不折叠)。
                    即"关卡这套正则原理上能看见多少个锚点"。
  乙  可解析口径 —— 用一条**宽**正则把语料里所有「看起来是锚点」的串取出来,
                    逐个试从仓库根解析。含 `run.py:220` 这类裸文件名。

甲 → 甲′ 的差 = 跳块 + 一行多锚点折叠(关卡**故意**不看的)。
甲′ → 乙 的差 = 扩展名不在白名单 / 无扩展名不在 EXTLESS_NAMES(关卡**看不见**的,
                比 UNCHECKED 更隐蔽 —— 连分母都进不去)。

乙 内部按**可解析性**分类(优先级从上到下,互斥,加总 = 乙):

  RESOLVED-BASELINE  基线仓库根解析得到
  RESOLVED-STUDY     本学习仓库根解析得到(自引报告 / 探针 / 章节)
  NONPATH            不是路径:host:port、IP:端口、版本号一类
  ABSPATH            原文是绝对路径,正则削掉前导 `/` 后才解析不到
  UNIQUE-SUFFIX      基线里**恰好一个**文件的路径以它结尾 —— 可机械补全
  AMBIGUOUS          基线里 **≥2 个**候选(`__init__.py` 171 个)—— 不许瞎猜
  NOT-IN-TREE        两棵树里都没有同名文件 —— 第三方包 / 真写错

用法(在 /home/user/hermes-study 下):
    python3 data/r11c/d-anchor-resolution-scan.py [基线仓库] [--no-exclude]
                                                  [--tsv 输出.tsv] [--quiet]

测量污染(H-R9D-e / H-R10B-b 同源):本探针扫 notes/ 与 reports/,而**写它的这一轮**
会把 `run.py:220`、`__init__.py` 这些字样当例子写进底稿,普查随即数到自己的散文。
默认按**前缀**剔除本轮产出(不是手维护的文件名单 —— R10B 的第一版名单当场就漏了自己一个文件),
`--no-exclude` 给不剔除的那个读数。**两个读数都要报。**
"""
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

STUDY = Path(__file__).resolve().parents[2]  # data/r11c/x.py -> repo root
_pos = [a for a in sys.argv[1:] if not a.startswith("-")]
REPO = Path(_pos[0] if _pos else "/home/user/hermes-agent")
sys.path.insert(0, str(STUDY / "scripts"))
import verify_citations as vc  # noqa: E402

PREFIXES = ("r11c-", "round-11c-")
RAW = "--no-exclude" in sys.argv
QUIET = "--quiet" in sys.argv
TSV_OUT = None
for i, a in enumerate(sys.argv):
    if a == "--tsv" and i + 1 < len(sys.argv):
        TSV_OUT = Path(sys.argv[i + 1])

# 会话标识绝不进产出(硬约束 6)。探针把语料里读到的东西写进 TSV,
# 而语料里有历史会话的临时目录路径。
SESSION_ID = re.compile(r"/tmp/claude-\d+/[^\s`)]*|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def scrub(s: str) -> str:
    return SESSION_ID.sub("<会话标识已抹除>", s)


def corpus():
    for d in ("chapters", "notes", "reports", "reviews"):
        for f in sorted((STUDY / d).glob("*.md")):
            if RAW or not f.name.startswith(PREFIXES):
                yield f


# ---------------------------------------------------------------------------
# 宽正则:「看起来是锚点」的最大集合。
#
# 与关卡的 CITE 只差一处:扩展名不限白名单,改为「1-6 位字母数字」。
# 前导斜杠**不吃**(与 CITE 一致,无 lookbehind),于是 `/home/user/a/run.py:3`
# 会被解析成 `home/user/a/run.py` —— 这正是要单列 ABSPATH 一类的原因:
# 它在甲′ 里长得跟一个写错的相对路径一模一样。
WIDE = re.compile(
    r"(?P<path>\.?[A-Za-z0-9_][A-Za-z0-9_./-]*\.(?P<ext>[A-Za-z0-9]{1,6}))"
    r":(?P<start>\d+)(?:-(?P<end>\d+))?"
)
FENCE = re.compile(r"^\s*```")
QUOTE = re.compile(r"^\s*>")

# NONPATH 判据:声明式,不靠嗅探(与 NON_SOURCE_LANGS 同一条原则)。
# 只有 ext 落在这张**网络后缀**表上、且路径里没有 `/` 也没有 `_` 时才算 host:port。
NET_SUFFIX = {"org", "com", "net", "io", "dev", "ai", "local", "test", "app",
              "co", "me", "gov", "edu", "cloud", "run"}
IPV4 = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")


def baseline_paths():
    out = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True,
                         text=True, check=True).stdout.split("\n")
    return [p for p in out if p]


def suffix_index(paths):
    """path 的每一个**目录边界后缀** -> 全路径集合。

    `gateway/platforms/base.py` 贡献 `base.py`、`platforms/base.py`、
    `gateway/platforms/base.py` 三个键。于是「裸文件名」与「写了一半的路径」
    走同一条判定:以它结尾的基线文件有几个。
    """
    idx = defaultdict(set)
    for p in paths:
        parts = p.split("/")
        for k in range(len(parts)):
            idx["/".join(parts[k:])].add(p)
    return idx


BASE_PATHS = baseline_paths()
BASE_IDX = suffix_index(BASE_PATHS)
STUDY_PATHS = subprocess.run(["git", "ls-files"], cwd=STUDY, capture_output=True,
                             text=True, check=True).stdout.split("\n")
STUDY_IDX = suffix_index([p for p in STUDY_PATHS if p])

_LINES: dict = {}


def nlines(p: Path) -> int:
    k = str(p)
    if k not in _LINES:
        try:
            _LINES[k] = len(p.read_text(encoding="utf-8", errors="replace").splitlines())
        except OSError:
            _LINES[k] = -1
    return _LINES[k]


def classify(path: str, start: int, prev_char: str):
    """(类别, 详情) —— 优先级互斥,见模块 docstring。"""
    if (REPO / path).is_file():
        n = nlines(REPO / path)
        return "RESOLVED-BASELINE", ("" if start <= n else f"行号越界(文件 {n} 行)")
    if (STUDY / path).is_file():
        n = nlines(STUDY / path)
        return "RESOLVED-STUDY", ("" if start <= n else f"行号越界(文件 {n} 行)")

    head = path.split("/")[0]
    ext = path.rsplit(".", 1)[-1].lower()
    if "/" not in path and "_" not in path and (ext in NET_SUFFIX or IPV4.match(path)):
        return "NONPATH", path
    if IPV4.match(head):
        return "NONPATH", path

    if prev_char == "/":
        # 原文写的是绝对路径 / 更长的路径,正则从中间切了一刀。
        return "ABSPATH", path

    cands = BASE_IDX.get(path, set())
    if len(cands) == 1:
        only = next(iter(cands))
        n = nlines(REPO / only)
        note = "" if start <= n else f"行号越界({only} 只有 {n} 行)"
        return "UNIQUE-SUFFIX", (only + ("  " + note if note else ""))
    if len(cands) > 1:
        return "AMBIGUOUS", f"{len(cands)} 个候选"
    if STUDY_IDX.get(path):
        c = STUDY_IDX[path]
        if len(c) == 1:
            return "UNIQUE-SUFFIX", "(本仓库) " + next(iter(c))
        return "AMBIGUOUS", f"(本仓库) {len(c)} 个候选"
    return "NOT-IN-TREE", path


def gate_sees(line: str, m) -> bool:
    """关卡的正则在同一位置也认出了这个锚点吗?"""
    def resolve(pth):
        t = REPO / pth
        if not t.is_file() and (STUDY / pth).is_file():
            t = STUDY / pth
        return t
    return any(c.start() == m.start() and c.group("path") == m.group("path")
               for c in vc.citations(line, resolve))


def main():
    jia_prime = 0          # 甲′:关卡正则命中数(不跳块、不折叠)
    yi = 0                 # 乙:宽正则命中数
    blind = 0              # 乙 里关卡看不见的
    cls = Counter()
    cls_blind = Counter()
    by_name = Counter()    # 不可解析锚点的路径串频次
    rows = []
    files = 0

    for f in corpus():
        files += 1
        rel = f.relative_to(STUDY).as_posix()
        for ln, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            for m in WIDE.finditer(line):
                path, start = m.group("path"), int(m.group("start"))
                prev = line[m.start() - 1] if m.start() else ""
                kind, detail = classify(path, start, prev)
                seen = gate_sees(line, m)
                # NONPATH 不是锚点,不进任何分母(与关卡对 host:port 的判法一致)
                if kind == "NONPATH":
                    cls["NONPATH"] += 1
                    continue
                yi += 1
                cls[kind] += 1
                if seen:
                    jia_prime += 1
                else:
                    blind += 1
                    cls_blind[kind] += 1
                if not kind.startswith("RESOLVED"):
                    by_name[path] += 1
                    rows.append((rel, ln, path, start, kind,
                                 "gate-visible" if seen else "GATE-BLIND", detail))
                elif detail:
                    rows.append((rel, ln, path, start, kind + "-OUT-OF-RANGE",
                                 "gate-visible" if seen else "GATE-BLIND", detail))
                elif not seen:
                    # 能解析、却不被关卡当成锚点 —— 「连分母都进不去」那一档,
                    # 必须落进明细,否则它在 TSV 里也是隐形的。
                    rows.append((rel, ln, path, start, kind, "GATE-BLIND",
                                 "扩展名不在 CITE_EXTS 白名单上"))

        # 无扩展名锚点由关卡自己的正则单独负责,宽正则够不到,单独加进甲′
        for ln, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            for m in vc.CITE_EXTLESS.finditer(line):
                if vc.is_extless_citation(m, lambda p: (REPO / p) if (REPO / p).is_file() else (STUDY / p)):
                    jia_prime += 1
                    yi += 1
                    cls["RESOLVED-EXTLESS"] += 1

    tag = "不剔除本轮(--no-exclude)" if RAW else "剔除本轮 r11c-*"
    print(f"语料:{files} 份 .md(chapters/notes/reports/reviews),{tag}")
    print(f"甲′ 关卡正则命中 = {jia_prime}")
    print(f"乙  宽正则命中   = {yi}   (差 {blind} 个 = 关卡看不见的)")
    unres = sum(v for k, v in cls.items()
                if not k.startswith("RESOLVED") and k != "NONPATH")
    print(f"乙 中不可解析 = {unres} / {yi} = {unres * 100.0 / yi:.1f}%")
    print("\n分类(互斥,RESOLVED* 与不可解析各类加总 = 乙):")
    for k in ("RESOLVED-BASELINE", "RESOLVED-STUDY", "RESOLVED-EXTLESS",
              "ABSPATH", "UNIQUE-SUFFIX", "AMBIGUOUS", "NOT-IN-TREE"):
        if cls.get(k):
            print(f"  {k:<20} {cls[k]:>6}   其中关卡看不见 {cls_blind.get(k, 0)}")
    print(f"  {'(NONPATH 非锚点)':<20} {cls.get('NONPATH', 0):>6}   不进分母")

    print("\n不可解析锚点 TOP 20(路径串 -> 出现次数):")
    for name, n in by_name.most_common(20):
        c = BASE_IDX.get(name, set())
        note = f"基线 {len(c)} 个同名候选" if c else "基线无同名文件"
        print(f"  {n:>5}  {name}   ({note})")

    if TSV_OUT:
        with TSV_OUT.open("w", encoding="utf-8") as fh:
            fh.write("file\tline\tpath\tstart\tclass\tgate\tdetail\n")
            for r in rows:
                fh.write(scrub("\t".join(str(x) for x in r)) + "\n")
        print(f"\n明细 -> {TSV_OUT}  ({len(rows)} 行)")


if __name__ == "__main__":
    main()
