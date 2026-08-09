#!/usr/bin/env python3
"""R10B 片D 探针:校验底稿 §0.2 的 12 个归组是否不重不漏地覆盖 store/ 的 86 个模块。

用法:
    python3 data/r10b/probes/probe_d_store_groups.py /home/user/hermes-agent

打印每组条数、总数、以及 missing / extra 两个集合(都应为 [])。
退出码 1 表示归组与磁盘不一致。
"""
import pathlib
import sys

GROUPS = {
    'A 与内核接驳/连接与会话身份':
        'gateway gateway-switch session session-states session-sync session-pin-sync',
    'B profile/项目/工作区':
        'profile profile-share projects coding-status',
    'C 布局/窗格/窗口':
        'layout panes pane-focus route-tiles windows thread-scroll zoom translucency',
    'D Composer 一族':
        'composer composer-queue composer-actions composer-input-history '
        'composer-popout composer-status quick-entry find-in-page',
    'E 回合内阻塞式交互':
        'prompts clarify approval-mode compaction',
    'F 工具行与产物':
        'tool-view tool-dismiss tool-diffs tool-drafting artifacts preview '
        'preview-edit preview-status',
    'G 通知与提醒':
        'notifications native-notifications notify-baseline agent-notices billing-block ambient',
    'H 语音/声音/触感':
        'wake-word voice-playback voice-prefs completion-sound haptics reactions',
    'I 宠物':
        'pet pet-gallery pet-generate pet-overlay',
    'J 设置类小原子':
        'backdrop statusbar-prefs keybinds keep-awake power data-url-read-max '
        'embed-consent model-presets model-visibility provider-collapse reactions-enabled',
    'K 事件驱动刷新信号':
        'live-sync workspace-events',
    'L 其余单点':
        'active-work activity background-delegation boot command-palette cron '
        'file-actions goals hub-actions onboarding reactions-local review '
        'session-color session-switcher starmap subagents system-actions todos updates',
}


def main() -> int:
    root = pathlib.Path(sys.argv[1])
    on_disk = {p.stem for p in (root / 'apps/desktop/src/store').glob('*.ts')
               if not p.name.endswith('.test.ts')}

    seen: set[str] = set()
    dupes: list[str] = []
    total = 0
    for label, names in GROUPS.items():
        items = names.split()
        total += len(items)
        print(f'{label}: {len(items)}')
        for n in items:
            if n in seen:
                dupes.append(n)
            seen.add(n)

    print(f'total in groups = {total}, files on disk = {len(on_disk)}')
    print(f'missing (on disk, ungrouped): {sorted(on_disk - seen)}')
    print(f'extra (grouped, not on disk): {sorted(seen - on_disk)}')
    print(f'duplicated across groups: {sorted(dupes)}')

    ok = total == len(on_disk) == len(seen) and not (on_disk ^ seen) and not dupes
    print('OK' if ok else 'FAIL')

    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
