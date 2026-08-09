#!/usr/bin/env python3
"""R10B 片G 探针:枚举 apps/desktop/src/components/ui/ 的对外接缝。

用法(在 hermes-agent 基线根目录之外任何位置均可):

    python3 data/r10b/probes/probe_g_ui_surface.py /home/user/hermes-agent [--tsv]

对每个 ui/*.{ts,tsx}(排除 *.test.*)输出:
  - 该文件导出的每一个符号(inline export + 尾部 `export { ... }`)
  - 每个导出的 React 组件的 props 类型注解原文(经空白归一)
  - props 注解的分类:passthrough(ComponentProps<...>) / named(具名 interface/type)
    / inline(内联对象字面量) / none(无参)

纯文本解析,不 import、不执行任何被测代码。
"""

import re
import sys
from pathlib import Path

UI_REL = "apps/desktop/src/components/ui"


def strip_comments(src: str) -> str:
    """把注释替换成等长空格,保持偏移量不变。"""
    out = list(src)
    i, n = 0, len(src)
    state = None  # None | 'line' | 'block' | 'sq' | 'dq' | 'tpl'
    while i < n:
        c = src[i]
        nxt = src[i + 1] if i + 1 < n else ""
        if state is None:
            if c == "/" and nxt == "/":
                state = "line"
                out[i] = out[i + 1] = " "
                i += 2
                continue
            if c == "/" and nxt == "*":
                state = "block"
                out[i] = out[i + 1] = " "
                i += 2
                continue
            if c == "'":
                state = "sq"
            elif c == '"':
                state = "dq"
            elif c == "`":
                state = "tpl"
            i += 1
            continue
        if state == "line":
            if c == "\n":
                state = None
            else:
                out[i] = " "
            i += 1
            continue
        if state == "block":
            if c == "*" and nxt == "/":
                out[i] = out[i + 1] = " "
                state = None
                i += 2
                continue
            if c != "\n":
                out[i] = " "
            i += 1
            continue
        # inside a string literal
        if c == "\\":
            i += 2
            continue
        if (state == "sq" and c == "'") or (state == "dq" and c == '"') or (state == "tpl" and c == "`"):
            state = None
        i += 1
    return "".join(out)


def match_balanced(src: str, start: int, open_ch: str, close_ch: str) -> int:
    """src[start] == open_ch;返回匹配的 close_ch 的下标,失败返回 -1。"""
    depth = 0
    i = start
    n = len(src)
    while i < n:
        c = src[i]
        if c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def split_top_level_colon(params: str) -> str:
    """取参数列表里顶层第一个 `:` 之后的部分(= 类型注解)。"""
    depth = 0
    for i, c in enumerate(params):
        if c in "([{<":
            depth += 1
        elif c in ")]}>":
            depth -= 1
        elif c == ":" and depth == 0:
            return params[i + 1 :].strip()
    return ""


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def classify(annotation: str) -> str:
    if not annotation:
        return "none"
    a = annotation
    if a.startswith("{"):
        return "inline"
    if "ComponentProps<" in a and not re.match(r"^[A-Z][A-Za-z0-9_]*(\s|$)", a):
        return "passthrough"
    if re.match(r"^[A-Z][A-Za-z0-9_]*$", a):
        return "named"
    return "mixed"


def interface_fields(body: str) -> list:
    """从 interface/type 体里抠出顶层字段名。

    注意:尖括号**不计入深度**。`onClose?: () => void` 里的 `>` 若被当成收括号,
    深度会掉到 -1,其后所有字段都不再被切分——这正是初版漏掉
    `PaneTabProps.selected/vertical/side` 的原因。
    """
    fields = []
    depth = 0
    token = ""
    for c in body:
        if c in "({[":
            depth += 1
        elif c in ")}]":
            depth -= 1
        if depth == 0 and c in ";\n,":
            m = re.match(r"\s*(?:readonly\s+)?\[?'?([A-Za-z_$][\w$]*)'?\]?\s*\??\s*:", token)
            if m:
                fields.append(m.group(1) + ("?" if "?" in token.split(":")[0] else ""))
            token = ""
        else:
            token += c
    m = re.match(r"\s*(?:readonly\s+)?\[?'?([A-Za-z_$][\w$]*)'?\]?\s*\??\s*:", token)
    if m:
        fields.append(m.group(1) + ("?" if "?" in token.split(":")[0] else ""))
    return fields


def analyze(path: Path):
    raw = path.read_text(encoding="utf-8")
    src = strip_comments(raw)

    # --- exported names -----------------------------------------------------
    exported = []
    for m in re.finditer(
        r"^export\s+(?:declare\s+)?(function|const|let|class|interface|type|enum)\s+([A-Za-z_$][\w$]*)",
        src,
        re.M,
    ):
        exported.append((m.group(2), m.group(1)))
    for m in re.finditer(r"^export\s*\{([^}]*)\}", src, re.M):
        for part in m.group(1).split(","):
            part = part.strip()
            if not part:
                continue
            part = re.sub(r"^type\s+", "", part)
            name = part.split(" as ")[-1].strip()
            if name:
                exported.append((name, "re-export"))

    # --- interfaces / type aliases -----------------------------------------
    ifaces = {}
    for m in re.finditer(r"\b(?:export\s+)?interface\s+([A-Za-z_$][\w$]*)([^{]*)\{", src):
        end = match_balanced(src, src.index("{", m.end() - 1), "{", "}")
        if end > 0:
            own = interface_fields(src[m.end() : end])
            ext = norm(m.group(2))
            if ext.startswith("extends"):
                own = own + [f"<{ext}>"]
            ifaces[m.group(1)] = own
    # `type X = A & B & { … }` — 交叉类型里的对象字面量也要抠字段(Input 就是这种)。
    for m in re.finditer(r"\b(?:export\s+)?type\s+([A-Za-z_$][\w$]*)\s*=", src):
        rest = src[m.end() :]
        # 括号深度为 0 且下一行**顶格**(第 0 列非空白)才算声明结束。用空行判界
        # 会被剥注释后留下的整行空白骗到(Input 的 JSDoc 就是这样把 RHS 截断的)。
        depth = 0
        cut = len(rest)
        for i, c in enumerate(rest):
            if c in "({[":
                depth += 1
            elif c in ")}]":
                depth -= 1
            elif c == "\n" and depth == 0 and i + 1 < len(rest) and not rest[i + 1].isspace():
                cut = i
                break
        rhs = rest[:cut]
        own = []
        pos = 0
        while True:
            brace = rhs.find("{", pos)
            if brace < 0:
                break
            end = match_balanced(rhs, brace, "{", "}")
            if end < 0:
                break
            own += interface_fields(rhs[brace + 1 : end])
            pos = end + 1
        head = norm(re.sub(r"\{[^{}]*\}", "{…}", rhs))
        ifaces[m.group(1)] = own + ([f"<= {head}>"] if not own or "&" in head else [])

    # --- function components ------------------------------------------------
    comps = []
    seen = set()
    for m in re.finditer(r"\bfunction\s+([A-Za-z_$][\w$]*)\s*(?:<[^(]*?>)?\s*\(", src):
        name = m.group(1)
        paren = src.rindex("(", m.start(), m.end())
        close = match_balanced(src, paren, "(", ")")
        if close < 0:
            continue
        params = src[paren + 1 : close]
        ann = split_top_level_colon(params)
        line = src[:paren].count("\n") + 1
        # `React.forwardRef<El, Props>(function Name(...))`: the props type is
        # the SECOND generic argument, not an annotation on the parameter.
        fwd = re.search(
            r"forwardRef\s*<\s*[^,<>]*,\s*([A-Za-z_$][\w$]*)\s*>\s*\(\s*$",
            src[max(0, m.start() - 200) : m.start()],
        )
        if not ann and fwd:
            ann = fwd.group(1)
        comps.append((name, norm(ann), classify(norm(ann)), line))
        seen.add(name)

    # `const Name = (props: X) => …` / `const Name = memo(Impl)` arrow forms.
    for m in re.finditer(r"\bconst\s+([A-Za-z_$][\w$]*)\s*(?::\s*[^=]+)?=\s*(?:memo\s*\()?\(", src):
        name = m.group(1)
        if name in seen:
            continue
        paren = src.rindex("(", m.start(), m.end())
        close = match_balanced(src, paren, "(", ")")
        if close < 0:
            continue
        tail = src[close + 1 : close + 40]
        if "=>" not in tail:
            continue
        ann = split_top_level_colon(src[paren + 1 : close])
        comps.append((name, norm(ann), classify(norm(ann)), src[:paren].count("\n") + 1))
        seen.add(name)

    # `const Name = memo(Impl, cmp)` — resolve to the impl's own annotation.
    for m in re.finditer(r"\bconst\s+([A-Za-z_$][\w$]*)\s*=\s*memo\s*\(\s*([A-Za-z_$][\w$]*)", src):
        name, impl = m.group(1), m.group(2)
        if name in seen:
            continue
        hit = next((c for c in comps if c[0] == impl), None)
        comps.append((name, hit[1] if hit else f"memo({impl})", hit[2] if hit else "mixed",
                      src[: m.start()].count("\n") + 1))
        seen.add(name)

    return exported, ifaces, comps


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    root = Path(sys.argv[1])
    tsv = "--tsv" in sys.argv
    ui = root / UI_REL
    files = sorted(p for p in ui.iterdir() if p.suffix in {".ts", ".tsx"} and ".test." not in p.name)

    total_exports = 0
    total_comps = 0
    for path in files:
        exported, ifaces, comps = analyze(path)
        names = sorted({n for n, _ in exported})
        total_exports += len(names)
        exported_comps = [c for c in comps if c[0] in names]
        total_comps += len(exported_comps)
        if tsv:
            for cname, ann, kind, line in exported_comps:
                fields = ",".join(ifaces.get(ann, [])) if kind == "named" else ""
                print(f"{path.name}\t{cname}\t{kind}\t{ann}\t{fields}")
        else:
            print(f"== {path.name}  exports={len(names)}  components={len(exported_comps)}")
            print("   exports: " + ", ".join(names))
            for cname, ann, kind, line in exported_comps:
                extra = ""
                if kind == "named" and ann in ifaces:
                    extra = "  fields=[" + ", ".join(ifaces[ann]) + "]"
                print(f"   - {cname} :{line}  [{kind}] {ann}{extra}")
    print(f"\nFILES={len(files)} EXPORTED_NAMES={total_exports} EXPORTED_COMPONENTS={total_comps}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
