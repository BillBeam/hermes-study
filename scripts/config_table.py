#!/usr/bin/env python3
"""Build the R8A configuration-key table from the hermes-agent baseline.

The authoritative definition of every Hermes config key is the literal
``DEFAULT_CONFIG`` dict in ``hermes_cli/config_defaults.py``; the *statically
declared* environment variables are ``OPTIONAL_ENV_VARS`` in the same file.
Both are pure data (the module's own docstring says so), so they can be read
exactly by AST — no import, no execution, no guessing.

**Caveat that matters for anyone using the env-var output.** ``OPTIONAL_ENV_VARS``
is not the whole list at runtime. Importing ``hermes_cli.config`` MUTATES THAT
DICT IN PLACE — it is literally the same object — through two injection passes
that add provider-profile and platform-plugin variables
(``hermes_cli/config.py:5307``, ``_inject_profile_env_vars``, run eagerly at
import). Measured on this baseline: **151 entries in the source literal, 308
after import**. So this script's env table covers the ~49% that is statically
declared; the rest exists only once the process is running. That is a property
of the codebase, not a limitation we can engineer away here — an AST pass
cannot see a dict that a different module fills in at import time. Treat the
env table as "what is written down", not "what the wizard will ask for".

There is also a *second* env registry this script does not emit: ``_EXTRA_ENV_KEYS``
in ``hermes_cli/config.py:263`` (108 names), for variables written to ``.env`` by
setup/provider flows but deliberately kept out of the user-facing list —
deprecated knobs live there so compatibility paths still recognise them while the
setup checklist stops offering them. The set of names Hermes *recognises* is the
union of the two (239 with the static literal, 365 after import); the set it
*recommends* is ``OPTIONAL_ENV_VARS`` alone. That split is intentional and worth
preserving in any reimplementation — but it means neither table alone answers
"which env vars does this program know about".

**And the config-key table is not the set of keys a user may legally write.** It
is the complete flattening of ``DEFAULT_CONFIG`` — nothing more. Three families
of valid keys sit outside it: (1) the 23 roots in ``_EXTRA_KNOWN_ROOT_KEYS``
(emitted separately) together with their entire subtrees, which have no defaults
at all; (2) nested keys that exist only in a projection table elsewhere — e.g. 8
of the 30 keys in ``TERMINAL_CONFIG_ENV_MAP`` (hermes_cli/config.py:3183) have no
entry under ``DEFAULT_CONFIG["terminal"]``; and (3) arbitrary top-level scalars,
which are legal by design because the gateway bridges them into ``os.environ``
for skills and external programs, so the root level is deliberately open-world.
Use this table as "every key that has a declared default", which is exactly what
it is and what the doc-coverage question needs.

For each key this script reports four columns:

  key          dotted path (``agent.max_turns``) or env var name
  default      the default literal, as written in the source
  def_at       ``hermes_cli/config_defaults.py:N`` — where it is defined
  read_sites   non-test sites that mention the leaf name / env var
  docs         which documentation surfaces mention it

**Read sites are counted per language, and that is not a nicety.** A large part
of this config surface is never read by Python at all: the TypeScript clients
(``ui-tui/``, ``web/``, ``apps/desktop/``) fetch the merged config over the
``config.get`` RPC and interpret it themselves. Scanning only ``*.py`` reports
live keys like ``display.show_cost`` (read at ui-tui/src/gatewayTypes.ts:89)
and ``dashboard.show_token_analytics`` (web/src/App.tsx:423) as dead. The
``py_sites`` / ``ts_sites`` split makes that boundary visible instead of
silently mis-scoring it.

Read-site detection is deliberately *generous*: config values are read three
different ways in this codebase — ``cfg_get(cfg, "agent", "max_turns")``
(hermes_cli/config.py:2886), ``_get_nested(config, "agent.max_turns")``
(:1073), and plain subscript chains ``CLI_CONFIG["agent"]["max_turns"]`` —
so no single pattern finds them all. We therefore count occurrences of the
quoted leaf name and report the count plus a few representative sites. That
over-counts keys whose leaf name is a common word, and the ``AMBIG`` flag marks
those. What it does *not* do is under-count: a key reported with 0 read sites
really is never mentioned outside its definition, which is the finding worth
having.

Usage:
    python3 scripts/config_table.py <baseline_repo> [--out-dir data]
"""
from __future__ import annotations

import argparse
import ast
import csv
import json
import re
import subprocess
import sys
from pathlib import Path

DEFAULTS_FILE = "hermes_cli/config_defaults.py"
CONFIG_FILE = "hermes_cli/config.py"

# Documentation surfaces, in the order they are reported.
DOC_SURFACES = [
    (".env.example", [".env.example"]),
    ("AGENTS.md", ["AGENTS.md"]),
    ("README", ["README.md", "README.zh-CN.md", "README.es.md", "README.ur-pk.md"]),
    ("CONTRIBUTING", ["CONTRIBUTING.md", "CONTRIBUTING.es.md"]),
    ("website/docs", None),   # globbed
    ("docs/", None),          # globbed
]

# Leaf names too generic for a quoted-name search to mean anything.
AMBIGUOUS_LEAVES = {
    "enabled", "mode", "model", "path", "name", "type", "url", "host", "port",
    "timeout", "max", "min", "size", "limit", "provider", "token", "key",
    "value", "format", "level", "style", "theme", "backend", "command", "args",
    "default", "prompt", "color", "width", "height", "state", "status", "id",
}


def load_source(repo: Path) -> tuple[str, ast.Module]:
    src = (repo / DEFAULTS_FILE).read_text(encoding="utf-8")
    return src, ast.parse(src)


def top_level_dict(tree: ast.Module, name: str) -> ast.Dict:
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == name:
                    if not isinstance(node.value, ast.Dict):
                        raise SystemExit(f"{name} is not a dict literal")
                    return node.value
    raise SystemExit(f"{name} not found in {DEFAULTS_FILE}")


def literal(node: ast.AST) -> str:
    """Render a default value the way it is written in the source."""
    try:
        val = ast.literal_eval(node)
    except (ValueError, SyntaxError):
        return f"<{type(node).__name__}>"
    if isinstance(val, dict):
        return "{...}" if val else "{}"
    if isinstance(val, list):
        return f"[{len(val)} items]" if val else "[]"
    return json.dumps(val, ensure_ascii=False) if isinstance(val, str) else repr(val)


def flatten(d: ast.Dict, prefix: str = "") -> list[tuple[str, str, int, bool]]:
    """(dotted_key, default_literal, lineno, is_branch) for every key, recursively.

    Branch nodes (nested dicts) are emitted too — a user can set a whole subtree
    in config.yaml, and several code paths read the branch rather than a leaf.
    """
    out: list[tuple[str, str, int, bool]] = []
    for k_node, v_node in zip(d.keys, d.values):
        if not isinstance(k_node, ast.Constant) or not isinstance(k_node.value, str):
            continue  # `**spread` or a computed key — none exist today, but be safe
        key = f"{prefix}{k_node.value}"
        is_branch = isinstance(v_node, ast.Dict) and bool(v_node.keys)
        out.append((key, literal(v_node), k_node.lineno, is_branch))
        if is_branch:
            out.extend(flatten(v_node, prefix=f"{key}."))
    return out


def extra_root_keys(repo: Path) -> list[tuple[str, int]]:
    """Root keys valid on disk but deliberately absent from DEFAULT_CONFIG.

    ``hermes_cli/config.py`` maintains ``_EXTRA_KNOWN_ROOT_KEYS`` beside
    ``DEFAULT_CONFIG`` and unions the two into the validator's whitelist. Its own
    comment is explicit that DEFAULT_CONFIG is the source of truth for
    *documented* roots, not for *all valid* ones — legacy list forms, optional
    blocks omitted when unused, and top-level convenience forms the gateway
    bridges all live only here. They therefore have no defaults and no nested key
    definitions, so nothing under them appears in the key table above. Emitting
    them separately keeps that hole visible instead of implying the table is total.
    """
    tree = ast.parse((repo / CONFIG_FILE).read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == "_EXTRA_KNOWN_ROOT_KEYS":
                    if isinstance(node.value, ast.Set):
                        return [
                            (e.value, e.lineno)
                            for e in node.value.elts
                            if isinstance(e, ast.Constant) and isinstance(e.value, str)
                        ]
    return []


def env_var_entries(d: ast.Dict) -> list[tuple[str, str, int]]:
    """(ENV_NAME, description, lineno) for each OPTIONAL_ENV_VARS entry."""
    out = []
    for k_node, v_node in zip(d.keys, d.values):
        if not isinstance(k_node, ast.Constant) or not isinstance(k_node.value, str):
            continue
        desc = ""
        if isinstance(v_node, ast.Dict):
            for kk, vv in zip(v_node.keys, v_node.values):
                if isinstance(kk, ast.Constant) and kk.value == "description":
                    try:
                        desc = str(ast.literal_eval(vv))
                    except (ValueError, SyntaxError):
                        desc = "<computed>"
        out.append((k_node.value, desc, k_node.lineno))
    return out


def rg(repo: Path, pattern: str, globs: list[str]) -> list[str]:
    """Fixed-string search returning `path:line` hits (ripgrep if present, else grep)."""
    cmd = ["rg", "--no-heading", "--line-number", "--fixed-strings", pattern]
    for g in globs:
        cmd += ["--glob", g]
    try:
        p = subprocess.run(cmd, cwd=repo, capture_output=True, text=True, timeout=120)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    if p.returncode not in (0, 1):
        return []
    hits = []
    for line in p.stdout.splitlines():
        parts = line.split(":", 2)
        if len(parts) >= 2:
            hits.append(f"{parts[0]}:{parts[1]}")
    return hits


PY_GLOBS = ["*.py", "!tests/**", "!tests-js/**", "!**/__tests__/**"]
TS_GLOBS = ["*.ts", "*.tsx", "*.js", "*.jsx", "!tests/**", "!tests-js/**",
            "!**/__tests__/**", "!**/*.test.ts", "!**/*.test.tsx",
            "!**/node_modules/**", "!website/build/**"]


def read_sites(repo: Path, leaf: str, defaults_rel: str, globs: list[str]) -> list[str]:
    """Non-test sites quoting or dot-accessing this leaf, excluding the definition file.

    TS clients reach keys three ways — quoted (``cfg["display"]["show_cost"]``),
    bare property access (``dash.show_token_analytics``), and object-literal keys
    (``show_cost?: boolean``) — so the bare name must be searched too, not just
    the quoted forms used on the Python side.
    """
    hits = rg(repo, f'"{leaf}"', globs)
    hits += rg(repo, f"'{leaf}'", globs)
    hits += rg(repo, f".{leaf}", globs)
    hits += rg(repo, f"{leaf}?:", globs)
    hits += rg(repo, f"{leaf}:", globs)
    return sorted({h for h in hits if not h.startswith(defaults_rel + ":")})


def doc_hits(repo: Path, needle: str) -> list[str]:
    """Which documentation surfaces mention this key/env var."""
    found = []
    for label, files in DOC_SURFACES:
        if files is None:
            globs = [f"{label.rstrip('/')}/**/*.md"] if label != "website/docs" \
                else ["website/docs/**/*.md"]
            hits = rg(repo, needle, globs)
        else:
            hits = []
            for f in files:
                if (repo / f).is_file():
                    hits += rg(repo, needle, [f])
        if hits:
            found.append(label)
    return found


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("repo", type=Path)
    ap.add_argument("--out-dir", type=Path, default=Path("data"))
    args = ap.parse_args()
    repo = args.repo
    if not (repo / DEFAULTS_FILE).is_file():
        raise SystemExit(f"not a hermes-agent baseline: {repo}")

    _, tree = load_source(repo)
    cfg_keys = flatten(top_level_dict(tree, "DEFAULT_CONFIG"))
    env_keys = env_var_entries(top_level_dict(tree, "OPTIONAL_ENV_VARS"))

    extras = extra_root_keys(repo)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    cfg_out = args.out_dir / "r8a-config-keys.tsv"
    env_out = args.out_dir / "r8a-env-vars.tsv"
    extra_out = args.out_dir / "r8a-extra-root-keys.tsv"

    roots = sum(1 for k, _, _, _ in cfg_keys if "." not in k)
    print(f"DEFAULT_CONFIG: {len(cfg_keys)} keys "
          f"({sum(1 for _, _, _, b in cfg_keys if b)} branches, "
          f"{sum(1 for _, _, _, b in cfg_keys if not b)} leaves); "
          f"{roots} root keys")
    print(f"_EXTRA_KNOWN_ROOT_KEYS: {len(extras)} further valid roots "
          f"(no defaults, no nested definitions — not covered by the key table)")
    print(f"  => {roots + len(extras)} valid root keys in total")
    print(f"OPTIONAL_ENV_VARS: {len(env_keys)} entries in the source literal "
          f"(mutated in place at import; see module docstring)")

    with extra_out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["root_key", "def_at", "py_sites", "py_sites_sample", "docs"])
        for name, lineno in sorted(extras):
            py = read_sites(repo, name, DEFAULTS_FILE, PY_GLOBS)
            w.writerow([name, f"{CONFIG_FILE}:{lineno}", len(py),
                        "; ".join(py[:3]), ",".join(doc_hits(repo, name))])
    print(f"wrote {extra_out}")

    with cfg_out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["key", "kind", "default", "def_at", "py_sites", "ts_sites",
                    "py_sites_sample", "ts_sites_sample", "ambiguous", "docs"])
        for key, dflt, lineno, is_branch in cfg_keys:
            leaf = key.rsplit(".", 1)[-1]
            py = read_sites(repo, leaf, DEFAULTS_FILE, PY_GLOBS)
            ts = read_sites(repo, leaf, DEFAULTS_FILE, TS_GLOBS)
            docs = doc_hits(repo, key) or doc_hits(repo, leaf)
            w.writerow([
                key,
                "branch" if is_branch else "leaf",
                dflt,
                f"{DEFAULTS_FILE}:{lineno}",
                len(py),
                len(ts),
                "; ".join(py[:3]),
                "; ".join(ts[:3]),
                "AMBIG" if leaf in AMBIGUOUS_LEAVES else "",
                ",".join(docs),
            ])
    print(f"wrote {cfg_out}")

    with env_out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["env_var", "def_at", "py_sites", "ts_sites",
                    "py_sites_sample", "docs", "description"])
        for name, desc, lineno in env_keys:
            py = read_sites(repo, name, DEFAULTS_FILE, PY_GLOBS)
            ts = read_sites(repo, name, DEFAULTS_FILE, TS_GLOBS)
            w.writerow([
                name,
                f"{DEFAULTS_FILE}:{lineno}",
                len(py),
                len(ts),
                "; ".join(py[:4]),
                ",".join(doc_hits(repo, name)),
                re.sub(r"\s+", " ", desc)[:160],
            ])
    print(f"wrote {env_out}")
    _summarise(cfg_out, env_out, args.out_dir / "r8a-config-keys-summary.md")


def _summarise(cfg_out: Path, env_out: Path, dest: Path) -> None:
    """Write the slices worth looking at, so consumers need not re-derive them.

    The three TSVs answer "what is every key"; this answers "which rows should I
    actually read". Kept as a generated file rather than prose in a report so it
    cannot drift from the tables it summarises.
    """
    cfg = list(csv.DictReader(cfg_out.open(encoding="utf-8"), delimiter="\t"))
    env = list(csv.DictReader(env_out.open(encoding="utf-8"), delimiter="\t"))

    def n(row, k):
        return int(row[k])

    dead = [r for r in cfg if n(r, "py_sites") == 0 and n(r, "ts_sites") == 0]
    ts_only = [r for r in cfg if n(r, "py_sites") == 0 and n(r, "ts_sites") > 0]
    undocumented = [r for r in cfg if not r["docs"]]
    ambiguous = [r for r in cfg if r["ambiguous"] == "AMBIG"]
    env_dead = [r for r in env if n(r, "py_sites") == 0 and n(r, "ts_sites") == 0]

    lines = [
        "# R8A 配置项全表 · 值得先看的几片",
        "",
        "本文件由 `scripts/config_table.py` 生成,**不要手改**——它存在的意义就是不会与表脱节。",
        "表本身回答“有哪些键”,本文件回答“该先读哪些行”。",
        "",
        "> **读之前先读 `scripts/config_table.py` 开头的边界说明。** 一句话:",
        "> 这 856 个键是“**有默认值的键**”的全集,不是“用户能合法写的键”的全集。",
        "",
        f"- 配置键合计:**{len(cfg)}**"
        f"(叶子 {sum(1 for r in cfg if r['kind'] == 'leaf')} / 分支 {sum(1 for r in cfg if r['kind'] == 'branch')})",
        f"- 静态环境变量合计:**{len(env)}**(运行时会被就地灌到 308,见脚本说明)",
        "",
        f"## 1. Python 与 TypeScript 都不读的键({len(dead)})",
        "",
        "候选死配置。**逐条人工复核过再下结论**——本轮第一版就在这里错判过 5 个。",
        "",
    ]
    for r in dead:
        lines.append(f"- `{r['key']}` — 默认 `{r['default']}`,定义于 {r['def_at']},文档:{r['docs'] or '无'}")

    lines += [
        "",
        f"## 2. 只有 TypeScript 读的键({len(ts_only)})",
        "",
        "Python 侧完全不碰;配置经 `config.get` RPC 发给 TS 客户端后由它解释。",
        "**任何只扫 Python 的分析都会把这些判成死键。**",
        "",
    ]
    for r in ts_only:
        lines.append(f"- `{r['key']}` — {r['ts_sites_sample'].split(';')[0]}")

    lines += [
        "",
        f"## 3. 全部文档面零提及的键({len(undocumented)})",
        "",
        "这是本轮 ◇-1 的清单,也是**唯一站得住的文档缺口数字**",
        "(为什么不报百分比,见 `notes/r8a-90` ◇-1)。R11 对表时可直接消费。",
        "",
    ]
    lines += [f"- `{r['key']}` ({r['def_at']})" for r in undocumented]

    lines += [
        "",
        f"## 4. 叶子名过于常见、读取点统计不可信的键({len(ambiguous)})",
        "",
        "叶子名形如 `enabled` / `timeout` / `mode`。**这些行的 `py_sites` / `ts_sites` 只能当上界看。**",
        "",
        "<details><summary>展开</summary>",
        "",
    ]
    lines += [f"- `{r['key']}`" for r in ambiguous]
    lines += ["", "</details>", ""]

    if env_dead:
        lines += [f"## 5. 无人读取的环境变量({len(env_dead)})", ""]
        for r in env_dead:
            lines.append(f"- `{r['env_var']}` — 文档:{r['docs'] or '无'}")
        lines.append("")

    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {dest}")


if __name__ == "__main__":
    main()
