#!/usr/bin/env python3
"""负控:`verify_derived_numbers.py --sync` 的写入腿(R11F-fix 第 1 项)。

**这个负控必须真的触发**,不接受「负控通过」的自报 —— 所以每一条都**同时跑两版**:
R11F 交付版(`git show <R11F_TIP>:scripts/verify_derived_numbers.py`)与本轮修订版,
把两边的实际行为逐条打印出来。一条断言的证据是「旧版这样、新版那样」,不是一句 PASS。

跑法:

    python3 data/r11f-fix/probes/derived_write_negative_control.py

每个用例造一个**临时 git 仓库**(`mktemp -d`,不碰本仓库,也不碰基线),里面放:

    scripts/verify_derived_numbers.py     # 被测的那一版
    data/ledger.tsv                       # 先提交「旧」台账,再改成「新」台账
    fixture.md                            # 带 <!-- derived: --> 声明的正文

然后端到端跑 `--sync --since HEAD`,比对 fixture.md 落笔后的样子。
`--since HEAD` 在这里是**不动的**:临时仓库只有一个提交,且负控自己不提交第二次。

四条用例:

  W1 非目标数字      区段里同时有 `12,586` 和独立的 `2,586`,要换的是后者。
                     旧版 `str.replace` 把 `12,586` 一并改成 `12,829`,而 `hits` 用同一套
                     子串语义去数,`assert done == hits` 恒成立 —— 它抓不到自己造的损坏。
  W2 守卫 4 死代码   同一条声明里两个键旧真值相同。旧版的 `sibling_truths` 是 set,
                     `sum(1 for v in set if v == old) > 1` 恒为假,守卫一次都没触发过;
                     于是 A 的新值被写进了 B 的那一格。
  W3 死循环          新值把旧值当子串包住(586 -> 2586)。旧版 `while f_old in line:`
                     每换一次又造出一个 f_old,**永不终止**;这里用子进程超时把它钉下来。
  W4 锚点行号        区段里有 `notes/x.md:2586` 和独立的 `2,586`。旧版把锚点行号也换了
                     —— 那是 verify_citations.py 的资产,当场造一处引用漂移。

外加 W5 正控:一次正常同步 + 重跑幂等,证明收紧后写入腿仍然能干活。
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

STUDY = Path(__file__).resolve().parents[3]
R11F_TIP = "bdb82d5"          # R11F 收官提交,交付版脚本的出处(固定 sha,不用分支名)
NEW = STUDY / "scripts" / "verify_derived_numbers.py"
TIMEOUT = 25


def ledger(rows):
    """造一份台账:rows = [(layer, [每个文件的行数])]。列序与 data/ledger.tsv 一致。"""
    out = ["path\tkind\tlines\tlayer\tround\tstatus"]
    n = 0
    for layer, sizes in rows:
        for size in sizes:
            n += 1
            out.append(f"f{n}.py\tpy\t{size}\t{layer}\tR1\tR1-inventoried")
    return "\r\n".join(out) + "\r\n"


def make_repo(script_text, old_ledger, new_ledger, fixture):
    tmp = Path(tempfile.mkdtemp(prefix="vdn-nc-"))
    (tmp / "scripts").mkdir()
    (tmp / "data").mkdir()
    (tmp / "scripts" / "verify_derived_numbers.py").write_text(script_text, encoding="utf-8")
    (tmp / "data" / "ledger.tsv").write_text(old_ledger, encoding="utf-8", newline="")
    (tmp / "fixture.md").write_text(fixture, encoding="utf-8")
    env = dict(os.environ, GIT_AUTHOR_NAME="nc", GIT_AUTHOR_EMAIL="nc@x",
               GIT_COMMITTER_NAME="nc", GIT_COMMITTER_EMAIL="nc@x")
    for cmd in (["git", "init", "-q", "-b", "nc"], ["git", "add", "-A"],
                ["git", "commit", "-qm", "old ledger", "--no-verify"]):
        subprocess.run(cmd, cwd=tmp, env=env, check=True, capture_output=True)
    (tmp / "data" / "ledger.tsv").write_text(new_ledger, encoding="utf-8", newline="")
    return tmp


def run_sync(tmp):
    """跑 --sync --since HEAD,回 (退出码, 合并输出, fixture.md 落笔后的内容)。"""
    try:
        p = subprocess.run([sys.executable, "scripts/verify_derived_numbers.py",
                            "--sync", "--since", "HEAD", "fixture.md"],
                           cwd=tmp, capture_output=True, text=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        return "TIMEOUT", f"<未在 {TIMEOUT}s 内终止>", (tmp / "fixture.md").read_text(encoding="utf-8")
    return p.returncode, (p.stdout + p.stderr).strip(), (tmp / "fixture.md").read_text(encoding="utf-8")


def case(tag, title, old_ledger, new_ledger, fixture, want_old, want_new, positive=False):
    """跑同一个用例的旧版与新版,打印两边实际行为,回「两边都符合预期」。

    positive=True 表示这是正控:期望的是**两版都正常干活**,不是「旧版翻车」。
    """
    print(f"\n{'=' * 78}\n{tag} · {title}\n{'=' * 78}")
    results = {}
    for label, text in (("R11F 交付版", OLD_SRC), ("R11F-fix 修订版", NEW.read_text(encoding="utf-8"))):
        tmp = make_repo(text, old_ledger, new_ledger, fixture)
        try:
            rc, out, body = run_sync(tmp)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        print(f"\n--- {label} ---")
        print(f"exit={rc}")
        for line in out.splitlines()[:6]:
            print(f"  {line}")
        print("  fixture.md 落笔后(只打印区段行):")
        for line in body.splitlines():
            if line.startswith("|") or line.startswith("仍有") or line.startswith("见 "):
                print(f"    {line}")
        results[label] = (rc, out, body)
    ok_old = want_old(*results["R11F 交付版"])
    ok_new = want_new(*results["R11F-fix 修订版"])
    if positive:
        print(f"\n断言(正控):交付版{'正常' if ok_old else '**异常**'};"
              f"修订版{'正常' if ok_new else '**异常**'} —— "
              f"{'PASS' if (ok_old and ok_new) else 'FAIL'}")
    else:
        print(f"\n断言:交付版{'确实' if ok_old else '**没有**'}表现出该缺陷;"
              f"修订版{'已' if ok_new else '**未**'}拦住 —— "
              f"{'PASS' if (ok_old and ok_new) else 'FAIL'}")
    return ok_old and ok_new


# ---------------------------------------------------------------- 用例定义

# W1:L1.lines 旧 2586 -> 新 2829;区段里另有一个 12,586 是别的东西。
W1_OLD = ledger([("L1", [2586]), ("L2", [10])])
W1_NEW = ledger([("L1", [2829]), ("L2", [10])])
W1_FIX = """<!-- derived: ledger.L1.lines -->

| 指标 | 值 |
|---|---:|
| L1 行数 | 2,586 |
| 另一个与本声明无关的数 | 12,586 |
"""

# W2:两个键真值都是 2586,而只有 L1 要变(L2 本轮没动)。
# 于是 L2 那一条在 `old == new` 处就被跳过,**没有第二组 edits 去撞那句 assert** ——
# 这正是守卫 4 唯一该出手、而 R11F 版一定不出手的形态:L1 的 hits 把 L2 那一格也算了进去。
W2_OLD = ledger([("L1", [2586]), ("L2", [2586])])
W2_NEW = ledger([("L1", [2829]), ("L2", [2586])])
W2_FIX = """<!-- derived: ledger.L1.lines ledger.L2.lines -->

| 层 | 行数 |
|---|---:|
| L1 | 2,586 |
| L2 | 2,586 |
"""

# W3:新值把旧值当子串包住(586 -> 2586)。
W3_OLD = ledger([("L1", [586])])
W3_NEW = ledger([("L1", [2586])])
W3_FIX = """<!-- derived: ledger.L1.lines -->

| 指标 | 值 |
|---|---:|
| L1 行数 | 586 |
"""

# W4:区段里有一个锚点,它的行号恰好等于旧真值。
W4_OLD = ledger([("L1", [2586])])
W4_NEW = ledger([("L1", [2829])])
W4_FIX = """<!-- derived: ledger.L1.lines -->

| 指标 | 值 |
|---|---:|
| L1 行数 | 2,586 |
| 出处 | 见 `notes/x.md:2586` |
"""

# W5 正控:一段普通的、带算式的区段,旧值出现两次,两处都该换,且算式仍成立。
# L1 1,000 -> 1,300、合计 8,530 -> 8,830;7,530 未声明,不该被动(8,830 − 1,300 = 7,530)。
W5_OLD = ledger([("L1", [1000]), ("L2", [7530])])
W5_NEW = ledger([("L1", [1300]), ("L2", [7530])])
W5_FIX = """<!-- derived: ledger.L1.lines ledger.total.lines -->

仍有 1,000 行属于 L1,即 8,530 − 1,000 = 7,530 行不属于它。
"""


def main():
    rows = []
    rows.append(case(
        "W1", "替换动作不得命中非目标数字(12,586 里的 2,586)",
        W1_OLD, W1_NEW, W1_FIX,
        want_old=lambda rc, out, body: "12,829" in body,
        want_new=lambda rc, out, body: "12,586" in body and "| 2,829 |" in body))
    rows.append(case(
        "W2", "同声明内多键撞值的守卫必须真的能被触发",
        W2_OLD, W2_NEW, W2_FIX,
        # 交付版:守卫恒不触发 -> L1 的两个 hits 把 L2 那一格也算进去,两格都成 2,829,
        # 且输出报 synced=2 / skipped=0(即「全都对了」)。L2 那一格从此是错的。
        want_old=lambda rc, out, body: body.count("2,829") == 2 and "[SKIP]" not in out,
        # 修订版:因与 ledger.L2.lines 撞值而跳过,点名撞的是谁,一个字都不写
        want_new=lambda rc, out, body: body.count("2,586") == 2
        and out.count("[SKIP]") == 1 and "张冠李戴" in out
        and "ledger.L2.lines" in out))
    rows.append(case(
        "W3", "新值包含旧值时,替换必须终止",
        W3_OLD, W3_NEW, W3_FIX,
        want_old=lambda rc, out, body: rc == "TIMEOUT",
        want_new=lambda rc, out, body: rc == 0 and "| 2,586 |" in body))
    rows.append(case(
        "W4", "锚点里的行号不是可复算数,不许被改",
        W4_OLD, W4_NEW, W4_FIX,
        want_old=lambda rc, out, body: "notes/x.md:2829" in body,
        want_new=lambda rc, out, body: "notes/x.md:2586" in body and "| 2,829 |" in body))
    ok = (lambda rc, out, body: body.count("1,300") == 2 and "8,830" in body
          and "7,530" in body and rc == 0)
    rows.append(case(
        "W5", "正控:一段里同一个旧值出现两次,两处都换,未声明的数不动",
        W5_OLD, W5_NEW, W5_FIX, want_old=ok, want_new=ok, positive=True))

    print(f"\n{'=' * 78}")
    print(f"negative-control W1..W5   PASS={sum(rows)}/{len(rows)}  (W1..W4 负控 + W5 正控)")
    if not all(rows):
        print("FAIL: 有用例没有同时满足「交付版触发缺陷 / 修订版拦住」")
        return 1
    print("OK: 四条负控的缺陷在交付版上均实际触发、在修订版上均被拦住;正控两版皆正常")
    return 0


OLD_SRC = subprocess.run(["git", "-C", str(STUDY), "show",
                          f"{R11F_TIP}:scripts/verify_derived_numbers.py"],
                         capture_output=True, text=True, check=True).stdout

if __name__ == "__main__":
    sys.exit(main())
