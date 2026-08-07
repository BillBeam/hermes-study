# R4-95 行为规格测试运行记录

> 底稿。基线 `863e31318`(hermes-agent 零改动,只读)。运行器:官方 `scripts/run_tests.sh`
> (密封环境、per-file 子进程隔离、8 workers)。命令模板:
> `HERMES_PYTHON=/home/user/hermes-venv/bin/python bash scripts/run_tests.sh <files>`。
> 目的:把 R4 机制簇的测试当**行为规格**跑通,证实底稿断言、锁定回归基线。

## 1. 汇总

本会话跑的三批,全绿:

| 批次 | 文件数 | 通过 | 失败 | 运行墙钟 |
|---|---|---|---|---|
| 核心后端 + 终端 + 进程 + patch + file_sync/state | 23 | 343 | 0 | 12.9s |
| 浏览器自动化栈 | 10 | 122 | 0 | 142.8s |
| computer_use 桌面控制 | 16 | 199 | 0 | 5.7s |
| **合计** | **49** | **664** | **0** | — |

`test_browser_hardening.py` 单文件 142.8s(含真实超时/等待路径),仍全过;其余多在 1–8s。

## 2. 逐批清单

### 批一:核心后端 + 终端 + 进程 + patch + file(23 文件 / 343)

环境后端契约与实现:`test_base_environment`(契约 + `_wait_for_process`)、`test_docker_environment`、
`test_ssh_environment`、`test_ssh_bulk_upload`、`test_singularity_preflight`、`test_modal_sandbox_fixes`、
`test_modal_snapshot_isolation`(快照命名空间隔离 + legacy 迁移)、`test_modal_bulk_upload`、
`test_managed_modal_environment`、`test_daytona_environment`(stop-resume 生命周期)、
`test_vercel_sandbox_environment`(快照 + 自愈)。

文件同步与新鲜度:`test_file_sync`、`test_file_sync_back`(反向同步完整契约)、`test_file_sync_sigint`、
`test_file_state_registry`(跨代理读后写守卫)。

终端 shell 语义 + 后台进程 + 补丁:`test_process_registry`、`test_patch_parser`、`test_terminal_tool`、
`test_terminal_compound_background`(`A && B &` 重写)、`test_terminal_exit_semantics`、
`test_terminal_cwd_echo`(CWD 标记回传)、`test_terminal_truncation_spill`(有界捕获 + spill)、
`test_runtime_cwd`。

### 批二:浏览器(10 文件 / 122)

`test_browser_supervisor`、`test_browser_supervisor_healthcheck`、`test_browser_cdp_tool`、
`test_browser_cdp_override`、`test_browser_camofox`、`test_browser_hardening`、`test_browser_secret_exfil`、
`test_browser_ssrf_local`、`test_browser_orphan_reaper`、`test_browser_type_redaction`。

### 批三:computer_use(16 文件 / 199)

`test_computer_use`(73)、`test_computer_use_vision_routing`(18)、`test_computer_use_delivery_ladder`(17)、
`test_computer_use_approval_isolation`、`test_computer_use_capture_routing`、`test_computer_use_cua_0_9`(37)、
`test_computer_use_cua_0_10_permissions`、`test_computer_use_cua_backend_linux`、
`test_computer_use_null_pid_windows`、`test_cua_spawn_env_sanitization`、`test_cua_no_overlay`、
`test_cua_atexit_teardown`、`test_cua_perf_knobs`、`test_cua_telemetry`、`test_cua_cli_fallback_env`、
`test_cua_wsl_manifest_path`。

## 3. 环境依赖(可选装,非代码失败)

沿用 R2/R3 记录的模式——**这些是测试宿主缺可选依赖/系统工具,不是 hermes-agent 代码缺陷**。本轮为让
远端后端测试从 skip/error 转为真实运行,在 venv/系统里补装:

- `daytona==0.155.0`:否则 `ImportError: Feature 'terminal.daytona' unavailable: lazy installs disabled`。
- `modal==1.3.4`:同上,`terminal.modal` 懒装被禁。
- `openssh-client`(apt,`/usr/bin/ssh`):否则 `RuntimeError: SSH is not installed or not in PATH`。
  初次 `apt-get install` 报 404,`apt-get update` 后成功。

hermes 的 `lazy_deps` 机制(R3 学过)在密封测试环境里**故意禁掉懒装**,所以缺依赖会 fail-fast 而非
静默降级——这本身是被测行为的一部分(测试要么 skip 要么要求预装)。补装后相关后端测试全部真实通过。

真跑模型仍需任一 provider 凭据(见 R1 §1.5);本簇纯执行环境测试**不需要**模型凭据,也未配置。

## 4. 与底稿的呼应(测试即规格)

- `test_modal_snapshot_isolation` 钉死 r4-20 §2.1 的 `direct:<task>` 命名空间键 + legacy 迁移 + 复活失败回退。
- `test_daytona_environment` 钉死 r4-20 §2.3 的"persistent cleanup `stop()` 而非 delete""中断掀沙箱返回 130"
  "STOPPED 态下一命令前 `start()` 自愈"。
- `test_file_sync_back` 钉死 r4-20 §3.3 的凭据单向、last-write-wins、flock、SIGINT 延迟、尺寸/重试护栏。
- `test_terminal_compound_background` 钉死 r4-02 §3 的 `A && B &` → `A && { B & }` 重写。
- `test_file_state_registry` 钉死 r4-50 §2 的跨代理读后写 stale 守卫。
- `test_cua_spawn_env_sanitization` 钉死 r4-40 的"每个 cua-driver spawn 都 sanitize env 剥 provider 密钥"。
- `test_computer_use_delivery_ladder` 钉死 r4-40 的 background/foreground 投递阶梯 + 审批 session 隔离
  (老 driver 上 foreground 拒绝而非静默降级)。
