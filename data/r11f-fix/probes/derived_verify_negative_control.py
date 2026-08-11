#!/usr/bin/env python3
"""负控:`verify_derived_numbers.py` 的校验腿(R11F-fix 第 2 项)。

要证的是一件具体的事:**一条声明覆盖多个键时,R11D/R11F 的判据只问「这个数在不在区段里」,
所以它对「哪个数是哪个键的」完全无感。** 把整张表的数字重排,关卡照样打印
`declared=N OK=N STALE=0` 并退出 0。

与写入腿的负控同一套办法:每条用例**同时跑两版**(`git show <R11F_TIP>:` 取交付版,
工作树取修订版),把两边的真实输出打出来。断言的证据是「旧版绿、新版红」,不是一句 PASS。

    python3 data/r11f-fix/probes/derived_verify_negative_control.py

每个用例造一个临时 STUDY(`mktemp -d`,不碰本仓库、不碰基线):

    scripts/verify_derived_numbers.py     # 被测的那一版
    data/ledger.tsv                       # 造出想要的复算真值
    fixture.md                            # 带 <!-- derived: --> 声明的正文

四条用例:

  V1 键值对应关系   两个键、一张两行的表,把两行的值**对调**。
                    交付版:两个数都「在区段里」-> 全绿。修订版:保序绑定失败 -> ORDER。
  V2 子串假绿       真值 2,586 在区段里只以 `12,586` 的一部分出现。
                    交付版:`"2,586" in body` -> True -> OK。修订版:token 是 `12,586` -> STALE。
  V3 锚点行号假绿   真值 2,586 在区段里只作为 `notes/x.md:2586` 的行号出现。
                    交付版:子串命中 -> OK。修订版:锚点整段排除 -> STALE。
  V4 正控           表写对时两版都绿,且修订版 `--explain` 打出键 ↔ token 的绑定。
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

STUDY = Path(__file__).resolve().parents[3]
R11F_TIP = "bdb82d5"          # R11F 收官提交(固定 sha,不用分支名)
NEW = STUDY / "scripts" / "verify_derived_numbers.py"


def ledger(rows):
    out = ["path\tkind\tlines\tlayer\tround\tstatus"]
    n = 0
    for layer, sizes in rows:
        for size in sizes:
            n += 1
            out.append(f"f{n}.py\tpy\t{size}\t{layer}\tR1\tR1-inventoried")
    return "\r\n".join(out) + "\r\n"


def run(script_text, ledger_text, fixture, extra=()):
    tmp = Path(tempfile.mkdtemp(prefix="vdn-vc-"))
    try:
        (tmp / "scripts").mkdir()
        (tmp / "data").mkdir()
        (tmp / "scripts" / "verify_derived_numbers.py").write_text(script_text, encoding="utf-8")
        (tmp / "data" / "ledger.tsv").write_text(ledger_text, encoding="utf-8", newline="")
        (tmp / "fixture.md").write_text(fixture, encoding="utf-8")
        p = subprocess.run([sys.executable, "scripts/verify_derived_numbers.py",
                            *extra, "fixture.md"],
                           cwd=tmp, capture_output=True, text=True, timeout=30)
        return p.returncode, (p.stdout + p.stderr).strip()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def case(tag, title, ledger_text, fixture, want_old, want_new, extra=(), positive=False):
    print(f"\n{'=' * 78}\n{tag} · {title}\n{'=' * 78}")
    print("\nfixture.md:")
    for line in fixture.strip().splitlines():
        print(f"    {line}")
    res = {}
    for label, text in (("R11F 交付版", OLD_SRC), ("R11F-fix 修订版", NEW.read_text(encoding="utf-8"))):
        rc, out = run(text, ledger_text, fixture, extra)
        res[label] = (rc, out)
        print(f"\n--- {label} ---  exit={rc}")
        for line in out.splitlines():
            print(f"  {line}")
    ok_old, ok_new = want_old(*res["R11F 交付版"]), want_new(*res["R11F-fix 修订版"])
    if positive:
        print(f"\n断言(正控):交付版{'绿' if ok_old else '**没绿**'};"
              f"修订版{'绿' if ok_new else '**没绿**'} —— {'PASS' if ok_old and ok_new else 'FAIL'}")
    else:
        print(f"\n断言:交付版{'确实假绿' if ok_old else '**没有假绿**'};"
              f"修订版{'已判红' if ok_new else '**未判红**'} —— "
              f"{'PASS' if ok_old and ok_new else 'FAIL'}")
    return ok_old and ok_new


# V1:L1.lines = 2,586 / L2.lines = 1,431,两行的值在表里**对调**。
V1_LEDGER = ledger([("L1", [2586]), ("L2", [1431])])
V1_FIX = """<!-- derived: ledger.L1.lines ledger.L2.lines -->

| 层 | 行数 |
|---|---:|
| L1 | 1,431 |
| L2 | 2,586 |
"""

# V2:真值 2,586 只以 `12,586` 的一部分出现。
V2_LEDGER = ledger([("L1", [2586])])
V2_FIX = """<!-- derived: ledger.L1.lines -->

L1 相关的那个数写错了,这里印的是 12,586。
"""

# V3:真值 2,586 只作为锚点行号出现。
V3_LEDGER = ledger([("L1", [2586])])
V3_FIX = """<!-- derived: ledger.L1.lines -->

L1 的行数见 `notes/x.md:2586`,正文没有印它。
"""

# V4 正控:同 V1 的台账,表写对了。
V4_FIX = """<!-- derived: ledger.L1.lines ledger.L2.lines -->

| 层 | 行数 |
|---|---:|
| L1 | 2,586 |
| L2 | 1,431 |
"""


def main():
    rows = []
    rows.append(case(
        "V1", "一条声明覆盖多个键:区段内的取值与键的对应关系必须可判",
        V1_LEDGER, V1_FIX,
        want_old=lambda rc, out: rc == 0 and "declared=2  OK=2" in out,
        want_new=lambda rc, out: rc == 1 and "ORDER=1" in out and "[ORDER]" in out))
    rows.append(case(
        "V2", "子串假绿:12,586 里的 2,586 不是 2,586",
        V2_LEDGER, V2_FIX,
        want_old=lambda rc, out: rc == 0 and "OK=1" in out,
        want_new=lambda rc, out: rc == 1 and "STALE=1" in out))
    rows.append(case(
        "V3", "锚点假绿:notes/x.md:2586 的行号不是本键的真值",
        V3_LEDGER, V3_FIX,
        want_old=lambda rc, out: rc == 0 and "OK=1" in out,
        want_new=lambda rc, out: rc == 1 and "STALE=1" in out))
    rows.append(case(
        "V4", "正控:表写对时两版都绿,修订版还打得出键 ↔ token 的绑定",
        V1_LEDGER, V4_FIX,
        want_old=lambda rc, out: rc == 0 and "declared=2  OK=2" in out,
        want_new=lambda rc, out: rc == 0 and "ledger.L1.lines = 2,586 ↔" in out,
        extra=("--explain",), positive=True))

    print(f"\n{'=' * 78}")
    print(f"negative-control V1..V4   PASS={sum(rows)}/{len(rows)}")
    if not all(rows):
        print("FAIL: 有用例没有同时满足「交付版假绿 / 修订版判红」")
        return 1
    print("OK: 三种假绿在交付版上均实际发生,在修订版上均被判红;正控两版皆绿")
    return 0


OLD_SRC = subprocess.run(["git", "-C", str(STUDY), "show",
                          f"{R11F_TIP}:scripts/verify_derived_numbers.py"],
                         capture_output=True, text=True, check=True).stdout

if __name__ == "__main__":
    sys.exit(main())
