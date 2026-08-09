#!/usr/bin/env python3
"""R11A 片B 探针:枚举 .github/workflows/ 全部 workflow 的 name / 触发器 / job 数。

只读解析,不执行任何 workflow。用法:

    python3 data/r11a/probes/probe_b_workflows.py /home/user/hermes-agent

输出 TSV:file<TAB>name<TAB>triggers<TAB>n_jobs<TAB>job_ids
注意 YAML 1.1 把裸 `on:` 解析成布尔 True,这里两种键都认。
"""
import sys
from pathlib import Path

import yaml


def triggers_of(doc):
    on = doc.get("on", doc.get(True))
    if on is None:
        return []
    if isinstance(on, str):
        return [on]
    if isinstance(on, list):
        return list(on)
    return list(on.keys())


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "/home/user/hermes-agent")
    wf_dir = root / ".github" / "workflows"
    rows = []
    for p in sorted(wf_dir.iterdir()):
        if p.suffix not in (".yml", ".yaml"):
            continue
        doc = yaml.safe_load(p.read_text(encoding="utf-8"))
        jobs = doc.get("jobs") or {}
        rows.append((p.name, str(doc.get("name", "")), ",".join(triggers_of(doc)),
                     len(jobs), ",".join(jobs.keys())))
    only = sys.argv[2] if len(sys.argv) > 2 else ""
    if only == "--count":
        print(f"{len(rows)} workflows / {sum(r[3] for r in rows)} jobs")
        return 0
    if only == "--gate-gap":
        # ci.yml 里「以 uses: 调用子 workflow」的 job,有哪些没进
        # all-checks-pass 的 needs —— 即分支保护那一个必需检查看不到它们。
        doc = yaml.safe_load((wf_dir / "ci.yml").read_text(encoding="utf-8"))
        jobs = doc["jobs"]
        gate = set(jobs["all-checks-pass"]["needs"])
        called = {k for k, v in jobs.items() if "uses" in v}
        print("called-but-not-in-gate:", " ".join(sorted(called - gate)))
        return 0
    if only == "--brief":
        print("file\tname\ttriggers\tn_jobs")
        for r in rows:
            print(f"{r[0]}\t{r[1]}\t{r[2]}\t{r[3]}")
        return 0
    print("file\tname\ttriggers\tn_jobs\tjob_ids")
    for r in rows:
        print("\t".join(str(x) for x in r))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
