#!/usr/bin/env python3
"""把全语料**未配对**的只读 ```verify 块真跑一遍,只看「还跑不跑得通」。

为什么这个测量有意义:配对块比对输出,未配对块**一次都没被执行过**。于是有两种
失败,关卡对第二种完全无感:

  (a) 命令跑得通但输出与贴的不一致 —— 只有配对块查得到(R10B 立本关卡的动机)
  (b) 命令**根本跑不通**(路径没了、拼写错、依赖没装) —— 配对与否都没查过,
      而它是对「重跑能复现该结论的那一条命令」这条规矩更彻底的违反

分型见 evidence_block_profile.py;本探针只跑 READONLY 那一型,MUTATING 一律不跑
(语料里真有 `npm install --workspace` 打进基线的命令)。

跑之前与跑之后各记一次基线 `git status --porcelain` 的行数,任何变动都会被报出来。

用法:python3 data/r11b/probes/evidence_runnability_sweep.py [--timeout 60] [--jobs 8] [--out FILE]
"""
import concurrent.futures as cf
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(subprocess.run(["git", "-C", str(Path(__file__).resolve().parent),
                            "rev-parse", "--show-toplevel"],
                           capture_output=True, check=True).stdout.decode().strip())
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify_evidence_commands import PAIR, ANY_VERIFY  # noqa: E402
from evidence_block_profile import classify  # noqa: E402

BASELINE = Path("/home/user/hermes-agent")
SCOPE = ("notes", "chapters", "reports", "reviews", "data")


def baseline_dirt() -> int:
    if not BASELINE.is_dir():
        return -1
    out = subprocess.run(["git", "-C", str(BASELINE), "status", "--porcelain"],
                         capture_output=True).stdout.decode()
    return len([x for x in out.splitlines() if x.strip()])


def collect():
    items = []
    for d in SCOPE:
        for p in sorted((ROOT / d).rglob("*.md")):
            t = p.read_text(encoding="utf-8", errors="replace")
            paired = {m.group("cmd") for m in PAIR.finditer(t)}
            for m in ANY_VERIFY.finditer(t):
                body = m.group(0)[len("```verify\n"):-3]
                if body in paired:
                    continue
                kind, _ = classify(body)
                if kind == "READONLY":
                    items.append((p.relative_to(ROOT).as_posix(), body))
    return items


def run_one(item, timeout):
    name, cmd = item
    try:
        r = subprocess.run(["bash", "-c", cmd], cwd=ROOT, capture_output=True,
                           timeout=timeout)
        return name, r.returncode, (r.stderr.decode(errors="replace").strip()
                                    .splitlines() or [""])[-1][:160], cmd
    except subprocess.TimeoutExpired:
        return name, "TIMEOUT", "", cmd
    except Exception as exc:  # noqa: BLE001
        return name, "ERROR", str(exc)[:160], cmd


def main(argv: list[str]) -> int:
    timeout = int(argv[argv.index("--timeout") + 1]) if "--timeout" in argv else 60
    jobs = int(argv[argv.index("--jobs") + 1]) if "--jobs" in argv else 8
    out = argv[argv.index("--out") + 1] if "--out" in argv else None

    before = baseline_dirt()
    items = collect()
    results = []
    with cf.ThreadPoolExecutor(max_workers=jobs) as ex:
        for r in ex.map(lambda i: run_one(i, timeout), items):
            results.append(r)
    after = baseline_dirt()

    ok = [r for r in results if r[1] == 0]
    nonzero = [r for r in results if isinstance(r[1], int) and r[1] != 0]
    timed = [r for r in results if r[1] == "TIMEOUT"]
    err = [r for r in results if r[1] == "ERROR"]

    if out:
        # 语料里有历史底稿把**会话专属 scratchpad 路径(含会话标识)**写进了命令。
        # 把失败明细原样落库,就等于把那些标识**再抄一遍进仓库**——正是本项目边界
        # 「不把任何会话信息写入仓库产物」禁止的事。所以落库前先抹掉。
        # (这条是本轮自己踩出来的:初版明细文件带进了 10 处会话标识。)
        redact = re.compile(r"/tmp/claude-[0-9]+/-home-user-hermes-study/[0-9a-f-]{8,}")
        with open(out, "w", encoding="utf-8") as fh:
            for name, rc, tail, cmd in sorted(results, key=lambda x: str(x[1])):
                if rc == 0:
                    continue
                line = f"[{rc}] {name}\t{tail}\t{' '.join(cmd.split())[:200]}\n"
                fh.write(redact.sub("/tmp/claude-<session>", line))

    print(f"readonly_unpaired={len(items)} exit0={len(ok)} nonzero={len(nonzero)} "
          f"timeout={len(timed)} error={len(err)}")
    print(f"baseline_porcelain_before={before} after={after} "
          f"{'CLEAN' if before == after else '*** BASELINE CHANGED ***'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
