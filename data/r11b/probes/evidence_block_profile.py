#!/usr/bin/env python3
"""给全语料的 ```verify 块分型:哪些能安全重跑、哪些根本跑不了。

「把配对率从 18.9% 提上去」这个提法预设了未配对块都**能**被钉输出。本探针
去查这个前提是否成立,分四型:

  MUTATING   命令会改基线 / 装包 / 写文件 —— 关卡**不该**自动跑它
  DEADPATH   命令引用了会话专属绝对路径,而该路径此刻不存在 —— 它已经复现不了任何东西
  READONLY   只读且路径可解析 —— 这一型才是「跑一遍看它还跑不跑得通」的可得覆盖面
  OTHER      解析不出上述特征

用法:python3 data/r11b/probes/evidence_block_profile.py [--list <TYPE>]
不依赖会话专属路径:仓库根从本文件位置推出。
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(subprocess.run(["git", "-C", str(Path(__file__).resolve().parent),
                            "rev-parse", "--show-toplevel"],
                           capture_output=True, check=True).stdout.decode().strip())
sys.path.insert(0, str(ROOT / "scripts"))
from verify_evidence_commands import PAIR, ANY_VERIFY  # noqa: E402

SCOPE = ("notes", "chapters", "reports", "reviews", "data")

# 只认**命令位置**上的这些词(行首或管道/分号/&& 之后),避免把 grep 模式里的
# 同名字符串误判成动作 —— 初版没加这条限制,`grep -rn "curl"` 被算成了外网请求。
MUTATE = re.compile(
    r"(?:^|[|;&]\s*|\$\(\s*)(?:sudo\s+)?"
    r"(?:pip3?\s+install|apt(?:-get)?\s+install|npm\s+(?:i|ci|install)|yarn\s+add"
    r"|pnpm\s+(?:i|add|install)|cargo\s+(?:install|build)|go\s+install"
    r"|rm\s+-|mv\s+|cp\s+|chmod\s+|chown\s+|tee\s+|mkdir\s+"
    r"|git\s+(?:commit|push|checkout|clean|reset|apply|rm)"
    r"|curl\s|wget\s)", re.M)
REDIRECT_WRITE = re.compile(r"(?<![0-9<>])>\s*(?!/dev/null)[^\s|&;]+")
ABSPATH = re.compile(r"(?<![\w=])/(?:home|tmp|var|opt|root|mnt)/[A-Za-z0-9_./-]+")


def classify(cmd: str):
    if MUTATE.search(cmd) or REDIRECT_WRITE.search(cmd):
        return "MUTATING", ""
    dead = []
    for m in ABSPATH.finditer(cmd):
        p = m.group(0).rstrip(".,:;\"'")
        # 只判「路径前缀」是否存在:命令里常带 glob 或后续参数
        probe = p
        while probe and not Path(probe).exists() and "/" in probe.rstrip("/"):
            probe = probe.rsplit("/", 1)[0]
        if probe in ("", "/home", "/tmp", "/var", "/opt", "/root", "/mnt"):
            dead.append(p)
    if dead:
        return "DEADPATH", ";".join(sorted(set(dead))[:3])
    if ABSPATH.search(cmd) or cmd.strip():
        return "READONLY", ""
    return "OTHER", ""


def main(argv: list[str]) -> int:
    want = argv[argv.index("--list") + 1] if "--list" in argv else None
    counts = {"MUTATING": 0, "DEADPATH": 0, "READONLY": 0, "OTHER": 0}
    pcounts = dict(counts)
    listed = []
    for d in SCOPE:
        for p in sorted((ROOT / d).rglob("*.md")):
            t = p.read_text(encoding="utf-8", errors="replace")
            paired = {m.group("cmd") for m in PAIR.finditer(t)}
            for m in ANY_VERIFY.finditer(t):
                body = m.group(0)[len("```verify\n"):-3]
                kind, why = classify(body)
                if body in paired:
                    pcounts[kind] += 1
                else:
                    counts[kind] += 1
                    if want and kind == want:
                        listed.append((p.name, why, " ".join(body.split())[:100]))
    for name, why, c in listed[:40]:
        print(f"  {name} [{why}] {c}")
    print("未配对块分型: " + "  ".join(f"{k}={v}" for k, v in counts.items())
          + f"  合计={sum(counts.values())}")
    print("已配对块分型: " + "  ".join(f"{k}={v}" for k, v in pcounts.items())
          + f"  合计={sum(pcounts.values())}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
