#!/usr/bin/env python3
"""R11F 片 A —— 三家适配器**向平台注册**的交互入口面(判据 2)。

三家的注册惯用法完全不同,所以按平台各写一个 AST 提取器:

  discord   `@tree.command(name=..., description=...)`  原生 slash
            `@self._client.event` + `async def on_*`     网关事件监听
            `class X(discord.ui.View)` + `@discord.ui.button(label=...)`  按钮
  telegram  `add_handler(<Handler>(...))`                 python-telegram-bot 处理器
            `callback_data=` 产出的前缀 / `data.startswith(...)` 消费的前缀
  slack     `@self._app.event("...")` / `self._app.action(...)` /
            `@self._app.command(...)`                     slack-bolt 三类订阅

用法: python3 a_interaction_surface.py [基线路径] [--mode summary|discord|telegram|slack]
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

DISCORD = "plugins/platforms/discord/adapter.py"
TELEGRAM = "plugins/platforms/telegram/adapter.py"
SLACK = "plugins/platforms/slack/adapter.py"


def _lit(node) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _kw(call: ast.Call, name: str):
    for k in call.keywords:
        if k.arg == name:
            return k.value
    return None


# ── discord ────────────────────────────────────────────────────────────────
def discord_surface(src: str) -> dict:
    tree = ast.parse(src)
    slashes, events, views, buttons = [], [], [], []
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in n.decorator_list:
                if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute) \
                        and dec.func.attr == "command" \
                        and isinstance(dec.func.value, ast.Name) and dec.func.value.id == "tree":
                    nm = _lit(_kw(dec, "name"))
                    desc = _lit(_kw(dec, "description"))
                    if nm:
                        slashes.append((nm, desc or "", dec.lineno))
                if isinstance(dec, ast.Attribute) and dec.attr == "event":
                    events.append((n.name, n.lineno))
                if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute) \
                        and dec.func.attr == "button":
                    lab = _lit(_kw(dec, "label"))
                    buttons.append((lab or n.name, n.lineno))
        if isinstance(n, ast.ClassDef):
            for b in n.bases:
                if isinstance(b, ast.Attribute) and b.attr == "View":
                    views.append((n.name, n.lineno))
    return {"slash": sorted(slashes), "event": sorted(events),
            "view": sorted(views), "button": sorted(buttons, key=lambda x: x[1])}


# ── telegram ───────────────────────────────────────────────────────────────
def telegram_surface(src: str) -> dict:
    tree = ast.parse(src)
    handlers = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                and n.func.attr == "add_handler" and n.args:
            a = n.args[0]
            if isinstance(a, ast.Call):
                hname = a.func.id if isinstance(a.func, ast.Name) else ast.unparse(a.func)
                cb = ""
                for arg in a.args:
                    if isinstance(arg, ast.Attribute):
                        cb = arg.attr
                handlers.append((hname, cb, n.lineno))
    produced: dict[str, int] = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            v = _kw(n, "callback_data")
            if v is None:
                continue
            txt = None
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                txt = v.value
            elif isinstance(v, ast.JoinedStr):
                first = v.values[0] if v.values else None
                txt = first.value if isinstance(first, ast.Constant) else None
            if txt:
                pre = txt.split(":", 1)[0]
                produced.setdefault(pre, n.lineno)
    # 「消费」的口径限定在**回调分发函数体内**(_handle_callback_query),
    # 否则 `.startswith(...)` 会把全文件的路径/MIME 前缀判断一起吞进来
    # (实测朴素口径多出 7 个:`**` `/output/` `/outputs/` `/workspace/`
    #  `file` `image/` `text/`),那不是 callback_data 前缀。
    consumed: dict[str, int] = {}
    dispatch = [n for n in ast.walk(tree)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                and n.name == "_handle_callback_query"]
    for fn in dispatch:
        for n in ast.walk(fn):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                    and n.func.attr == "startswith" and n.args:
                arg = n.args[0]
                items = arg.elts if isinstance(arg, ast.Tuple) else [arg]
                for it in items:
                    s = _lit(it)
                    if s:
                        consumed.setdefault(s.split(":", 1)[0].rstrip(":"), n.lineno)
    return {"handler": sorted(handlers, key=lambda x: x[2]),
            "produced": dict(sorted(produced.items())),
            "consumed": dict(sorted(consumed.items()))}


# ── slack ──────────────────────────────────────────────────────────────────
def slack_surface(src: str) -> dict:
    tree = ast.parse(src)
    events, actions, commands = [], [], []

    def _pat(node) -> str:
        s = _lit(node)
        if s is not None:
            return s
        return "re:" + ast.unparse(node)

    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in n.decorator_list:
                if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                    if dec.func.attr == "event" and dec.args:
                        events.append((_pat(dec.args[0]), n.name, dec.lineno))
                    elif dec.func.attr == "command" and dec.args:
                        commands.append((_pat(dec.args[0]), n.name, dec.lineno))
                    elif dec.func.attr == "action" and dec.args:
                        actions.append((_pat(dec.args[0]), n.name, dec.lineno))
        # 非装饰器写法:self._app.action(id)(cb)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Call) \
                and isinstance(n.func.func, ast.Attribute) and n.func.func.attr == "action" \
                and n.func.args:
            cb = ast.unparse(n.args[0]) if n.args else ""
            actions.append((_pat(n.func.args[0]), cb, n.lineno))
        # for 循环里的 self._app.action(_action_id)(cb):记录循环常量表
    # 展开 `for _action_id in (...)` 常量元组
    loop_ids = []
    for n in ast.walk(tree):
        if isinstance(n, ast.For) and isinstance(n.target, ast.Name) \
                and isinstance(n.iter, ast.Tuple):
            vals = [_lit(e) for e in n.iter.elts]
            if all(v is not None for v in vals):
                body_txt = ast.unparse(n.body)
                if ".action(" in body_txt:
                    loop_ids.append((n.target.id, [v for v in vals], n.lineno, body_txt))
    return {"event": sorted(events, key=lambda x: x[2]),
            "action": sorted(actions, key=lambda x: x[2]),
            "command": sorted(commands, key=lambda x: x[2]),
            "action_loop": loop_ids}


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]
    root = Path(args[0]) if args else Path("/home/user/hermes-agent")
    mode = "summary"
    for f in flags:
        if f.startswith("--mode"):
            mode = f.split("=", 1)[1] if "=" in f else "summary"

    d = discord_surface((root / DISCORD).read_text(encoding="utf-8"))
    t = telegram_surface((root / TELEGRAM).read_text(encoding="utf-8"))
    s = slack_surface((root / SLACK).read_text(encoding="utf-8"))

    if mode == "discord":
        for nm, desc, ln in d["slash"]:
            print(f"slash\t/{nm}\t{DISCORD}:{ln}\t{desc}")
        for nm, ln in d["event"]:
            print(f"event\t{nm}\t{DISCORD}:{ln}")
        for nm, ln in d["view"]:
            print(f"view\t{nm}\t{DISCORD}:{ln}")
        for nm, ln in d["button"]:
            print(f"button\t{nm}\t{DISCORD}:{ln}")
        return 0
    if mode == "telegram":
        for h, cb, ln in t["handler"]:
            print(f"handler\t{h}\t{cb}\t{TELEGRAM}:{ln}")
        for p, ln in t["produced"].items():
            print(f"produced\t{p}:\t{TELEGRAM}:{ln}")
        for p, ln in t["consumed"].items():
            print(f"consumed\t{p}:\t{TELEGRAM}:{ln}")
        return 0
    if mode == "slack":
        for p, fn, ln in s["event"]:
            print(f"event\t{p}\t{fn}\t{SLACK}:{ln}")
        for p, fn, ln in s["command"]:
            print(f"command\t{p}\t{fn}\t{SLACK}:{ln}")
        for p, fn, ln in s["action"]:
            print(f"action\t{p}\t{fn}\t{SLACK}:{ln}")
        for var, vals, ln, _ in s["action_loop"]:
            print(f"action_loop\t{var}\t{' '.join(vals)}\t{SLACK}:{ln}")
        return 0

    print(f"DISCORD  slash={len(d['slash'])} client_event={len(d['event'])} "
          f"ui_view={len(d['view'])} ui_button={len(d['button'])}")
    only_consumed = sorted(set(t["consumed"]) - set(t["produced"]))
    only_produced = sorted(set(t["produced"]) - set(t["consumed"]))
    print(f"TELEGRAM add_handler={len(t['handler'])} "
          f"callback_prefix_produced={len(t['produced'])} "
          f"callback_prefix_consumed={len(t['consumed'])} "
          f"consumed_only={len(only_consumed)}")
    print(f"  consumed-but-never-produced: {' '.join(only_consumed) or '(无)'}")
    print(f"  produced-but-never-consumed: {' '.join(only_produced) or '(无)'}")
    loop_n = sum(len(v) for _, v, _, _ in s["action_loop"])
    print(f"SLACK    event={len(s['event'])} command={len(s['command'])} "
          f"action_direct={len(s['action'])} action_via_loop={loop_n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
