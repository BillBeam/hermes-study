#!/usr/bin/env python3
"""R11A 片A — flake 对外输出面的机械枚举。

本容器**没有 nix**(`command -v nix` 无输出),所以无法用 `nix flake show` 求值枚举。
退而求其次:按 flake-parts 的写法在源文件里做**结构化文本抽取**——

  * `packages` / `checks` / `devShells`:找到形如 `<name> = {` 的块起始行,
    再收集**恰好比它多一层缩进**的属性名(避开块内嵌套 let 里的绑定)。
  * `flake.overlays.<x>` / `flake.nixosModules.<x>`:flake-parts 里这两个是
    顶层平铺写法,直接按前缀抓。
  * NixOS 模块选项:`<name> = mkOption {` / `mkEnableOption`,按缩进分顶层与
    `container.*` 子块。

局限要如实说:这是**文本抽取**,不是求值。一个用 `//` 或 `lib.optionalAttrs`
动态拼进去的输出,这里看不见。已知的一处动态项是
`nix/packages.nix` 里 `full = minimal.override {...}` 这类 let 绑定——它不是输出,
不该被抓,而本脚本按"块内恰好一层缩进"的规则确实不会抓它。

用法:
    python3 data/r11a/probes/probe_a_nix_surface.py /home/user/hermes-agent
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ATTR = re.compile(r"^(?P<indent> *)(?P<name>[A-Za-z_][A-Za-z0-9_'-]*) =(?: |$)")
INHERIT = re.compile(r"^(?P<indent> *)inherit (?P<names>[A-Za-z_][A-Za-z0-9_' -]*);")
BLOCK_OPEN = re.compile(r"^(?P<indent> *)(?P<name>[A-Za-z_][A-Za-z0-9_.'-]*) = (let )?\{\s*$")


def block_attrs(path: Path, block_name: str) -> list[str]:
    """属性名列表:`block_name = {` 块里恰好深一层的 `x = ...`。"""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    out: list[str] = []
    depth = None
    base_indent = None
    for line in lines:
        if depth is None:
            m = BLOCK_OPEN.match(line)
            if m and m.group("name") == block_name:
                base_indent = len(m.group("indent"))
                depth = 1
            continue
        depth += line.count("{") - line.count("}")
        if depth <= 0:
            break
        m = ATTR.match(line)
        if m and len(m.group("indent")) == base_indent + 2:
            out.append(m.group("name"))
            continue
        # `inherit sandbox;` 也是一条输出(与 `sandbox = sandbox;` 等价)
        mi = INHERIT.match(line)
        if mi and len(mi.group("indent")) == base_indent + 2:
            out.extend(mi.group("names").split())
    return out


def prefixed(root: Path, prefix: str) -> list[str]:
    hits: list[str] = []
    for p in sorted(root.glob("nix/*.nix")) + [root / "flake.nix"]:
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.match(r"^\s*" + re.escape(prefix) + r"([A-Za-z0-9_-]+)\s*=", line)
            if m:
                hits.append(f"{p.relative_to(root)}:{m.group(1)}")
    return hits


def nixos_options(path: Path) -> tuple[list[str], list[str]]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    top: list[str] = []
    container: list[str] = []
    in_container = False
    for line in lines:
        m = re.match(r"^(?P<i> *)(?P<n>[A-Za-z][A-Za-z0-9_]*) = mk(Option|EnableOption)", line)
        if re.match(r"^ {6}container = \{\s*$", line):
            in_container = True
            continue
        if m:
            indent = len(m.group("i"))
            if indent == 6:
                in_container = False
                top.append(m.group("n"))
            elif indent == 8 and in_container:
                container.append(m.group("n"))
    return top, container


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "/home/user/hermes-agent")

    pkgs = block_attrs(root / "nix/packages.nix", "packages")
    extra_pkg = [
        m.group(1)
        for m in re.finditer(
            r"^\s*packages\.([A-Za-z0-9_-]+) = ",
            (root / "nix/checks.nix").read_text(encoding="utf-8"),
            re.M,
        )
    ]
    checks = block_attrs(root / "nix/checks.nix", "checks")
    # checks 块被 `} // lib.optionalAttrs pkgs.stdenv.hostPlatform.isLinux {` 一分为二:
    # 之前的是三系统都建,之后的只在 Linux 建。
    checks_text = (root / "nix/checks.nix").read_text(encoding="utf-8").splitlines()
    split_at = next(
        i for i, ln in enumerate(checks_text, 1)
        if "lib.optionalAttrs pkgs.stdenv.hostPlatform.isLinux" in ln
    )
    all_sys = [c for c in checks
               if next(i for i, ln in enumerate(checks_text, 1)
                       if re.match(r"^ {8}" + re.escape(c) + r" = ", ln)) < split_at]
    shells = prefixed(root, "devShells.")
    overlays = prefixed(root, "flake.overlays.")
    modules = prefixed(root, "flake.nixosModules.")
    top, container = nixos_options(root / "nix/nixosModules.nix")

    systems = re.findall(r'"([a-z0-9_]+-[a-z]+)"', re.search(
        r"systems = \[(.*?)\];", (root / "flake.nix").read_text(encoding="utf-8"), re.S).group(1))

    print(f"systems ({len(systems)}): " + " ".join(systems))
    print(f"packages ({len(pkgs) + len(extra_pkg)}): " + " ".join(pkgs + extra_pkg))
    print(f"checks ({len(checks)}): " + " ".join(checks))
    print(f"  其中三系统都建 ({len(all_sys)}): " + " ".join(all_sys))
    print(f"  其中仅 Linux ({len(checks) - len(all_sys)}, 见 nix/checks.nix:{split_at}): "
          + " ".join(c for c in checks if c not in all_sys))
    print(f"devShells ({len(shells)}): " + " ".join(shells))
    print(f"overlays ({len(overlays)}): " + " ".join(overlays))
    print(f"nixosModules ({len(modules)}): " + " ".join(modules))
    print(f"services.hermes-agent 顶层选项 ({len(top)}): " + " ".join(top))
    print(f"services.hermes-agent.container.* ({len(container)}): " + " ".join(container))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
