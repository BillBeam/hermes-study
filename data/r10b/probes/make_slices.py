#!/usr/bin/env python3
"""Split R10's REMAINDER (977 files / 214,245 lines) into R10B's work slices.

Same contract as R10's make_slices.py: ordered rules, FIRST MATCH WINS, any file
the rules do not claim is a hard error, and the run asserts the slices partition
the scope exactly (no overlap, no loss). The unit of capacity is lines/slice, not
files/slice -- R10 measured R8D at 20,838 lines/slice and itself at 22,145, a
6.3% spread, while files/slice differed by 2.2x. Target here is ~21,500.

Slice I is the 13 L3 files, kept whole and alone on purpose: L3 has had zero
precedent for ten rounds and R11B has 787 files / 263,763 lines of it waiting on
a number. Mixing them into a general slice would make the L3 unit cost
unmeasurable, which is the one thing this round is supposed to produce.

    python3 data/r10b/probes/make_slices.py [--write]
"""
import csv
import sys
from pathlib import Path

STUDY = Path(__file__).resolve().parents[3]
LEDGER = STUDY / "data" / "ledger.tsv"
SCOPE = STUDY / "data" / "r10" / "slices" / "REMAINDER.txt"
OUT = STUDY / "data" / "r10b" / "slices"

# (slice, title, [prefix or exact path, ...]) -- ordered, first match wins.
RULES = [
    ("I", "apps/desktop 的 i18n 语言包(全部 13 个 L3 文件,单独成片以取 L3 单位成本)", [
        "apps/desktop/src/i18n/",
    ]),
    # B before A: A's last prefix is all of app/chat/, and the session sidebar
    # living under it belongs with the session list, not with the composer.
    ("B", "会话列表、切换与会话视图", [
        "apps/desktop/src/app/chat/sidebar/",
        "apps/desktop/src/app/session/",
        "apps/desktop/src/app/quick-entry/",
        "apps/desktop/src/app/session-switcher.tsx",
        "apps/desktop/src/app/session-picker-overlay.tsx",
        "apps/desktop/src/app/open-session.ts",
    ]),
    ("A", "聊天输入区:composer、右栏与会话瓦片", [
        "apps/desktop/src/app/chat/composer/",
        "apps/desktop/src/app/chat/right-rail/",
        "apps/desktop/src/app/chat/hooks/",
        "apps/desktop/src/app/chat/",
    ]),
    ("C", "设置面、计费与 profile/网关设置", [
        "apps/desktop/src/app/settings/",
        "apps/desktop/src/app/profiles/",
        "apps/desktop/src/app/gateway/",
        "apps/shared/",
    ]),
    ("D", "状态层:store、hooks、sdk 与内核接驳", [
        "apps/desktop/src/store/",
        "apps/desktop/src/hooks/",
        "apps/desktop/src/sdk/",
        "apps/desktop/src/hermes.ts",
        "apps/desktop/src/main.tsx",
    ]),
    ("E", "运行时库、主题、调试与类型面", [
        "apps/desktop/src/lib/",
        "apps/desktop/src/themes/",
        "apps/desktop/src/debug/",
        "apps/desktop/src/types/",
        "apps/desktop/src/global.d.ts",
        "apps/desktop/src/vite-env.d.ts",
    ]),
    ("F", "消息渲染:assistant-ui、聊天组件与右侧栏", [
        "apps/desktop/src/components/assistant-ui/",
        "apps/desktop/src/components/chat/",
        "apps/desktop/src/app/right-sidebar/",
    ]),
    ("G", "窗格外壳、通用 UI 原语与应用 shell", [
        "apps/desktop/src/components/pane-shell/",
        "apps/desktop/src/components/ui/",
        "apps/desktop/src/app/shell/",
    ]),
    ("H", "能力面板:插件、技能、贡献、星图与命令面板", [
        "apps/desktop/src/plugins/",
        "apps/desktop/src/contrib/",
        "apps/desktop/src/app/skills/",
        "apps/desktop/src/app/starmap/",
        "apps/desktop/src/app/contrib/",
        "apps/desktop/src/app/command-palette/",
        "apps/desktop/src/app/command-center/",
        "apps/desktop/src/app/agents/",
    ]),
    ("K", "构建、打包、安装器与端到端测试", [
        "apps/desktop/scripts/",
        "apps/desktop/e2e/",
        "apps/bootstrap-installer/",
        "apps/desktop/vite.config.ts",
        "apps/desktop/vitest.config.ts",
        "apps/desktop/vitest.setup.ts",
        "apps/desktop/playwright.config.ts",
        "apps/desktop/tsconfig.json",
        "apps/desktop/tsconfig.electron.json",
        "apps/desktop/tsconfig.e2e.json",
        "apps/desktop/eslint.config.mjs",
        "apps/desktop/components.json",
        "apps/desktop/package.json",
        "apps/desktop/index.html",
        "apps/desktop/preview-demo.html",
        "apps/desktop/DESIGN.md",
        "apps/desktop/README.md",
        "apps/desktop/AGENTS.md",
    ]),
    # J is last on purpose: it is the declared catch-all for the desktop shell's
    # remaining overlays, chrome and small feature panes. Anything the rules
    # above miss lands here VISIBLY rather than being silently dropped -- but a
    # file outside apps/desktop/src/ still errors out (see below).
    ("J", "桌面外壳其余:覆盖层、小组件、宠物、cron/消息/webhook 面板与样式", [
        "apps/desktop/src/components/",
        "apps/desktop/src/app/",
        "apps/desktop/src/",
    ]),
]


def main() -> None:
    write = "--write" in sys.argv
    lines = {}
    with LEDGER.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            lines[row["path"].strip()] = (int(row["lines"]), row["layer"].strip())

    scope = [x.strip() for x in SCOPE.read_text(encoding="utf-8").splitlines() if x.strip()]
    missing = [p for p in scope if p not in lines]
    if missing:
        raise SystemExit(f"scope files absent from ledger: {missing[:5]}")

    assigned, buckets = {}, {k: [] for k, _, _ in RULES}
    for p in scope:
        for key, _, prefixes in RULES:
            if any(p == q or p.startswith(q) for q in prefixes):
                buckets[key].append(p)
                assigned[p] = key
                break
        else:
            raise SystemExit(f"no rule claims {p} -- add one rather than widening J")

    # --- partition assertions -------------------------------------------------
    total_files = sum(len(v) for v in buckets.values())
    if total_files != len(scope):
        raise SystemExit(f"file count {total_files} != scope {len(scope)}")
    seen = set()
    for key, files in buckets.items():
        for p in files:
            if p in seen:
                raise SystemExit(f"{p} landed in two slices")
            seen.add(p)
    if seen != set(scope):
        raise SystemExit("slice union != scope")

    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for key, title, _ in RULES:
        files = sorted(buckets[key])
        n = sum(lines[p][0] for p in files)
        l3 = sum(1 for p in files if lines[p][1] == "L3")
        l3n = sum(lines[p][0] for p in files if lines[p][1] == "L3")
        rows.append((key, title, len(files), n, l3, l3n))
        if write:
            (OUT / f"{key}.txt").write_text("\n".join(files) + "\n", encoding="utf-8")

    rows.sort(key=lambda r: r[0])
    print(f"{'slice':>5} {'files':>6} {'lines':>8} {'L3f':>4} {'L3lines':>8}  title")
    for key, title, nf, nl, l3, l3n in rows:
        print(f"{key:>5} {nf:6d} {nl:8d} {l3:4d} {l3n:8d}  {title}")
    tf = sum(r[2] for r in rows)
    tl = sum(r[3] for r in rows)
    t3 = sum(r[4] for r in rows)
    t3l = sum(r[5] for r in rows)
    print(f"{'TOTAL':>5} {tf:6d} {tl:8d} {t3:4d} {t3l:8d}")
    work = [r for r in rows if r[3]]
    print(f"\nlines/slice: min={min(r[3] for r in work)} max={max(r[3] for r in work)} "
          f"mean={tl // len(work)}  (R10 measured 22,145; R8D 20,838)")
    if write:
        with (OUT / "_summary.tsv").open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f, delimiter="\t")
            w.writerow(["slice", "title", "files", "lines", "l3_files", "l3_lines"])
            for key, title, nf, nl, l3, l3n in rows:
                w.writerow([key, title, nf, nl, l3, l3n])
        (OUT / "_all-r10b.txt").write_text("\n".join(sorted(scope)) + "\n", encoding="utf-8")
        print(f"\nwrote {len(rows)} slice files + _summary.tsv to {OUT}")
    print("OK: slices partition R10 REMAINDER exactly (no overlap, no loss)")


if __name__ == "__main__":
    main()
