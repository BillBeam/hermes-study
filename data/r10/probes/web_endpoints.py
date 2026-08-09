#!/usr/bin/env python3
"""R10 · G 片探针:机械枚举 dashboard 前端(web/)引用的 HTTP 端点。

用法(在基线仓库根下跑):
    cd /home/user/hermes-agent
    python3 /home/user/hermes-study/data/r10/probes/web_endpoints.py web/src/lib/api.ts
    python3 /home/user/hermes-study/data/r10/probes/web_endpoints.py $(ls web/src/**/*.ts*)

为什么不是一条 grep:`api.ts` 里的 URL 是模板字符串,而模板字符串的
``${...}`` 里可以再嵌引号(例:``/api/hermes/update/check${force ? "?force=true" : ""}``)。
按引号配对的正则会在内层那个 ``"`` 上截断,于是那一条端点被读成
``/api/hermes/update/check${force``。所以这里做了一个最小的字符串/模板字面量
分词器(跟踪 ``${`` 的花括号深度),而不是正则。

判定规则:
  * 收集每一个字符串/模板字面量,其内容(可含前缀 ``${BASE}``)以
    ``/api`` / ``/auth`` / ``/dashboard-plugins`` 开头;
  * 跳过 ``//`` 与 ``/* */`` 注释里的;
  * 跳过 ``PROFILE_SCOPED_PREFIXES`` 那张前缀表(它是前缀表,不是调用);
  * 方法:从该字面量往后扫到**下一个**同类字面量为止,取 ``method: "X"``,
    取不到记 GET(fetch 默认);
  * ``${...}`` 归一化为 ``{}``;紧贴在路径段后面(前面不是 ``/``)的 ``{}``
    是 query/后缀插值(如 ``/api/skills${profileQuery(p)}``),剥掉;
    前面是 ``/`` 的 ``{}`` 是路径参数(如 ``/api/cron/jobs/${id}``),保留。
  * 含空格或 ``:`` 的结果标 ``<<not-a-path>>``——那是错误信息文案,不是端点
    (``api.ts:208`` 的 ``/api/auth/ws-ticket: HTTP ${res.status}`` 就是这一条)。
"""
import re
import sys


def scan_strings(src):
    """产出 (start, end, kind, text):每一个字符串 / 模板字面量。"""
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if c == "/" and i + 1 < n and src[i + 1] == "/":
            j = src.find("\n", i)
            i = n if j < 0 else j + 1
            continue
        if c == "/" and i + 1 < n and src[i + 1] == "*":
            j = src.find("*/", i)
            i = n if j < 0 else j + 2
            continue
        if c in "\"'":
            j = i + 1
            while j < n:
                if src[j] == "\\":
                    j += 2
                    continue
                if src[j] == c or src[j] == "\n":
                    break
                j += 1
            yield (i, j + 1, c, src[i + 1 : j])
            i = j + 1
            continue
        if c == "`":
            j = i + 1
            depth = 0
            while j < n:
                if src[j] == "\\":
                    j += 2
                    continue
                if src[j] == "$" and j + 1 < n and src[j + 1] == "{":
                    depth += 1
                    j += 2
                    continue
                if depth > 0:
                    if src[j] == "{":
                        depth += 1
                    elif src[j] == "}":
                        depth -= 1
                    j += 1
                    continue
                if src[j] == "`":
                    break
                j += 1
            yield (i, j + 1, "`", src[i + 1 : j])
            i = j + 1
            continue
        i += 1


METHOD = re.compile(r'method:\s*"([A-Z]+)"')
PREFIX_RE = re.compile(r"^(?:\$\{BASE\})?(/api|/auth|/dashboard-plugins)")

all_rows = []
for path in sys.argv[1:]:
    src = open(path, encoding="utf-8").read()
    lines = src.split("\n")
    starts, off = [], 0
    for ln in lines:
        starts.append(off)
        off += len(ln) + 1

    def lineno(pos):
        lo, hi = 0, len(starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if starts[mid] <= pos:
                lo = mid
            else:
                hi = mid - 1
        return lo + 1

    tbl = re.search(r"const PROFILE_SCOPED_PREFIXES = \[(.*?)\];", src, re.S)
    tbl_range = (tbl.start(), tbl.end()) if tbl else (-1, -1)

    hits = [t for t in scan_strings(src) if PREFIX_RE.match(t[3])]
    hits = [h for h in hits if not (tbl_range[0] <= h[0] <= tbl_range[1])]
    for i, (s, e, _kind, text) in enumerate(hits):
        nxt = hits[i + 1][0] if i + 1 < len(hits) else len(src)
        window = src[e : min(nxt, e + 800)]
        mm = METHOD.search(window)
        method = mm.group(1) if mm else "GET"
        p = text
        if p.startswith("${BASE}"):
            p = p[len("${BASE}") :]
        p = re.sub(r"\$\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", "{}", p)
        p = p.split("?")[0]
        p = re.sub(r"\{\}(\{\})+", "{}", p)
        while re.search(r"[^/{}]\{\}$", p):
            p = p[:-2]
        if " " in p or ":" in p:
            p = "<<not-a-path>> " + p
        all_rows.append((method, p.rstrip("/") or "/", lineno(s), path))

seen = {}
for method, p, ln, path in all_rows:
    seen.setdefault((method, p), []).append((path, ln))

real = [k for k in seen if not k[1].startswith("<<")]
for (method, p), locs in sorted(seen.items(), key=lambda kv: (kv[0][1], kv[0][0])):
    where = " ".join(f"{pa}:{l}" for pa, l in locs)
    print(f"{method:7s} {p:52s} {where}")
print()
print(f"literal call sites : {len(all_rows)}")
print(f"distinct endpoints : {len(real)}")
print(f"not-a-path strings : {len(seen) - len(real)}")
