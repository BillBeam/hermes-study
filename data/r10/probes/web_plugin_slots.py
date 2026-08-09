#!/usr/bin/env python3
"""R10 · G 片探针:比对 dashboard 前端「声明的插槽名」与「实际渲染的插槽名」。

用法(在基线仓库根下跑):
    cd /home/user/hermes-agent
    python3 /home/user/hermes-study/data/r10/probes/web_plugin_slots.py

  * 声明面 = ``web/src/plugins/slots.ts`` 的 ``KNOWN_SLOT_NAMES`` 数组字面量;
  * 渲染面 = 全 ``web/src`` 里 ``<PluginSlot name="..." />`` 的字面量
    (排除 ``slots.ts`` 自己的 docstring 示例与 ``*.test.tsx``);
  * 全仓不存在 ``<PluginSlot name={...}>`` 这种动态名(脚本会报出来),
    所以「渲染面」这个集合是完备的,不是抽样。
"""
import re
import pathlib

ROOT = pathlib.Path(".")
slots_src = (ROOT / "web/src/plugins/slots.ts").read_text(encoding="utf-8")
m = re.search(r"export const KNOWN_SLOT_NAMES = \[(.*?)\] as const;", slots_src, re.S)
declared = re.findall(r'"([^"]+)"', m.group(1))

rendered = {}
dynamic = []
for p in sorted(ROOT.glob("web/src/**/*.ts*")):
    if ".test." in p.name or p.as_posix().endswith("plugins/slots.ts"):
        continue
    text = p.read_text(encoding="utf-8")
    for mo in re.finditer(r'<PluginSlot\s+name="([^"]+)"', text):
        ln = text[: mo.start()].count("\n") + 1
        rendered.setdefault(mo.group(1), []).append(f"{p.as_posix()}:{ln}")
    for mo in re.finditer(r"<PluginSlot\s+name=\{", text):
        ln = text[: mo.start()].count("\n") + 1
        dynamic.append(f"{p.as_posix()}:{ln}")

d, r = set(declared), set(rendered)
print(f"KNOWN_SLOT_NAMES declared : {len(declared)}")
print(f"rendered slot names       : {len(r)}")
print(f"dynamic <PluginSlot name={{...}}> sites : {len(dynamic)} {dynamic}")
print()
print("declared but NEVER rendered:")
for n in sorted(d - r):
    print(f"  - {n}")
print("rendered but NOT declared:")
for n in sorted(r - d):
    print(f"  - {n}   {' '.join(rendered[n])}")

# ── 第三面:website/docs 的插槽目录 ────────────────────────────────────
doc = ROOT / "website/docs/user-guide/features/extending-the-dashboard.md"
src = doc.read_text(encoding="utf-8")
seg = src[src.index("#### Slot catalogue") : src.index("#### Re-registration")]
documented = set()
for row in re.findall(r"^\|\s*`([^`]+)`\s*(?:/\s*`([^`]+)`\s*)?\|", seg, re.M):
    documented.update(n for n in row if n)
print()
print(f"website/docs slot catalogue : {len(documented)}")
print("documented but NEVER rendered:", sorted(documented - r))
print("rendered but NOT documented :", sorted(r - documented))
