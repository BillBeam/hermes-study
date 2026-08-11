#!/usr/bin/env python3
"""负控:强制范围单一落点 `scripts/mandatory_scope.py`(R11F-fix 第 4 项)。

要证的是两件事:

  (a) **空段真的会让关卡红**,而不是静默变成一个更小的分母 —— 这正是 R11F 丢掉
      `reading/` 时发生的事(关卡绿、报告报数、无人指出少跑了一段);
  (b) `--round <N>` 展开出来的文件集,与 CLAUDE.md 里那行 shell 的 glob **逐字相同**,
      并且与「漏掉 `reading/`」的那个集合差额可点名。

    python3 data/r11f-fix/probes/gate_scope_negative_control.py

S1 / S2 / S3 在 `mktemp -d` 造的临时 STUDY 里跑(只放一份 `scripts/mandatory_scope.py`,
它的 `STUDY = parents[1]` 于是指向临时目录,不碰本仓库);S4 在真仓库上比集合,只读。
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

STUDY = Path(__file__).resolve().parents[3]
MOD = STUDY / "scripts" / "mandatory_scope.py"
RND = "11f"


def temp_study(layout):
    """造一个临时 STUDY;layout = {相对路径: 内容}。回临时根目录。"""
    tmp = Path(tempfile.mkdtemp(prefix="scope-nc-"))
    (tmp / "scripts").mkdir()
    shutil.copy2(MOD, tmp / "scripts" / "mandatory_scope.py")
    for rel, body in layout.items():
        p = tmp / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    return tmp


def run_in(tmp, *args):
    p = subprocess.run([sys.executable, "scripts/mandatory_scope.py", *args],
                       cwd=tmp, capture_output=True, text=True, timeout=30)
    return p.returncode, (p.stdout + p.stderr).strip()


FULL = {
    "chapters/r1-x.md": "x\n",
    "reading/01-quickread.md": "x\n",
    "notes/r9z-raw-a.md": "x\n",
    "reports/round-9z-b.md": "x\n",
}
NO_READING = {k: v for k, v in FULL.items() if not k.startswith("reading/")}


def show(tag, title, rc, out, ok, note=""):
    print(f"\n{'=' * 78}\n{tag} · {title}\n{'=' * 78}")
    print(f"exit={rc}")
    for line in out.splitlines():
        print(f"  {line}")
    if note:
        print(f"  ({note})")
    print(f"断言:{'PASS' if ok else '**FAIL**'}")
    return ok


def main():
    rows = []

    # S1:reading/ 段为空 —— R11F 那次的形状,必须是一次有声的失败。
    tmp = temp_study(NO_READING)
    try:
        rc, out = run_in(tmp, "--round", "9z")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    rows.append(show("S1", "reading/ 段解析出 0 个文件 -> EMPTY-SCOPE 阻断",
                     rc, out, rc != 0 and "EMPTY-SCOPE" in out and "reading" in out))

    # S2:轮次号写错 —— 两个与轮次相关的段同时为空。
    tmp = temp_study(FULL)
    try:
        rc, out = run_in(tmp, "--round", "nosuch")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    rows.append(show("S2", "轮次号写错 -> notes/reports 两段皆空,同样阻断",
                     rc, out,
                     rc != 0 and "EMPTY-SCOPE" in out and "notes" in out and "reports" in out))

    # S3 正控:四段齐全 -> 解析成功,并把每段个数打印出来。
    tmp = temp_study(FULL)
    try:
        rc, out = run_in(tmp, "--round", "9z")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    rows.append(show("S3", "正控:四段齐全 -> 解析成功且逐段报数",
                     rc, out,
                     rc == 0 and "chapters=1" in out and "reading=1" in out
                     and "notes=1" in out and "reports=1" in out))

    # S4:真仓库上比集合 —— --round 展开 == CLAUDE.md 那行 glob;差额 == 掉的那一段。
    sys.path.insert(0, str(STUDY / "scripts"))
    from mandatory_scope import resolve                                    # noqa: E402
    got, _ = resolve([RND])
    want = sorted({p for pat in (f"chapters/*.md", "reading/*.md",
                                 f"notes/r{RND}-*.md", f"reports/round-{RND}-*.md")
                   for p in STUDY.glob(pat)})
    r11f_scope = sorted({p for pat in (f"chapters/*.md", f"notes/r{RND}-*.md",
                                       f"reports/round-{RND}-*.md")
                         for p in STUDY.glob(pat)})
    missing = sorted(set(got) - set(r11f_scope))
    out = (f"--round {RND} 展开 {len(got)} 个文件\n"
           f"CLAUDE.md 那行 glob 展开 {len(want)} 个文件\n"
           f"两者相同 ? {sorted(got) == want}\n"
           f"R11F 报告 §11 记的范围(无 reading/)展开 {len(r11f_scope)} 个文件\n"
           f"差额 {len(missing)} 个,逐个点名:\n"
           + "\n".join(f"  - {p.relative_to(STUDY)}" for p in missing))
    rows.append(show("S4", "真仓库:--round 展开 == CLAUDE.md 的 glob,差额即 R11F 少跑的那一段",
                     0, out, sorted(got) == want and len(missing) == 3))

    print(f"\n{'=' * 78}")
    print(f"negative-control S1..S4   PASS={sum(rows)}/{len(rows)}")
    if not all(rows):
        print("FAIL")
        return 1
    print("OK: 空段两种形态均实际触发阻断;--round 与 CLAUDE.md 的 glob 逐字同集")
    return 0


if __name__ == "__main__":
    sys.exit(main())
