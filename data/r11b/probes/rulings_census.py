#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R11B 片 A · A-1 跨轮定案去重普查(口径见 notes/r11b-raw-rulings-census.md §1)。

在本学习仓库任意子目录下都能跑,自己用 `git rev-parse --show-toplevel` 推仓库根。

    python3 data/r11b/probes/rulings_census.py              # 汇总:案号家族 + 声明位
    python3 data/r11b/probes/rulings_census.py --species2   # 同一案号多实体(按轮次分组)
    python3 data/r11b/probes/rulings_census.py --clusters   # 同一处代码多案号(跨轮聚类)
    python3 data/r11b/probes/rulings_census.py --id H-R9B-d # 单号明细
    python3 data/r11b/probes/rulings_census.py --file gateway/relay/media.py

口径(写死在代码里,便于重跑复核):
  * 语料面 = reports/*.md + notes/*.md + chapters/*.md;reviews/ 不并入(见底稿 §1.1)。
  * 案号四个家族:
      H  移交号        H-7 / H-R9A-a / H-R10B-C-j
      G  全局定案号    ■-R8B-12 / ▲-R11A-01 / ◇-R8C-a
      S  片内定案号    ■-H-1 / ▲-G-01 / ▲ B-2(记号 + 片字母 + 序号)
      L  轮内裸序号    ■-1 / ▲2(只在本文件内有意义,故作用域 = 文件)
  * 「声明位」= 案号出现在标题行 / 表格前两格 / `- **案号**` 项目符号 / `**案号** ——` 段首。
  * 锚点 = 声明位正文块内的 `路径:行号`,且该路径在基线里真实存在。
  * 轮次 = 从产出文件名解析(reports/round-9c-* → R9C;notes/r9b-raw-tts.md → R9B)。
"""
from __future__ import annotations

import argparse
import collections
import os
import re
import subprocess
import sys


def repo_root() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    out = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                         cwd=here, capture_output=True, text=True, check=True)
    return out.stdout.strip()


ROOT = repo_root()
BASELINE = os.environ.get("HERMES_BASELINE", "/home/user/hermes-agent")
CORPUS_DIRS = ["reports", "notes", "chapters"]
# 语料面截止到 R11A:`notes/r11b-*` 是本轮各片**正在写**的文件,是移动靶,
# 纳入会让报出的数不可复现(本片自己的底稿也在其中)。
EXCLUDE_PREFIX = ("r11b-",)

# ---------------------------------------------------------------- 语料快照
# 语料固定在 R11B 派工那一条 commit 上,而不是工作区。
# 理由:R11B 的片 C(改 chapters/ 锚点排版)与片 D(改历史 notes/ 引用)与本片**并行**
# 在同一棵工作树上写文件;若从工作区读,本底稿报出的每一个数都会随它们的进度漂移,
# 而「shell 命令即证据」这条关卡要在它们改完之后才重跑。快照读法让重跑恒等。
CORPUS_REV = os.environ.get("R11B_CORPUS_REV", "00f09bfeebc09055070f5577c3d51271a48d2088")


def _git(*args: str) -> str:
    return subprocess.run(["git", "-C", ROOT, *args],
                          capture_output=True, text=True, check=True).stdout


def corpus_files():
    """快照里 reports/ notes/ chapters/ 下的 .md,排除本轮在写的 r11b-*。"""
    out = _git("ls-tree", "-r", "--name-only", CORPUS_REV)
    for path in sorted(out.split("\n")):
        if not path.endswith(".md"):
            continue
        d = path.split("/")[0]
        if d not in ("reports", "notes", "chapters"):
            continue
        if os.path.basename(path).startswith(EXCLUDE_PREFIX):
            continue
        yield path


def corpus_read(path: str) -> str:
    return _git("show", f"{CORPUS_REV}:{path}")


# ---------------------------------------------------------------- 案号正则
RE_S = re.compile(r"[▲◇■◎][- ]([A-Z])-(\d{1,2})\b")           # ■-H-1 / ▲ B-2
RE_H = re.compile(r"\bH-(?:R\d+[A-Z]*(?:FIX)?|\d+)(?:-[A-Za-z0-9]+)*\b")
RE_G = re.compile(r"[▲◇■◎]-R\d+[A-Z]*(?:FIX)?-[0-9A-Za-z]+")
RE_L = re.compile(r"[▲◇■◎]-?\d{1,2}[a-z]?(?![0-9])")

CITE_EXTS = "py|mdx|md|yaml|yml|toml|c|h|sh|json|tsx|ts|mjs|js|nix|rs|txt"
RE_ANCHOR = re.compile(r"(?<![\w/.-])(\.?[\w][\w./+-]*\.(?:%s)):(\d+)" % CITE_EXTS)

RE_ROUND_REPORT = re.compile(r"round-([0-9]+[a-z]*(?:-fix)?)-")
RE_ROUND_NOTE = re.compile(r"^(r[0-9]+[a-z]*)-")


def round_of(rel: str) -> str:
    base = os.path.basename(rel)
    m = RE_ROUND_REPORT.match(base)
    if m:
        return "R" + m.group(1).upper().replace("-FIX", "FIX")
    m = RE_ROUND_NOTE.match(base)
    if m:
        return m.group(1).upper()
    return "?"


def iter_files(dirs):
    return corpus_files()


def find_ids(text: str):
    """返回 [(案号, 家族, 起始位置)];家族优先级 S > G > H > L,避免 ■-H-1 被拆成 H-1。"""
    out, consumed = [], set()

    def take(rx, fam):
        for m in rx.finditer(text):
            if any(i in consumed for i in range(m.start(), m.end())):
                continue
            out.append((m.group(0).replace(" ", "-"), fam, m.start()))
            consumed.update(range(m.start(), m.end()))

    take(RE_S, "S")
    take(RE_G, "G")
    take(RE_H, "H")
    take(RE_L, "L")
    return out


def strip_emph(s: str) -> str:
    return s.replace("**", "").replace("`", "").replace("~~", "").strip()


def is_decl(line: str, cid: str) -> str | None:
    s = line.strip()
    probe = cid.replace("-", "")
    def has(x):
        return cid in x or probe in x.replace("-", "").replace(" ", "")
    if not s:
        return None
    if s.startswith("#"):
        return "heading" if has(strip_emph(s.lstrip("#"))) else None
    if s.startswith("|"):
        cells = [strip_emph(c) for c in s.strip("|").split("|")]
        for idx in (0, 1):
            if idx < len(cells) and cells[idx] and has(cells[idx]):
                if set(cells[idx]) <= set("-: "):
                    return None
                return "table"
        return None
    m = re.match(r"^[-*+]\s+(.*)$", s)
    if m:
        body = m.group(1).strip()
        if has(strip_emph(body)[:60]) and (body.startswith("**") or body.startswith("`")
                                           or has(body[:len(cid) + 4])):
            return "bullet"
        return None
    if s.startswith("**") and has(strip_emph(s)[:60]):
        return "bold-lead"
    return None


def block_of(lines, i):
    """声明位的『正文块』——只取足以确定它指向哪段代码的那一小段,不取整节。

    取窄不取宽是有意的:块越长,越容易把邻近别的定案的锚点算到本条头上,
    而本探针是给人工裁决用的候选生成器,假阳性比假阴性贵。
    """
    s = lines[i].strip()
    if s.startswith("|"):
        return [lines[i]]
    if s.startswith("#"):
        lvl = len(s) - len(s.lstrip("#"))
        out = []
        for j in range(i, min(len(lines), i + 25)):
            t = lines[j].strip()
            if j > i and t.startswith("#") and (len(t) - len(t.lstrip("#"))) <= lvl:
                break
            out.append(lines[j])
        return out
    # 项目符号 / 加粗段首:取到本段结束(空行),最多 12 行
    out = []
    for j in range(i, min(len(lines), i + 12)):
        if j > i and not lines[j].strip():
            break
        out.append(lines[j])
    return out


_exists_cache: dict[str, bool] = {}


def baseline_exists(path: str) -> bool:
    if path not in _exists_cache:
        _exists_cache[path] = os.path.exists(os.path.join(BASELINE, path))
    return _exists_cache[path]


def collect():
    decls = collections.defaultdict(list)
    for rel in iter_files(CORPUS_DIRS):
        rnd = round_of(rel)
        lines = corpus_read(rel).split("\n")
        in_fence = False
        for i, line in enumerate(lines):
            if line.strip().startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            seen = set()
            for cid, fam, _ in find_ids(line):
                if cid in seen:
                    continue
                seen.add(cid)
                if not is_decl(line, cid):
                    continue
                key = f"{rel}::{cid}" if fam in ("L", "S") else cid
                blk = "\n".join(block_of(lines, i))
                anchors = sorted({(m.group(1), int(m.group(2)))
                                  for m in RE_ANCHOR.finditer(blk)
                                  if baseline_exists(m.group(1))})
                decls[key].append(dict(file=rel, line=i + 1, round=rnd, fam=fam,
                                       kind=is_decl(line, cid), cid=cid,
                                       text=line.strip()[:190], anchors=anchors))
    return decls


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--species2", action="store_true")
    ap.add_argument("--clusters", action="store_true")
    ap.add_argument("--id")
    ap.add_argument("--file")
    ap.add_argument("--window", type=int, default=60)
    ap.add_argument("--min-rounds", type=int, default=2)
    ap.add_argument("--summary", action="store_true",
                    help="只打家族汇总(不打逐轮),便于钉进 ```text 块")
    args = ap.parse_args()

    decls = collect()

    if args.id:
        for key, ds in sorted(decls.items()):
            if ds[0]["cid"] != args.id:
                continue
            print(f"--- {key}")
            for d in ds:
                print(f"  {d['file']}:{d['line']} [{d['round']}/{d['kind']}] {d['text'][:140]}")
                if d["anchors"]:
                    print("     锚点: " + ", ".join(f"{p}:{n}" for p, n in d["anchors"][:10]))
        return

    if args.file:
        for key, ds in sorted(decls.items()):
            for d in ds:
                if any(p == args.file for p, _ in d["anchors"]):
                    ls = sorted({n for p, n in d["anchors"] if p == args.file})
                    print(f"{d['round']:6s} {d['cid']:14s} {d['file']}:{d['line']}  行{ls[:8]}")
                    print(f"        {d['text'][:150]}")
        return

    if args.species2:
        # 同一案号多实体:把该号的全部声明位按「锚点文件集是否相交」并成实体组;
        # 只有锚点非空的组才算一个可判定的实体(空锚点的声明位是引用式复述,不单独成实体)。
        rows, n_entities = [], 0
        for key, ds in sorted(decls.items()):
            groups: list[dict] = []
            for d in ds:
                fs = {p for p, _ in d["anchors"]}
                if not fs:
                    continue
                hit = [g for g in groups if g["files"] & fs]
                if hit:
                    merged = hit[0]
                    for g in hit[1:]:
                        merged["files"] |= g["files"]
                        merged["ds"] += g["ds"]
                        groups.remove(g)
                    merged["files"] |= fs
                    merged["ds"].append(d)
                else:
                    groups.append(dict(files=set(fs), ds=[d]))
            if len(groups) >= 2:
                rows.append((key, groups))
                n_entities += len(groups)
        print(f"# 同一案号有 ≥2 个『锚点文件互不相交』的实体组:{len(rows)} 个案号,"
              f"共 {n_entities} 个实体(净多铸 {n_entities - len(rows)} 个)")
        for key, groups in rows:
            print(f"\n== {key}  ({len(groups)} 个实体)")
            for gi, g in enumerate(groups, 1):
                for d in g["ds"]:
                    a = ",".join(sorted({p for p, _ in d["anchors"]}))[:78]
                    print(f"   ({gi}) [{d['round']}] {d['file']}:{d['line']} {d['kind']:10s} {a}")
                    print(f"        {d['text'][:130]}")
        return

    if args.clusters:
        byfile = collections.defaultdict(list)
        for key, ds in decls.items():
            for d in ds:
                for p, n in d["anchors"]:
                    byfile[p].append((n, key, d))
        out = []
        for p, items in byfile.items():
            items.sort(key=lambda t: (t[0], t[1]))
            used = [False] * len(items)
            for i, (n, key, d) in enumerate(items):
                if used[i]:
                    continue
                grp = [(n, key, d)]
                used[i] = True
                for j in range(i + 1, len(items)):
                    if used[j]:
                        continue
                    if abs(items[j][0] - n) <= args.window:
                        grp.append(items[j])
                        used[j] = True
                cases = {g[1] for g in grp}
                rounds = {g[2]["round"] for g in grp}
                if len(cases) >= 2 and len(rounds) >= args.min_rounds:
                    out.append((len(cases), len(rounds), p, grp))
        out.sort(key=lambda t: (-t[1], -t[0], t[2]))
        print(f"# 同一处代码(同文件 ±{args.window} 行)被 ≥2 个案号、跨 ≥{args.min_rounds} 轮声明:"
              f"{len(out)} 簇")
        if args.summary:
            return
        for ncase, nround, p, grp in out:
            lines = sorted({g[0] for g in grp})
            print(f"\n== {p}  行{lines[:8]}  案号{ncase} 轮次{nround}")
            seen = set()
            for n, key, d in grp:
                sig = (key, d["file"], d["line"])
                if sig in seen:
                    continue
                seen.add(sig)
                print(f"   [{d['round']:6s}] {d['cid']:14s} {d['file']}:{d['line']}  ->{n}")
                print(f"        {d['text'][:130]}")
        return

    fam = collections.Counter()
    per_round = collections.Counter()
    for key, ds in decls.items():
        fam[ds[0]["fam"]] += 1
        per_round[min(d["round"] for d in ds)] += 1
    print(f"语料面 {CORPUS_DIRS};文件数 {len(list(iter_files(CORPUS_DIRS)))}")
    print(f"案号(作用域后)总数 {len(decls)};声明位总数 {sum(len(v) for v in decls.values())}")
    for f_, lab in (("H", "H  移交号"), ("G", "G  全局定案号"),
                    ("S", "S  片内定案号"), ("L", "L  轮内裸序号")):
        print(f"   {lab}: {fam[f_]}")
    if args.summary:
        return
    print("按首次出现轮次:")
    for r, c in sorted(per_round.items()):
        print(f"   {r:8s} {c}")


if __name__ == "__main__":
    sys.exit(main())
