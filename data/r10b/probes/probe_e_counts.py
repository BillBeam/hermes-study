#!/usr/bin/env python3
"""R10B 片 E:一次性打印底稿里引用的所有「表条数」,便于逐条复核。

用法:
    python3 data/r10b/probes/probe_e_counts.py /home/user/hermes-agent

每一行都是「表名 = 条数」,配套注明取数方式。全部靠正则数字面量,
不执行 TS;改了表的写法会让数字失真,所以任何一次复核都以本脚本重跑为准。
"""
from __future__ import annotations

import os
import re
import sys


def read(root: str, rel: str) -> str:
    return open(os.path.join(root, rel), encoding="utf-8").read()


def block(src: str, opener: str, closer: str = "\n]") -> str:
    return src.split(opener, 1)[1].split(closer, 1)[0]


def main() -> int:
    root = sys.argv[1] if len(sys.argv) > 1 else "/home/user/hermes-agent"
    D = "apps/desktop/"

    out: list[tuple[str, int | str, str]] = []

    # ── keybinds ────────────────────────────────────────────────────────────
    kb = read(root, D + "src/lib/keybinds/actions.ts")
    kb_lit = block(kb, "export const KEYBIND_ACTIONS: readonly KeybindActionMeta[] = [")
    lit = len(re.findall(r"\{\s*id: '", kb_lit))
    prof = int(re.search(r"PROFILE_SLOT_COUNT = (\d+)", kb).group(1))
    sess = int(re.search(r"SESSION_SLOT_COUNT = (\d+)", kb).group(1))
    out.append(("KEYBIND_ACTIONS 字面行", lit, "actions.ts 表内 `{ id: '`"))
    out.append(("PROFILE_SLOT_COUNT", prof, "生成 profile.switch.N"))
    out.append(("SESSION_SLOT_COUNT", sess, "生成 session.slot.N"))
    out.append(("KEYBIND_ACTIONS 运行时总数", lit + prof + sess, "字面 + 两组生成"))
    ro = block(kb, "export const KEYBIND_READONLY: readonly KeybindReadonly[] = [")
    out.append(("KEYBIND_READONLY", len(re.findall(r"\{ id: '", ro)), "只读展示行"))
    out.append(("KEYBIND_CATEGORIES", len(re.findall(r"'", block(kb, "KEYBIND_CATEGORIES: readonly KeybindCategory[] = [", "]"))) // 2, "分类枚举"))

    # ── combo 表 ────────────────────────────────────────────────────────────
    combo = read(root, D + "src/lib/keybinds/combo.ts")
    out.append(("CODE_TO_KEY", len(re.findall(r"^  \w+:", block(combo, "const CODE_TO_KEY: Record<string, string> = {", "\n}"), re.M)), "event.code → 基础键"))
    out.append(("MODIFIER_CODES", len(re.findall(r"'", block(combo, "const MODIFIER_CODES = new Set([", "\n])"))) // 2, "纯修饰键 code"))
    out.append(("TOKEN_LABELS", len(re.findall(r"^  \w+:", block(combo, "const TOKEN_LABELS: Record<string, string> = {", "\n}"), re.M)), "显示标签"))

    # ── 主题 ────────────────────────────────────────────────────────────────
    presets = read(root, D + "src/themes/presets.ts")
    builtins = re.findall(r"^  (\w+): \w+Theme,?$", block(presets, "export const BUILTIN_THEMES: Record<string, DesktopTheme> = {", "\n}"), re.M)
    out.append(("BUILTIN_THEMES", len(builtins), " ".join(builtins)))
    vscode = read(root, D + "src/themes/vscode.ts")
    out.append(("ANSI_TOKENS", len(re.findall(r"\['", block(vscode, "const ANSI_TOKENS: ReadonlyArray<readonly [keyof DesktopTerminalPalette, string]> = [")))
                , "VS Code terminal.ansi* → xterm ITheme 槽"))
    types = read(root, D + "src/themes/types.ts")
    out.append(("DesktopThemeColors 字段", len(re.findall(r"^  \w+\??:", block(types, "export interface DesktopThemeColors {", "\n}"), re.M)), "主题色令牌"))
    out.append(("DesktopTerminalPalette 字段", len(re.findall(r"^  \w+\??:", block(types, "export interface DesktopTerminalPalette {", "\n}"), re.M)), "终端调色板槽"))

    # ── 图标 ────────────────────────────────────────────────────────────────
    icons = read(root, D + "src/lib/icons.ts")
    out.append(("icons.ts Tabler 别名", len(re.findall(r"Icon\w+ as (\w+)", icons)), "IconX as X"))
    out.append(("iconSize 档位", len(re.findall(r"^  \w+:", block(icons, "export const iconSize = {", "\n}"), re.M)), "xs..xl"))
    brand = read(root, D + "src/lib/brand-icon.ts")
    bblock = block(brand, "const BRAND_ICONS: Record<string, BrandIcon> = {", "\n}")
    out.append(("BRAND_ICONS 域名键", len(re.findall(r"^\s+'([^']+)':", bblock, re.M)), "注册域 → 品牌图标"))
    out.append(("BRAND_ICONS 去重组件", len(set(re.findall(r": (Si\w+)", bblock))), "simple-icons 组件"))

    # ── 声音 ────────────────────────────────────────────────────────────────
    snd = read(root, D + "src/lib/completion-sound.ts")
    out.append(("COMPLETION_SOUND_VARIANTS", len(re.findall(r"^    id: \d+,$", snd, re.M)), "回合结束提示音预设"))

    # ── escape 层 ───────────────────────────────────────────────────────────
    esc = read(root, D + "src/lib/escape-layers.ts")
    out.append(("ESCAPE_PRIORITY", len(re.findall(r"^  \w+: \d+", block(esc, "export const ESCAPE_PRIORITY = {", "\n}"), re.M)), "Esc 归属层"))

    # ── markdown ────────────────────────────────────────────────────────────
    mc = read(root, D + "src/lib/markdown-code.ts")
    for name in ("CODICON_BY_LANGUAGE", "LANGUAGE_BY_EXTENSION", "SHIKI_LANGUAGE_BY_EXTENSION"):
        b = block(mc, f"const {name}: Record<string, string> = {{", "\n}")
        out.append((name, len(re.findall(r"^  [\w']+:", b, re.M)), "markdown-code 映射表"))
    out.append(("COMMON_CODE_LANGUAGES", len(re.findall(r"^  '", block(mc, "const COMMON_CODE_LANGUAGES = new Set([", "\n])"), re.M)), "被当成真代码的语言"))

    # ── media ───────────────────────────────────────────────────────────────
    media = read(root, D + "src/lib/media.ts")
    out.append(("MEDIA_BY_EXT", len(re.findall(r"^  \w+: \{", block(media, "const MEDIA_BY_EXT: Record<string, MediaInfo> = {", "\n}"), re.M)), "扩展名 → 媒体类型"))

    # ── 其它内容表 ──────────────────────────────────────────────────────────
    ss = read(root, D + "src/lib/session-source.ts")
    out.append(("SOURCE_LABELS", len(re.findall(r"^  [\w']+:", block(ss, "const SOURCE_LABELS: Record<string, string> = {", "\n}"), re.M)), "会话来源标签"))
    ep = read(root, D + "src/lib/excluded-paths.ts")
    out.append(("ALWAYS_EXCLUDED", len(re.findall(r"^  '", block(ep, "export const ALWAYS_EXCLUDED = new Set([", "\n])"), re.M)), "文件树硬排除项"))
    dt = read(root, D + "src/lib/desktop-toolsets.ts")
    out.append(("DESKTOP_HIDDEN_TOOLSETS", len(re.findall(r"^  '", block(dt, "const DESKTOP_HIDDEN_TOOLSETS = new Set([", "\n])"), re.M)), "桌面隐藏的 toolset"))
    cr = read(root, D + "src/lib/chat-runtime.ts")
    out.append(("BUILTIN_PERSONALITIES", len(re.findall(r"^  '", block(cr, "export const BUILTIN_PERSONALITIES = [", "\n]"), re.M)), "内置人格名"))
    re_ = read(root, D + "src/lib/reasoning-effort.ts")
    out.append(("REASONING_EFFORTS", len(re.findall(r"'", re.search(r"REASONING_EFFORTS = \[([^\]]*)\]", re_).group(1))) // 2, "思考强度档"))
    pit = read(root, D + "src/lib/project-idea-templates.ts")
    out.append(("PROJECT_IDEA_TEMPLATES", len(re.findall(r"^    emoji:", pit, re.M)), "新建项目点子池"))

    width = max(len(n) for n, _, _ in out)
    for name, count, note in out:
        print(f"{name:<{width}} = {count!s:>4}   # {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
