#!/usr/bin/env python3
"""R9C §3.1 / §3.2-4 的「点名覆盖率」测量,原样可重跑。

对台账里 layer=L1 的每个文件,在指定语料中做**精确子串**搜索:
  - 全路径零命中:该文件的仓库相对路径,在语料里一次也没出现
  - 裸文件名零命中:连 basename 都搜不到

用法:
  python3 l1_named_coverage.py <study_root> [--scope notes,chapters,reports] [--status-filter deep-read|all]
"""
import sys
import argparse
from pathlib import Path


def load_ledger(study: Path):
    rows = []
    with open(study / "data" / "ledger.tsv", encoding="utf-8") as fh:
        header = fh.readline()
        for line in fh:
            parts = line.rstrip("\n").rstrip("\r").split("\t")
            if len(parts) < 6:
                continue
            path, kind, lines, layer, rnd, status = parts[0], parts[1], parts[2], parts[3], parts[4], parts[5]
            rows.append({
                "path": path,
                "lines": int(lines),
                "layer": layer.strip(),
                "round": rnd.strip(),
                "status": status.strip(),
            })
    return rows


def corpus_text(study: Path, dirs):
    blobs = []
    for d in dirs:
        for p in sorted((study / d).glob("*.md")):
            blobs.append(p.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(blobs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("study")
    ap.add_argument("--scope", default="notes,chapters,reports")
    ap.add_argument("--status-filter", default="deep-read",
                    choices=["deep-read", "all"],
                    help="deep-read = 只测已标 *-deep-read 的;all = 测全部 L1")
    ap.add_argument("--list-misses", action="store_true")
    args = ap.parse_args()

    study = Path(args.study)
    dirs = [d.strip() for d in args.scope.split(",") if d.strip()]
    text = corpus_text(study, dirs)

    rows = [r for r in load_ledger(study) if r["layer"] == "L1"]
    if args.status_filter == "deep-read":
        rows = [r for r in rows if r["status"].endswith("-deep-read")]

    path_miss, name_miss = [], []
    for r in rows:
        if r["path"] not in text:
            path_miss.append(r)
            if Path(r["path"]).name not in text:
                name_miss.append(r)

    print(f"语料 = {'+'.join(dirs)}/  ({len(text):,} 字符)")
    print(f"被测 L1 文件 = {len(rows)} (status-filter={args.status_filter})")
    print(f"全路径零命中   = {len(path_miss)} 文件 / {sum(r['lines'] for r in path_miss):,} 行")
    print(f"裸文件名零命中 = {len(name_miss)} 文件 / {sum(r['lines'] for r in name_miss):,} 行")

    if args.list_misses:
        print("\n--- 全路径零命中逐个点名 ---")
        names = {r["path"] for r in name_miss}
        for r in sorted(path_miss, key=lambda x: x["path"]):
            tag = "  [连裸文件名也零命中]" if r["path"] in names else ""
            print(f"  {r['path']}\t{r['lines']}\t{r['round']}\t{r['status']}{tag}")


if __name__ == "__main__":
    main()
