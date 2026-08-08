# r8a-raw-pairing-key · pairing.py + subcommands/pairing.py + web_server 批准入口

> 底稿(证据层)。基线 `/home/user/hermes-agent` @ `863e31318553cda8ad61df681d08175364d4164b`(简写 863e313)。
> 所有 `路径:行号 @ 863e313` 均为相对基线仓库根的路径。
>
> **本段结案的 R7C 移交项**:R7C 只证明了「批准函数的 4 个调用点全在已认证侧,入站消息路径零调用」
> ——即「那道门只能从外面开」;但**没读门外那把钥匙**。本篇把钥匙读完:CLI 一把、dashboard 一把,
> 外加一把 R7C 没点名、本轮读出来的**第三把**(dashboard 内嵌 console 的 WebSocket)。

---

## 0. 结论速览(先给答案,后给证据)

1. **批准入口共三把钥匙,不是两把**:`hermes pairing approve`(CLI)、`POST /api/pairing/approve`
   (dashboard REST)、以及 `WS /api/console` 里跑 `pairing approve`(把 CLI handler 拉进 dashboard 进程)。
2. **两把主钥匙语义不一致**,而且**不一致的那一半就是 dashboard 明文注释里指出的坑**:
   CLI 在 request-id 路径失败时也会报「平台被锁定」,dashboard 显式只在 code 路径报。
3. **CLI 侧确实破坏了封装**:`store._is_locked_out` / `store._load_json` / `store._rate_limit_path`
   三个私有方法 + 一个私有 JSON schema(`_lockout:<platform>` 键名)被 CLI 直接复刻。
   dashboard 只借了 `_is_locked_out` 一个。
4. **`hermes pairing` 全部失败路径都 exit 0**,脚本化不可判失败;dashboard 侧有 400/404/429。
5. **第三把钥匙 profile 串档**:console 里跑 `pairing approve` 时 `_profile_scope` 的 HERMES_HOME 覆写
   **够不到** `gateway.pairing.PAIRING_DIR`(模块级常量,import 时定死),批准会落到 dashboard 自己的
   profile 而不是被选中的 profile。REST 入口用 `PairingStore(profile=...)` 避开了这个坑。

---

## 1. 命令面(parser):`hermes_cli/subcommands/pairing.py` 全文 40 行

**解决什么问题**:把 `pairing` 子命令从 god-file `hermes_cli/main.py:main()` 里拆出来,且**不反向 import main**
——handler 用关键字参数注入。这是 R8A 反复见到的「拆 god-file 但不制造循环 import」模式。

parser 构造函数只接受一个注入的 handler,签名把它写死成关键字参数。`hermes_cli/subcommands/pairing.py:12 @ 863e313`

```python
def build_pairing_parser(subparsers, *, cmd_pairing: Callable) -> None:
```

四个动作全部挂在 `dest="pairing_action"` 上,**没有 `required=True`**。`hermes_cli/subcommands/pairing.py:19 @ 863e313`

```python
    pairing_sub = pairing_parser.add_subparsers(dest="pairing_action")
```

于是 `hermes pairing` 裸跑时 `args.pairing_action is None`,落进 handler 的 else 分支打 usage(见 §2)。

`approve` 只有**一个**位置参数,metavar 写成 `request-id|code`,即「一个格子塞两种东西」,靠运行时形状判别。
`hermes_cli/subcommands/pairing.py:29-33 @ 863e313`

```python
    pairing_approve_parser.add_argument(
        "code",
        metavar="request-id|code",
        help="Request ID from 'pairing list', or the code the bot DM'd the user",
    )
```

`revoke` 两个位置参数;`clear-pending` 零参数——**没有 `--platform` 过滤**,所以 CLI 只能全平台清空。
`hermes_cli/subcommands/pairing.py:35-39 @ 863e313`

```python
    pairing_revoke_parser = pairing_sub.add_parser("revoke", help="Revoke user access")
    pairing_revoke_parser.add_argument("platform", help="Platform name")
    pairing_revoke_parser.add_argument("user_id", help="User ID to revoke")

    pairing_sub.add_parser("clear-pending", help="Clear all pending codes")
```

注入点收尾。`hermes_cli/subcommands/pairing.py:40 @ 863e313`

```python
    pairing_parser.set_defaults(func=cmd_pairing)
```

**取舍**:`approve` 用一个位置参数吃两种 ID,好处是 CLI 手感简单(操作员不必记 `--by-request-id`),
代价是**判别逻辑必须靠形状**,而形状判别一旦落空就会走进「计入暴力破解失败次数」的那条路(见 §5 defect D3)。

**注册处**(不在本段文件内,但决定了 handler 怎么被调):`hermes_cli/main.py:11601 @ 863e313` 调
`build_pairing_parser(subparsers, cmd_pairing=cmd_pairing)`;handler 本体是三行转发。
`hermes_cli/main.py:11159-11162 @ 863e313`

```python
def cmd_pairing(args):
    from hermes_cli.pairing import pairing_command

    pairing_command(args)
```

注意这里是**裸调用没有 `return`**——这条是 §5 defect D4 的一半。

---

## 2. 分发面:`hermes_cli/pairing.py` 全文 121 行

### 2.1 入口

**解决什么问题**:CLI 层不该在 import 时把 gateway 拖进来(`gateway.pairing` 会连带 `gateway.whatsapp_identity`、
`hermes_constants`、并在模块级算 `PAIRING_DIR`)。所以 store 的 import 放在函数体内。
`hermes_cli/pairing.py:11-16 @ 863e313`

```python
def pairing_command(args):
    """Handle hermes pairing subcommands."""
    from gateway.pairing import PairingStore

    store = PairingStore()
    action = getattr(args, "pairing_action", None)
```

**关键点**:`PairingStore()` **不传 profile**。CLI 的 profile 是靠进程环境变量实现的——
`hermes_cli/main.py` 在模块级(即任何 `gateway.pairing` 的 lazy import 之前)就把 `HERMES_HOME` 写进
`os.environ`。`hermes_cli/main.py:683 @ 863e313`

```python
        os.environ["HERMES_HOME"] = hermes_home
```

而这行所在的 `_apply_profile_override()` 在模块级被调用。`hermes_cli/main.py:690 @ 863e313`

```python
_apply_profile_override()
```

所以 `hermes -p work pairing approve ...` 是**正确**的:等到 `pairing_command` 里 import `gateway.pairing`,
模块级的 `PAIRING_DIR` 才第一次被计算,此时 `HERMES_HOME` 已指向 work profile。
——这个「靠 import 时机」的正确性非常脆,同一份代码搬进长驻进程就塌了(§4.3 defect D8)。

分发是四路 if/elif,第五路是 usage。`hermes_cli/pairing.py:18-28 @ 863e313`

```python
    if action == "list":
        _cmd_list(store)
    elif action == "approve":
        _cmd_approve(store, args.platform, args.code)
    elif action == "revoke":
        _cmd_revoke(store, args.platform, args.user_id)
    elif action == "clear-pending":
        _cmd_clear_pending(store)
    else:
        print("Usage: hermes pairing {list|approve|revoke|clear-pending}")
        print("Run 'hermes pairing --help' for details.")
```

**没有任何一条返回值**。整个 `pairing_command` 返回 `None`。

### 2.2 `list`

一次拉两张表,都不带 platform 过滤(= 遍历目录里所有 `*-pending.json` / `*-approved.json`)。
`hermes_cli/pairing.py:33-34 @ 863e313`

```python
    pending = store.list_pending()
    approved = store.list_approved()
```

表头把 `request_id` 排在第二列——**这是「门外那把钥匙」的实际形状**:操作员从这里抄 request-id,
而不是抄 code(code 只存 hash,永远不出现在这张表里)。`hermes_cli/pairing.py:42 @ 863e313`

```python
        print(f"  {'Platform':<12} {'Request ID':<18} {'User ID':<20} {'Name':<20} {'Age'}")
```

行渲染对 `request_id` 做了 `or '-'` 兜底——因为 legacy 明文 pending 条目的 `request_id` 是空串(见 §3.5)。
`hermes_cli/pairing.py:44-48 @ 863e313`

```python
        for p in pending:
            print(
                f"  {p['platform']:<12} {(p.get('request_id') or '-'):<18} {p['user_id']:<20} "
                f"{(p.get('user_name') or ''):<20} {p['age_minutes']}m ago"
            )
```

尾巴上的两行提示,明确了「两种钥匙都能开」的产品语义。`hermes_cli/pairing.py:49-50 @ 863e313`

```python
        print("\n  Approve with: hermes pairing approve <platform> <request-id>")
        print("  The code the bot DM'd the user also works if they relay it.")
```

approved 表只有三列,**不显示 `approved_at`**(store 里是存了的,见 §3.3)。
`hermes_cli/pairing.py:58-59 @ 863e313`

```python
        for a in approved:
            print(f"  {a['platform']:<12} {a['user_id']:<20} {(a.get('user_name') or ''):<20}")
```

### 2.3 `approve` —— 本段最重要的 35 行

流程:normalize → 形状判别 → 二选一调用 → 三分支报告。

```
platform.lower().strip()
code.strip()
        │
        ├─ looks_like_request_id(code) ── True ──▶ store.approve_request(platform, code)
        └────────────────────────────── False ──▶ store.approve_code(platform, code.upper())
                                                          │
                        ┌─────────────────────────────────┼──────────────────────────────┐
                     result 真                       result 假 且 _is_locked_out      其余
                        │                                 │                              │
                  打印 "Approved!"                 打印 "locked out" + 剩余分钟      打印 "not found or expired"
```

归一化两行。`hermes_cli/pairing.py:68-69 @ 863e313`

```python
    platform = platform.lower().strip()
    code = code.strip()
```

形状判别与二选一。`hermes_cli/pairing.py:71-74 @ 863e313`

```python
    if store.looks_like_request_id(code):
        result = store.approve_request(platform, code)
    else:
        result = store.approve_code(platform, code.upper())
```

成功分支拼一个 `Name (id)` 的显示串。`hermes_cli/pairing.py:75-80 @ 863e313`

```python
    if result:
        uid = result["user_id"]
        name = result.get("user_name") or ""
        display = f"{name} ({uid})" if name else uid
        print(f"\n  Approved! User {display} on {platform} can now use the bot~")
        print("  They'll be recognized automatically on their next message.\n")
```

**锁定分支——封装破坏的现场**。`hermes_cli/pairing.py:81 @ 863e313`

```python
    elif store._is_locked_out(platform):
```

紧接着三行,把 store 的私有存储 schema 整个复刻进 CLI:自己拿路径、自己读 JSON、自己拼 `_lockout:` 键。
`hermes_cli/pairing.py:86-89 @ 863e313`

```python
        limits = store._load_json(store._rate_limit_path())
        lockout_until = limits.get(f"_lockout:{platform}", 0)
        remaining = max(0, int(lockout_until - _time.time()))
        mins = remaining // 60
```

然后打印的补救路径是**硬编码字面量**,而不是上一行刚拿到的 `store._rate_limit_path()`。
`hermes_cli/pairing.py:95-98 @ 863e313`

```python
        print(
            "  To reset sooner, delete the '_lockout:{0}' entry from "
            "~/.hermes/platforms/pairing/_rate_limits.json\n".format(platform)
        )
```

失败兜底分支。`hermes_cli/pairing.py:99-101 @ 863e313`

```python
    else:
        print(f"\n  Pairing request or code '{code}' not found or expired for platform '{platform}'.")
        print("  Run 'hermes pairing list' to see pending requests.\n")
```

注释里写明了 `elif` 存在的理由是「消歧」,并给了 issue 号。`hermes_cli/pairing.py:82-84 @ 863e313`

```python
        # Disambiguate: approve_code returns None for both invalid codes
        # and lockout. Tell the operator it's lockout so they don't chase
        # a "wrong code" rabbit hole (#10195).
```

**问题**:这个 `elif` 挂在**整个 if/else 之后**,不区分刚才走的是 `approve_request` 还是 `approve_code`。
而 `approve_request` 根本不受锁定门控(§3.4)。于是「平台正好在锁定期 + 操作员点了一条过期的 request-id」
会被报成锁定——正好是 dashboard 用一行 `not by_request_id` 显式挡掉的那个误报(§4.2)。

### 2.4 `revoke`

`hermes_cli/pairing.py:104-111 @ 863e313`

```python
def _cmd_revoke(store, platform: str, user_id: str):
    """Revoke a user's access."""
    platform = platform.lower().strip()

    if store.revoke(platform, user_id):
        print(f"\n  Revoked access for user {user_id} on {platform}.\n")
    else:
        print(f"\n  User {user_id} not found in approved list for {platform}.\n")
```

注意 `user_id` **不做 strip、不做 normalize**——归一化完全交给 `store.revoke` 内部的 alias 匹配(§3.3)。
`platform` 做了 lower/strip,`user_id` 没有:一个尾随空格的 user_id 靠 `_user_id_aliases` 里的
`str(user_id or "").strip()` 兜住,能匹配上,所以不是 bug,但不对称。

### 2.5 `clear-pending`

`hermes_cli/pairing.py:114-120 @ 863e313`

```python
def _cmd_clear_pending(store):
    """Clear all pending pairing codes."""
    count = store.clear_pending()
    if count:
        print(f"\n  Cleared {count} pending pairing request(s).\n")
    else:
        print("\n  No pending requests to clear.\n")
```

无确认、无 platform 过滤、无 dry-run。

---

## 3. CLI 用到的 `gateway/pairing.py` 方法(签名 + 关键实现)

### 3.0 store 的落盘位置(决定了 CLI 到底在改哪个文件)

模块级常量,**import 时求值一次**。`gateway/pairing.py:59 @ 863e313`

```python
PAIRING_DIR = get_hermes_dir("platforms/pairing", "pairing")
```

`get_hermes_dir` 的语义是「legacy 目录**有内容**就用 legacy,否则用新路径」。`hermes_constants.py:278-282 @ 863e313`

```python
    home = home or get_hermes_home()
    old_path = home / old_name
    if _legacy_path_has_content(old_path):
        return old_path
    return home / new_subpath
```

`get_hermes_home()` 的解析链是:context-local override → `HERMES_HOME` 环境变量 → 平台默认。
读环境变量在这里。`hermes_constants.py:71-74 @ 863e313`

```python
    val = os.environ.get("HERMES_HOME", "").strip()
    if val:
        return Path(val)
    return _get_platform_default_hermes_home()
```

构造器:传 profile 走 `<root>/profiles/<name>`,不传就用模块级常量。
`gateway/pairing.py:424-437 @ 863e313`

```python
        if profile:
            root = get_default_hermes_root()
            profile_home = (
                root
                if profile == "default"
                else root / "profiles" / profile
            )
            self._dir = get_hermes_dir(
                "platforms/pairing",
                "pairing",
                home=profile_home,
            )
        else:
            self._dir = PAIRING_DIR
```

**这就是 §0 第 5 点的根因**:`else` 分支拿的是 import 时定死的值,任何 context-local 的 HERMES_HOME
覆写都够不到它。

一把 `RLock` 保护所有 read-modify-write。`gateway/pairing.py:450 @ 863e313`

```python
        self._lock = threading.RLock()
```

**注意锁的作用域是「一个 PairingStore 实例」**,不是文件。CLI 进程和 gateway 进程各自持有自己的
`PairingStore`,两个进程同时改同一个 `<platform>-pending.json` 时,`RLock` 不提供任何保护;
唯一的保护是 `_secure_write` 的 tmp+rename 原子替换(读者不会看到半截文件),但
「读-改-写」整体仍可丢更新(§5 defect D7)。

### 3.1 `looks_like_request_id(value) -> bool`(staticmethod)

`gateway/pairing.py:723-733 @ 863e313`

```python
    @staticmethod
    def looks_like_request_id(value: str) -> bool:
        """True when ``value`` has the shape of a ``list_pending`` request id.

        Request ids are ``secrets.token_hex(8)`` (16 lowercase hex chars);
        pairing codes are 8 chars from an unambiguous uppercase alphabet that
        excludes every hex letter's ambiguity partner. The two shapes cannot
        collide, so callers accepting either can dispatch on this.
        """
        value = str(value or "").strip()
        return len(value) == 16 and all(c in "0123456789abcdefABCDEF" for c in value)
```

**判别依据是长度 16 + 全 hex**。code 是 8 位、字母表 `ABCDEFGHJKLMNPQRSTUVWXYZ23456789`
(`gateway/pairing.py:47-48 @ 863e313`)

```python
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 8
```

长度就已经不可能撞(8 ≠ 16),docstring 里「字母表排除了 hex 字母的歧义伙伴」这句其实是多余的论据
——真正起作用的是长度。**这条判别是纯形状的,不查库**:一个长度 16 的任意 hex 串会被判成 request-id,
一个长度 15 的手滑 request-id 会被判成 code(§5 defect D3)。

### 3.2 `approve_request(platform, request_id) -> Optional[dict]`

`gateway/pairing.py:735 @ 863e313`

```python
    def approve_request(self, platform: str, request_id: str) -> Optional[dict]:
```

docstring 里把「为什么这条路不计失败、也不受锁定门控」写得很清楚——这是本段最关键的一条设计意图。
`gateway/pairing.py:745-751 @ 863e313`

```python
        Unlike :meth:`approve_code` this does NOT count a miss toward the
        brute-force lockout, and is not itself gated by one. The lockout
        protects the 8-char code space against guessing over a messaging
        channel; a request id is only ever obtained by an admin already
        authenticated to this store, so a stale id means "the row you clicked
        expired", not an attack. Counting it here let a few GUI clicks on a
        stale list lock the operator out of the CLI's code path too.
```

实现:持锁 → 清过期 → 小写归一 → 线性扫 pending,**跳过没有 salt/hash 的 legacy 条目**,
用 `compare_digest` 比 entry_id。`gateway/pairing.py:753-768 @ 863e313`

```python
        with self._lock:
            self._cleanup_expired(platform)
            request_id = str(request_id or "").strip().lower()
            if not request_id:
                return None

            pending = self._load_json(self._pending_path(platform))
            for entry_id, entry in pending.items():
                if not isinstance(entry, dict):
                    continue
                if "salt" not in entry or "hash" not in entry:
                    continue
                if secrets.compare_digest(str(entry_id).lower(), request_id):
                    return self._finish_approval(platform, pending, entry_id, entry)

            return None
```

**设计取舍**:request-id 用 `compare_digest` 做常量时间比较,其实并无必要(request-id 本来就在
`pairing list` 里明文给了操作员看),但这是一致的防御性风格,成本近似为零。
真正有意义的是 `if "salt" not in entry` 那两行——它保证 legacy 明文条目**没有任何可批准的 id**,
必须靠 TTL 老死。

### 3.3 `approve_code(platform, code) -> Optional[dict]` 与授权落盘

`gateway/pairing.py:665 @ 863e313`

```python
    def approve_code(self, platform: str, code: str) -> Optional[dict]:
```

**锁定检查必须在 pending 查找之前**,注释解释了为什么(否则锁定只挡发码不挡批准)。
`gateway/pairing.py:684-690 @ 863e313`

```python
            # Lockout check — must run before the pending lookup so a
            # valid code (e.g. one already sitting in pending) cannot be
            # accepted once the lockout fires. Without this, the lockout
            # only blocks `generate_code`, not `approve_code` — nullifying
            # the brute-force protection for any code already issued.
            if self._is_locked_out(platform):
                return None
```

匹配失败 → **计一次失败**。`gateway/pairing.py:717-719 @ 863e313`

```python
            if matched_key is None:
                self._record_failed_attempt(platform)
                return None
```

成功共用 `_finish_approval`:删 pending → 存盘 → **重置失败计数** → 写 approved。
`gateway/pairing.py:589-598 @ 863e313`

```python
        del pending[matched_key]
        self._save_json(self._pending_path(platform), pending)

        # A successful approval proves the requester is legitimate, so the
        # brute-force failure streak must not carry over. Without this,
        # isolated mistyped codes accumulate across the gateway's lifetime
        # (the counter is persisted in _rate_limits.json and only ever
        # reset when a lockout fires) and eventually trip a spurious
        # lockout on a single fresh typo — rejecting even a valid code.
        self._reset_failed_attempts(platform)
```

`_approve_user` 除了写 `<platform>-approved.json`,还会**把授权镜像进操作员的 allowlist 环境变量**。
`gateway/pairing.py:546-555 @ 863e313`

```python
        approved[normalized_user_id] = {
            "user_name": user_name,
            "approved_at": time.time(),
        }
        self._save_json(self._approved_path(platform), approved)

        # Mirror the grant into the operator's allowlist when one is configured
        # (option i), so the pairing store and the allowlist stay a single
        # visible source of truth. No-op on open gateways.
        _sync_allowlist_add(platform, normalized_user_id)
```

镜像策略是 **option (i):只有已经配了 allowlist 才写入**,否则什么都不做——避免「第一次配对把开放
网关悄悄变成封闭网关」。`gateway/pairing.py:184-193 @ 863e313`

```python
    env_var = _allowlist_env_for_platform(platform)
    if not env_var:
        return
    current = _read_allowlist_env(env_var)
    if not current:
        return  # No allowlist configured — leave the gateway open (option i).
    ids = _split_allowlist(current)
    if "*" in ids or str(user_id) in ids:
        return  # Already covered.
    ids.append(str(user_id))
```

写入用 `hermes_cli.config.save_env_value`,**整段 try/except 吞掉一切异常**。
`gateway/pairing.py:194-201 @ 863e313`

```python
    try:
        from hermes_cli.config import save_env_value

        save_env_value(env_var, ",".join(ids))
    except Exception:
        # Best-effort: the pairing store grant still authorizes via the union,
        # so a failure here degrades to "grant recorded but not mirrored".
        pass
```

### 3.4 `revoke(platform, user_id) -> bool`

`gateway/pairing.py:557-576 @ 863e313`

```python
    def revoke(self, platform: str, user_id: str) -> bool:
        """Remove a user from the approved list. Returns True if found."""
        path = self._approved_path(platform)
        with self._lock:
            approved = self._load_json(path)
            matching_ids = [
                approved_user_id
                for approved_user_id in approved
                if self._user_ids_match(platform, approved_user_id, user_id)
            ]
            if matching_ids:
                for approved_user_id in matching_ids:
                    del approved[approved_user_id]
                self._save_json(path, approved)
                # Keep the allowlist mirror in sync: revoking a paired user
                # also removes the entry the approval added (option i). No-op if
                # the user was added to the allowlist by other means.
                _sync_allowlist_remove(platform, user_id)
                return True
        return False
```

**返回值语义**:`True` = 「在 approved.json 里找到并删了」。它**完全不反映 allowlist 镜像是否删成功**
——`_sync_allowlist_remove` 的写入同样被 try/except 吞掉。`gateway/pairing.py:318-327 @ 863e313`

```python
    try:
        from hermes_cli.config import save_env_value, remove_env_value

        if remaining:
            save_env_value(env_var, ",".join(remaining))
        else:
            remove_env_value(env_var)
    except Exception:
        pass
    _sync_live_adapter_allowlist_remove(platform, user_id)
```

而 `save_env_value` / `remove_env_value` 在 managed 安装下是**打印后静默返回**,不抛异常。
`hermes_cli/config.py:3865-3869 @ 863e313`

```python
def save_env_value(key: str, value: str):
    """Save or update a value in ~/.hermes/.env."""
    if is_managed():
        managed_error(f"set {key}")
        return
```

`hermes_cli/config.py:3978-3985 @ 863e313`

```python
def remove_env_value(key: str) -> bool:
    """Remove a key from ~/.hermes/.env and os.environ.

    Returns True if the key was found and removed, False otherwise.
    """
    if is_managed():
        managed_error(f"remove {key}")
        return False
```

→ **在 managed 安装 / 或 `.env` 只读的容器里,`hermes pairing revoke` 会打印「Revoked access」,
但 allowlist 里的条目还在,授权 union 仍然放行那个用户。**(§5 defect D5)

### 3.5 `list_pending` / `list_approved` / `clear_pending`

`list_pending` 每次都先清过期,并给 legacy 条目发空 `request_id`。`gateway/pairing.py:791-800 @ 863e313`

```python
                    is_modern = isinstance(info.get("hash"), str) and isinstance(
                        info.get("salt"), str
                    )
                    results.append({
                        "platform": p,
                        "request_id": str(entry_id) if is_modern else "",
                        "user_id": info.get("user_id", ""),
                        "user_name": info.get("user_name", ""),
                        "age_minutes": age_min,
                    })
```

`list_approved` 把存储里的整个 info 字典 **splat 在后面**。`gateway/pairing.py:530-531 @ 863e313`

```python
            for uid, info in approved.items():
                results.append({"platform": p, "user_id": uid, **info})
```

→ `**info` 在 `"user_id": uid` **之后**,所以 approved.json 里若出现 `user_id` / `platform` 键
(手工编辑或未来 schema 演进)会**覆盖**正确值。当前 `_approve_user` 只写 `user_name` / `approved_at`,
所以现在不会踩到;记为低危(§5 defect D6)。

`clear_pending` **不先清过期**,`count` 因此包含尚未被 TTL 剪掉的过期条目;并且对每个平台无条件写 `{}`。
`gateway/pairing.py:803-812 @ 863e313`

```python
    def clear_pending(self, platform: str = None) -> int:
        """Clear all pending requests. Returns count removed."""
        with self._lock:
            count = 0
            platforms = [platform] if platform else self._all_platforms("pending")
            for p in platforms:
                pending = self._load_json(self._pending_path(p))
                count += len(pending)
                self._save_json(self._pending_path(p), {})
        return count
```

### 3.6 `_is_locked_out` / `_record_failed_attempt` / `_rate_limit_path` / `_load_json`

四个私有件,CLI 直接用了前三个中的两个 + `_load_json`。

`gateway/pairing.py:464-465 @ 863e313`

```python
    def _rate_limit_path(self) -> Path:
        return self._dir / "_rate_limits.json"
```

`gateway/pairing.py:835-840 @ 863e313`

```python
    def _is_locked_out(self, platform: str) -> bool:
        """Check if a platform is in lockout due to failed approval attempts."""
        limits = self._load_json(self._rate_limit_path())
        lockout_key = f"_lockout:{platform}"
        lockout_until = limits.get(lockout_key, 0)
        return time.time() < lockout_until
```

`gateway/pairing.py:842-854 @ 863e313`

```python
    def _record_failed_attempt(self, platform: str) -> None:
        """Record a failed approval attempt. Triggers lockout after MAX_FAILED_ATTEMPTS."""
        limits = self._load_json(self._rate_limit_path())
        fail_key = f"_failures:{platform}"
        fails = limits.get(fail_key, 0) + 1
        limits[fail_key] = fails
        if fails >= MAX_FAILED_ATTEMPTS:
            lockout_key = f"_lockout:{platform}"
            limits[lockout_key] = time.time() + LOCKOUT_SECONDS
            limits[fail_key] = 0  # Reset counter
            print(f"[pairing] Platform {platform} locked out for {LOCKOUT_SECONDS}s "
                  f"after {MAX_FAILED_ATTEMPTS} failed attempts", flush=True)
        self._save_json(self._rate_limit_path(), limits)
```

`_load_json` **对 `PermissionError` 特判打 warning,其余 OSError / JSONDecodeError 一律返回 `{}`**。
`gateway/pairing.py:495-497 @ 863e313`

```python
            except (json.JSONDecodeError, OSError):
                return {}
        return {}
```

这是 CLI 借用它时的第二个脆点:`_rate_limits.json` 损坏 / 不可读 → `{}` → `lockout_until = 0` →
CLI 打印「Lockout clears in ~0 minute(s)」,而实际上 `_is_locked_out` 也会因为同一个 `{}` 返回 False,
所以这一分支进不去——**两个私有读各自独立地被同一个静默失败污染,只是碰巧互相抵消**。
一旦哪天 `_is_locked_out` 改成从别处(内存缓存 / SQLite)读、而 `_load_json` 仍读文件,
CLI 就会进到分支里打出 `~0 minute(s)`。这就是「破坏封装为什么脆」的具体形态。

常量表(CLI 提示里的「~N 分钟」「5 次」全部来自这里,但 CLI **没有 import 它们**,只 import 了 `time`):
`gateway/pairing.py:51-57 @ 863e313`

```python
CODE_TTL_SECONDS = 3600             # Codes expire after 1 hour
RATE_LIMIT_SECONDS = 600            # 1 request per user per 10 minutes
LOCKOUT_SECONDS = 3600              # Lockout duration after too many failures

# Limits
MAX_PENDING_PER_PLATFORM = 3        # Max pending codes per platform
MAX_FAILED_ATTEMPTS = 5             # Failed approvals before lockout
```

---

## 4. 第二把钥匙:`hermes_cli/web_server.py` 的 pairing 路由

### 4.1 路由清单与鉴权

四条路由,全部在 `hermes_cli/web_server.py` 的这一段(注释自陈「远程 admin 无 shell 时的 onboarding 入口」)。
`hermes_cli/web_server.py:12280-12284 @ 863e313`

```python
# ---------------------------------------------------------------------------
# Pairing endpoints — approve / revoke / list messaging pairing codes.
#
# These are how a remote admin onboards messaging users (Telegram, Discord, …)
# without shell access.  Wraps gateway.pairing.PairingStore directly.
```

| 路由 | 方法 | profile 来源 | 调 store 的哪个方法 |
|---|---|---|---|
| `/api/pairing` | GET | query `?profile=` | `list_pending()` + `list_approved()` |
| `/api/pairing/approve` | POST | **body** `profile` | `approve_request` 或 `approve_code`(+ `_is_locked_out`) |
| `/api/pairing/revoke` | POST | **body** `profile` | `revoke` |
| `/api/pairing/clear-pending` | POST | query `?profile=` | `clear_pending()` |

**鉴权:四条路由都不调 `_require_token`,靠全局中间件兜底。** 中间件对所有 `/api/` 前缀强制会话 token,
除非路径在公共白名单里。`hermes_cli/web_server.py:663-670 @ 863e313`

```python
    path = request.url.path
    is_mcp_oauth_callback = path.startswith("/api/mcp/oauth/callback/")
    if path.startswith("/api/") and path not in _PUBLIC_API_PATHS and not is_mcp_oauth_callback:
        if not _has_valid_session_token(request) and not _has_valid_query_token(request, path):
            return JSONResponse(
                status_code=401,
                content={"detail": "Unauthorized"},
            )
```

白名单只有 6 条,**没有任何 pairing 路径**。`hermes_cli/dashboard_auth/public_paths.py:33-38 @ 863e313`

```python
PUBLIC_API_PATHS: frozenset[str] = frozenset({
    # Minimal process liveness probe for desktop/backend boot handshakes. It
    # intentionally avoids gateway config, platform discovery, MCP setup, and
    # host-local detail so readiness checks cannot spend their budget inside
    # cold plugin imports.
    "/api/health",
```

非 loopback 绑定时改由 OAuth/cookie 网关裁决(`auth_required` 为真则本中间件直接放行,交给上游)。
`hermes_cli/web_server.py:661-662 @ 863e313`

```python
    if getattr(request.app.state, "auth_required", False):
        return await call_next(request)
```

`auth_required` 的取值规则:**非 loopback 一律要网关,`--insecure` 已不再能关掉它**。
`hermes_cli/web_server.py:491 @ 863e313`

```python
    return host not in _LOOPBACK_HOST_VALUES
```

另外还有一条 bearer-token 旁路(service-to-service),但**只对显式注册过的路径生效**,
全仓唯一注册者是 `/api/gateway/drain`(`plugins/dashboard_auth/drain/__init__.py:280 @ 863e313`),
pairing 路由不在其列。

⇒ **结论:三条 pairing 变更路由的鉴权 = 「dashboard 管理员」**(loopback 下是注入 SPA 的 `_SESSION_TOKEN`,
非 loopback 下是 OAuth/password 会话 cookie)。没有更细的 RBAC——能开 dashboard 就能批准任何人配对。

请求体模型(`code` 与 `request_id` 都有默认空串,`profile` 可选)。
`hermes_cli/web_models.py:429-439 @ 863e313`

```python
class PairingApprove(BaseModel):
    platform: str
    code: str = ""
    request_id: str = ""
    profile: Optional[str] = None


class PairingRevoke(BaseModel):
    platform: str
    user_id: str
    profile: Optional[str] = None
```

### 4.2 `POST /api/pairing/approve` 的流程,以及与 CLI 的差异

`hermes_cli/web_server.py:12321-12333 @ 863e313`

```python
@app.post("/api/pairing/approve")
async def approve_pairing(body: PairingApprove):
    store = _pairing_store(body.profile)
    platform = (body.platform or "").lower().strip()
    # `request_id` is what an admin surface sends after listing pending
    # requests; `code` is the one-time code the user relays from their DM.
    # A GUI that only knows the older field name still works — a value with
    # request-id shape routes to the request path either way.
    target = (body.request_id or body.code or "").strip()
    if not platform or not target:
        raise HTTPException(
            status_code=400, detail="platform and request_id or code are required"
        )
```

**差异 1(路由判别)**:dashboard 是「字段优先 + 形状兜底」,CLI 是「纯形状」。
`hermes_cli/web_server.py:12335-12339 @ 863e313`

```python
    by_request_id = bool(body.request_id) or store.looks_like_request_id(target)
    if by_request_id:
        result = store.approve_request(platform, target)
    else:
        result = store.approve_code(platform, target.upper())
```

**差异 2(锁定报告)——这是本段最重要的不一致**。dashboard 用 `not by_request_id` 把锁定报告
限制在 code 路径,并在注释里写明了理由;CLI 没有这个条件。
`hermes_cli/web_server.py:12343-12350 @ 863e313`

```python
    # Lockout only gates the code path, so only report it there — otherwise a
    # stale request id would surface as a bogus 429 while the platform sat
    # locked out for an unrelated reason.
    if not by_request_id and store._is_locked_out(platform):
        raise HTTPException(
            status_code=429,
            detail=f"Platform '{platform}' is locked out after too many failed approvals.",
        )
```

对照 `hermes_cli/pairing.py:81 @ 863e313`

```python
    elif store._is_locked_out(platform):
```

⇒ **同一个误报,dashboard 挡了,CLI 没挡。** 复现:任一平台先被 5 次错码打进锁定期,
操作员再 `hermes pairing approve telegram <一条已过期的 request-id>`,
CLI 会说「Platform 'telegram' is locked out」并建议去删 `_lockout:` 条目,
而真实原因是那一行 pending 已经过 TTL 被 `_cleanup_expired` 剪掉了。
删掉 lockout 条目也不会让这条 request-id 变得可用——操作员被指向了错误的补救动作。

**差异 3(封装破坏程度)**:dashboard 只借了 `_is_locked_out` 一个私有方法;
CLI 借了 `_is_locked_out` + `_load_json` + `_rate_limit_path` **加上私有 JSON 的键名格式**。

**差异 4(失败可判)**:dashboard 404 / 429 / 400;CLI 全部 exit 0。

**差异 5(信息量)**:CLI 会算并打印剩余分钟数与文件路径,dashboard 只给一句话。
从「最小信息泄露」角度 dashboard 更保守,从「操作员自助」角度 CLI 更有用——但 CLI 那条路径写错了(§5 D2)。

**一致的部分**:两边都 `platform.lower().strip()`;两边都对 code 走 `.upper()`;
两边都用同一个 `looks_like_request_id`;两边都不做二次确认。

### 4.3 profile 作用域:`_pairing_store`

`hermes_cli/web_server.py:12288-12309 @ 863e313`

```python
def _pairing_store(profile: Optional[str] = None):
    """Pairing store for ``profile`` — the dashboard's own when unspecified.

    Every other admin endpoint scopes by profile, and the gateway already
    keeps one store per served profile (``gateway/run.py``). Without this the
    dashboard and desktop always read the global store, so an operator on a
    named profile approves into a whitelist their gateway never consults.

    ``PairingStore`` resolves the profile's home itself (``default`` maps back
    to the global store), so this only needs to validate the name — no
    ``_profile_scope`` needed, and nothing process-global is swapped across
    the ``await`` boundary.
    """
    from gateway.pairing import PairingStore

    requested = (profile or "").strip()
    if not requested or requested.lower() == "current":
        return PairingStore()

    _resolve_profile_dir(requested)  # 400/404 on an unknown profile

    return PairingStore(profile=requested)
```

docstring 明说了为什么**不**用 `_profile_scope`:那玩意会跨 `await` 换进程全局。
这是正确做法,并且顺手解释了 §4.4 里第三把钥匙为什么是坏的。

### 4.4 第三把钥匙(R7C 没点名):`WS /api/console`

dashboard 内嵌一个「安全命令控制台」,把 CLI 的 parser + handler 直接拉进 dashboard 进程执行。
注册表里 pairing 的四个动作齐全,后三个被标为 mutating(需二次确认)。
`hermes_cli/console_engine.py:784-789 @ 863e313`

```python
            "pairing": (
                "hermes_cli.subcommands.pairing",
                "build_pairing_parser",
                "cmd_pairing",
                [("list",), ("approve",), ("revoke",), ("clear-pending",)],
                {("approve",), ("revoke",), ("clear-pending",)},
            ),
```

mutating 的语义是「未确认就返回 confirm_required,不执行」。`hermes_cli/console_engine.py:523-529 @ 863e313`

```python
            if command.mutating and not confirmed:
                return ConsoleResult(
                    "confirm_required",
                    command=raw_line,
                    confirmation_message=command.confirmation
                    or f"Run `{command.usage}`?",
                )
```

⇒ **console 是三把钥匙里唯一带二次确认的**;CLI 和 REST 都是一次调用直接生效。

入口是 WebSocket。`hermes_cli/web_server.py:15306-15307 @ 863e313`

```python
@app.websocket("/api/console")
async def console_ws(ws: WebSocket) -> None:
```

**profile 串档**:执行时用 `_profile_scope(profile)` 包住。`hermes_cli/web_server.py:15146-15149 @ 863e313`

```python
    # _profile_scope swaps process-global skill module paths; keep it inside
    # the worker thread and never hold it across awaits.
    with _profile_scope(profile):
        return engine.execute(line, confirmed=confirmed)
```

而 `_profile_scope` 靠的是 **context-local** 的 `set_hermes_home_override`。
`hermes_cli/web_server.py:13609-13610 @ 863e313`

```python
        profile_dir = _resolve_profile_dir(requested)
        token = set_hermes_home_override(str(profile_dir))
```

`set_hermes_home_override` **刻意不动 `os.environ`**。`hermes_constants.py:30-37 @ 863e313`

```python
def set_hermes_home_override(path: str | Path | None) -> Token:
    """Set a context-local Hermes home override and return its reset token.

    This is for in-process, per-task scoping.  It deliberately does not mutate
    ``os.environ`` because that is shared by every thread in the process.
    """
    value: str | object = _UNSET if path is None else str(path)
    return _HERMES_HOME_OVERRIDE.set(value)
```

而 console 走的 `pairing_command` 里构造的是**不带 profile 的** `PairingStore()`
(`hermes_cli/pairing.py:15 @ 863e313`),它取 `PAIRING_DIR`——模块级、import 时定死
(`gateway/pairing.py:437 @ 863e313` 的 `else` 分支)。

⇒ **在 dashboard 长驻进程里,通过 console 对某个具名 profile 执行 `pairing approve`,
写入的是 dashboard 自己 HERMES_HOME 下的 pairing 目录,不是被选中 profile 的。**
这正是 `_pairing_store` docstring 里描述的那个故障(「operator approves into a whitelist
their gateway never consults」),REST 入口修好了,console 入口没有。(§5 defect D8)

CLI 之所以不受影响,是因为 `os.environ["HERMES_HOME"]` 在 `hermes_cli/main.py:683` 就设好了,
在 lazy import 之前。**同一段代码,进程模型一换就错**。

---

## 5. 可疑缺陷(只记录不修)

### D1 — CLI 破坏 `PairingStore` 封装(任务书点名)

**是什么**:`hermes_cli/pairing.py` 调用了三个下划线私有方法,并复刻了私有存储 schema。
`hermes_cli/pairing.py:81 @ 863e313`

```python
    elif store._is_locked_out(platform):
```

`hermes_cli/pairing.py:86-87 @ 863e313`

```python
        limits = store._load_json(store._rate_limit_path())
        lockout_until = limits.get(f"_lockout:{platform}", 0)
```

**为什么脆**(四条,按严重度):

1. **键名格式是复制的,不是共享的**。真值在 `gateway/pairing.py:849 @ 863e313`

   ```python
            lockout_key = f"_lockout:{platform}"
   ```

   两处各写一遍。改动一侧不会有任何编译期/运行期报错——`limits.get(..., 0)` 静默返回 0,
   `remaining` 变 0,CLI 打印「Lockout clears in ~0 minute(s)」。**失败模式是「打印一句假话」,不是崩溃。**
2. **`_load_json` 是设计成静默吞错的**(`gateway/pairing.py:495-497`),CLI 借它读同一个文件,
   于是把 store 内部的「读不到就当空」策略暴露成了用户可见的错误数字。
3. **存储后端一旦从「一个 JSON 文件」换成别的**(SQLite / 内存 / 远端),`_rate_limit_path()` 与
   `_load_json()` 这对组合立刻失去意义,而 `_is_locked_out()` 还能用——CLI 会分裂成「判断对、数字错」。
4. **锁没了**。store 内部所有读-改-写都在 `self._lock` 下;CLI 这两行在锁外裸读。
   单进程 CLI 目前无并发,但这条约定被打破后,任何人把 `pairing_command` 搬进多线程宿主
   (**console 已经把它搬进 dashboard 的线程池了**,`hermes_cli/web_server.py:15148`)就成了真竞态。

**正确姿势**:store 应当暴露一个 `lockout_remaining_seconds(platform) -> int` 或让
`approve_*` 返回结构化失败原因(`{"error": "locked_out", "retry_after": 1234}`),
CLI/REST 各自渲染。现在的形态是「私有实现细节泄漏成了两个调用方的公共依赖」。

### D2 — CLI 在 request-id 路径也报锁定(dashboard 已修,CLI 未修)

见 §4.2。锚点:`hermes_cli/pairing.py:81 @ 863e313` 的 `elif` 无 `by_request_id` 条件,
对照 `hermes_cli/web_server.py:12346 @ 863e313` 的 `if not by_request_id and ...`。
**怎么会踩到**:平台处于锁定期时点/敲一条已过期的 request-id,得到错误诊断 + 错误补救建议。

### D3 — 形状判别失手会把 request-id 手滑计进暴力破解计数

`looks_like_request_id` 要求**恰好** 16 位 hex(`gateway/pairing.py:733 @ 863e313`)

```python
        return len(value) == 16 and all(c in "0123456789abcdefABCDEF" for c in value)
```

少抄一位(15 位)或多抄一位(17 位)→ 判为 code → 走 `approve_code` → 不匹配 →
`_record_failed_attempt`(`gateway/pairing.py:718 @ 863e313`)。
**5 次这样的手滑就把整个平台锁 1 小时**,而锁定不仅挡批准,还挡 `generate_code`
(`gateway/pairing.py:628 @ 863e313`)——新用户连码都拿不到。
`approve_request` 明确设计成不计数(§3.2 docstring),但**形状判别错了就享受不到这个保护**。
dashboard 侧因为有 `bool(body.request_id)` 优先,SPA 传字段名就不会踩;**CLI 无法避免**。

### D4 — `hermes pairing` 所有失败路径 exit 0

`pairing_command` 四条分支全部只 print 不 return(`hermes_cli/pairing.py:18-28`);
转发层也是裸调用(`hermes_cli/main.py:11159-11162`);main 只在返回非零 int 时才 exit。
`hermes_cli/main.py:12590-12593 @ 863e313`

```python
    if hasattr(args, "func"):
        rc = args.func(args)
        if isinstance(rc, int) and rc != 0:
            sys.exit(rc)
```

**怎么会踩到**:`hermes pairing approve telegram WRONGCOD && notify-ok` —— 批准失败,但 `&&` 照样执行。
运维脚本/Ansible/CI 无法判定批准是否真的生效,只能去 grep stdout 中文提示串。

### D5 — `revoke` 在 allowlist 镜像失败时仍报「Revoked」

`store.revoke` 的返回值只反映 approved.json(§3.4),allowlist 侧写入被
`except Exception: pass` 吞掉(`gateway/pairing.py:325-326 @ 863e313`)

```python
    except Exception:
        pass
```

而 managed 安装下 `save_env_value` / `remove_env_value` 根本不抛异常,只打印后返回
(`hermes_cli/config.py:3867-3869`、`hermes_cli/config.py:3983-3985`)。
**怎么会踩到**:企业 managed 部署里 `hermes pairing revoke telegram 123` 打印
「Revoked access for user 123 on telegram.」,但 `TELEGRAM_ALLOWED_USERS` 里那一条还在;
授权是 pairing store 与 allowlist 的 **union**(`gateway/authz_mixin.py:582-587 @ 863e313`)

```python
        # grant, created only by a trusted operator approving a pairing code
        # (hermes gateway pairing approve / the authenticated dashboard) — an
        # inbound sender can never reach approve_code, so this is not an
        # attacker-controlled path. Honored as a UNION with the allowlist: a
        # paired user is authorized regardless of the allowlist, and when an
        # allowlist IS configured, operator approval also writes the user into
```

→ 被「撤销」的用户仍然被放行。REST `/api/pairing/revoke` 同病(它也只看 `store.revoke` 的布尔)。

### D6 — `list_approved` 的 `**info` 可覆盖 `user_id` / `platform`

`gateway/pairing.py:531 @ 863e313`

```python
                results.append({"platform": p, "user_id": uid, **info})
```

`**info` 在后,同名键胜出。当前写入方只放 `user_name`/`approved_at`,不会撞;
手工编辑过的 approved.json 或未来 schema 加了 `user_id` 字段就会让 `hermes pairing list`
与 `GET /api/pairing` 显示错误的 user_id,而 `revoke <显示出来的 id>` 会失败。低危,但零成本可防
(把 `**info` 放前面)。

### D7 — 跨进程「读-改-写」丢更新(锁只在实例内)

`self._lock` 是 `threading.RLock`(`gateway/pairing.py:450`),只保护同一个 `PairingStore` 实例。
CLI 进程、gateway 进程、dashboard 进程各有自己的实例,却写同一批 JSON 文件。
`_secure_write` 只保证单次替换原子(`gateway/pairing.py:386-392 @ 863e313`)

```python
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        atomic_replace(tmp_path, path)
```

**怎么会踩到**:gateway 正在给用户 B 发码(写 pending),操作员同时 `hermes pairing approve ... A`
(读 pending → 删 A → 整表写回)→ B 的 pending 条目被覆盖掉,B 拿到的码永远匹配不上,
且每次尝试都 `_record_failed_attempt`。窗口很窄,但这是 pairing 唯一无文件锁的写路径。

### D8 — console 入口的 profile 串档

见 §4.4。锚点三连:`hermes_cli/pairing.py:15`(构造不带 profile)、
`gateway/pairing.py:437`(`self._dir = PAIRING_DIR`,import 时定死)、
`hermes_cli/web_server.py:15148`(`with _profile_scope(profile)` 只设 context-local override)。
**怎么会踩到**:dashboard 上切到 profile `work`,打开 console,敲
`pairing approve telegram <id>` 并确认 → 写进 dashboard 自己 profile 的 pairing 目录;
`work` 的 gateway 永远读不到这条授权,用户仍被拒。而同一个 dashboard 上点「Approve」按钮
(走 REST + `PairingStore(profile="work")`)是对的。**两个 UI 元素、同一个页面、相反的结果。**

### D9 — CLI 打印的补救文件路径可能是错的

`hermes_cli/pairing.py:96-97 @ 863e313`

```python
            "  To reset sooner, delete the '_lockout:{0}' entry from "
            "~/.hermes/platforms/pairing/_rate_limits.json\n".format(platform)
```

真值就在上面第 86 行的 `store._rate_limit_path()` 里,但没被用。三种情形下这个字面量是错的:
(a) legacy 布局 → `~/.hermes/pairing/_rate_limits.json`(`hermes_constants.py:280-281`);
(b) `hermes -p work ...` → `~/.hermes/profiles/work/platforms/pairing/...`;
(c) `HERMES_HOME=/opt/data` 的 Docker → `/opt/data/platforms/pairing/...`。
**Docker 是官方推荐部署方式**,所以 (c) 命中率不低。

---

## 6. 文档 / 注释与代码的出入

| # | 文档说 | 代码做 | 锚点 |
|---|---|---|---|
| C1 | 「Storage: `~/.hermes/pairing/`」 | 新装是 `~/.hermes/platforms/pairing/`;legacy 目录**有内容**才回落 | `gateway/pairing.py:18` vs `gateway/pairing.py:59` + `hermes_constants.py:280` |
| C2 | 官网 security.md 同样写 `~/.hermes/pairing/` | 同上 | `website/docs/user-guide/security.md:437` |
| C3 | cli-commands.md 写 `approve <platform> <code>` | 实际 metavar 是 `request-id\|code`,首选 request-id | `website/docs/reference/cli-commands.md:1119` vs `hermes_cli/subcommands/pairing.py:31` |
| C4 | web-dashboard.md 写 approve body 是 `{platform, code}` | 模型有 `code`/`request_id`/`profile` 三个字段,SPA 只发 `request_id`+`profile` | `website/docs/user-guide/features/web-dashboard.md:528` vs `hermes_cli/web_models.py:429` |
| C5 | web-dashboard.md 四条路由全无 `profile` 说明 | list/clear-pending 收 query `profile`,approve/revoke 收 body `profile` | 同上 vs `hermes_cli/web_server.py:12313` / `12372` |
| C6 | authz 注释写命令是 `hermes gateway pairing approve` | 实际命令是 `hermes pairing approve`(parser 挂在顶层 subparsers) | `gateway/authz_mixin.py:583` vs `hermes_cli/main.py:11601` |
| C7 | `save_env_value` docstring 写「~/.hermes/.env」 | 实际是 `get_hermes_home()/.env`,随 profile/HERMES_HOME 变 | `hermes_cli/config.py:3866` vs `hermes_cli/config.py:698-700` |

逐条证据:

C1 —— `gateway/pairing.py:18 @ 863e313`

```
Storage: ~/.hermes/pairing/
```

C2 —— `website/docs/user-guide/security.md:437 @ 863e313`

```markdown
**Storage:** Pairing data is stored in `~/.hermes/pairing/` with per-platform JSON files:
```

C3 —— `website/docs/reference/cli-commands.md:1119 @ 863e313`

```markdown
| `approve <platform> <code>` | Approve a pairing code. |
```

C4/C5 —— `website/docs/user-guide/features/web-dashboard.md:528 @ 863e313`

```markdown
| `POST /api/pairing/approve` | Approve a code. Body: `{platform, code}` |
```

C6 —— `gateway/authz_mixin.py:583 @ 863e313`

```python
        # (hermes gateway pairing approve / the authenticated dashboard) — an
```

C7 —— `hermes_cli/config.py:698-700 @ 863e313`

```python
def get_env_path() -> Path:
    """Get the .env file path (for API keys)."""
    return get_hermes_home() / ".env"
```

**另有一条「文档滞后但代码更保守」的正向出入**:`gateway/pairing.py:16` 的
「Codes are never logged to stdout」在本段成立——CLI 的 list 打的是 `request_id`,不是 code;
`_record_failed_attempt` 的 print 里也只有 platform 名(`gateway/pairing.py:852-853`)。

---

## 7. 配置键 / 环境变量穷举(本段)

本段**没有任何 config.yaml 键被读取**——pairing 的批准入口完全不读 config.yaml。
读到的全是环境变量,共三类。

### 7.1 存储定位

| 键 | 类型 | 默认 | 读取点 | 说明 |
|---|---|---|---|---|
| `HERMES_HOME` | env | 平台默认(POSIX `~/.hermes`;Win `%LOCALAPPDATA%\hermes`) | `hermes_constants.py:71`(`_hermes_home_from_env`) | fallback 链:context-local override → `HERMES_HOME` → 平台默认;`get_hermes_home()` `hermes_constants.py:132-139` |
| `LOCALAPPDATA` | env | `Path.home()/AppData/Local` | `hermes_constants.py:56`(`_get_platform_default_hermes_home`) | 仅 win32 分支;是 `HERMES_HOME` 未设时的下一跳 |

`hermes_constants.py:132-139 @ 863e313`

```python
    override = get_hermes_home_override()
    if override:
        return Path(override)

    if not os.environ.get("HERMES_HOME", "").strip():
        _warn_profile_fallback_once()

    return _hermes_home_from_env()
```

`hermes_constants.py:55-59 @ 863e313`

```python
    if sys.platform == "win32":
        local_appdata = os.environ.get("LOCALAPPDATA", "").strip()
        base = Path(local_appdata) if local_appdata else Path.home() / "AppData" / "Local"
        return base / "hermes"
    return Path.home() / ".hermes"
```

`get_default_hermes_root()`(profile store 用)也读同一个 `HERMES_HOME`,但语义是「找 root」:
`hermes_constants.py:179 @ 863e313`

```python
    env_home = os.environ.get("HERMES_HOME", "")
```

### 7.2 平台 allowlist 镜像(approve/revoke 会写)

18 个静态键,来自一张字面量表。读:`_read_allowlist_env`;写:`save_env_value` / `remove_env_value`。
`gateway/pairing.py:69-88 @ 863e313`

```python
_PLATFORM_ALLOWLIST_ENV = {
    "telegram": "TELEGRAM_ALLOWED_USERS",
    "discord": "DISCORD_ALLOWED_USERS",
    "whatsapp": "WHATSAPP_ALLOWED_USERS",
    "whatsapp_cloud": "WHATSAPP_CLOUD_ALLOWED_USERS",
    "slack": "SLACK_ALLOWED_USERS",
    "signal": "SIGNAL_ALLOWED_USERS",
    "email": "EMAIL_ALLOWED_USERS",
    "sms": "SMS_ALLOWED_USERS",
    "mattermost": "MATTERMOST_ALLOWED_USERS",
    "matrix": "MATRIX_ALLOWED_USERS",
    "dingtalk": "DINGTALK_ALLOWED_USERS",
    "feishu": "FEISHU_ALLOWED_USERS",
    "wecom": "WECOM_ALLOWED_USERS",
    "wecom_callback": "WECOM_CALLBACK_ALLOWED_USERS",
    "weixin": "WEIXIN_ALLOWED_USERS",
    "bluebubbles": "BLUEBUBBLES_ALLOWED_USERS",
    "qqbot": "QQ_ALLOWED_USERS",
    "yuanbao": "YUANBAO_ALLOWED_USERS",
}
```

全部 18 个:默认值均为「未设 = 无 allowlist = 开放网关」(option i,见 §3.3),值格式是逗号分隔,
`*` 表示通配且**永不被 revoke 删除**(`gateway/pairing.py:312-315`)。

第 19 个「动态键」:插件平台的 `allowed_users_env`,从 platform registry 取。
`gateway/pairing.py:101-108 @ 863e313`

```python
    try:
        from gateway.platform_registry import platform_registry

        entry = platform_registry.get(platform)
        if entry and entry.allowed_users_env:
            return entry.allowed_users_env
    except Exception:
        pass
```

**读取的 fallback 链**(三跳,含一次静默降级):
`gateway/pairing.py:163-172 @ 863e313`

```python
    try:
        from agent.secret_scope import UnscopedSecretError, get_secret

        try:
            return (get_secret(env_var) or "").strip()
        except UnscopedSecretError:
            pass
    except Exception:
        pass
    return (os.getenv(env_var) or "").strip()
```

即:profile secret scope → (scope 未装则) `os.getenv` → `""`。
**注意 scoped miss 会返回空串而不是回落到进程 env**——docstring 明写这是刻意的
(`gateway/pairing.py:150-156`),避免多 profile 复用时借到别的 profile 的 allowlist。

**已知缺口(代码自陈)**:读是 profile-aware 的,写不是。`gateway/pairing.py:158-161 @ 863e313`

```python
    TODO(profile-secrets): the grant mirror below still WRITES through
    ``hermes_cli.config.save_env_value`` / ``remove_env_value``, which target
    the root ``.env`` — those writes need a profile-aware counterpart before
    pairing grants can be mirrored correctly under multiplexing.
```

⇒ `POST /api/pairing/approve` 带 `profile=work` 时:pairing store 写对了(work 的目录),
但 allowlist 镜像写进 **dashboard 进程自己的** `.env`。这条 TODO 是官方已知,不另记 defect。

### 7.3 相邻但不属于批准入口的键(为完整性列出,已标注)

| 键 | 类型 | 写入点 | 备注 |
|---|---|---|---|
| `WHATSAPP_DM_POLICY` | env | `hermes_cli/web_server.py:8599`(子进程 env)、`hermes_cli/web_server.py:8888`(落 `.env`) | **属于 WhatsApp onboarding 向导**,不是 pairing 批准入口;向导强制写死为 `"pairing"` |
| `WHATSAPP_MODE` | env | `hermes_cli/web_server.py:8887` 附近 | 同上 |

`hermes_cli/web_server.py:8599 @ 863e313`

```python
    env["WHATSAPP_DM_POLICY"] = "pairing"
```

`hermes_cli/web_server.py:8888 @ 863e313`

```python
            save_env_value("WHATSAPP_DM_POLICY", "pairing")
```

### 7.4 dashboard 侧的鉴权相关(非 pairing 私有,但决定谁能开门)

`_SESSION_TOKEN`(进程内生成,不是环境变量)、`X-Hermes-Session-Token` 头名、
`auth_required`(`app.state`,由 `should_require_auth(host)` 算出)。
这三者都不是配置键,列在此处是因为「谁能调批准接口」的答案全在它们身上(§4.1)。

---

## 8. 配套测试(行为规格)

| 文件 | 覆盖什么 |
|---|---|
| `tests/hermes_cli/test_pairing.py` | **本段唯一的 CLI 端到端规格**,只有 1 个用例:request-id 与 bot code 两条路都能批准 |
| `tests/hermes_cli/test_dashboard_admin_endpoints.py` | `TestPairingEndpoints`:REST approve(request_id 路径)、profile 隔离、未知 profile 404 |
| `tests/hermes_cli/test_subcommands_followup.py` | parser 注册契约(`build_pairing_parser` + `cmd_pairing` 名字对得上) |
| `tests/gateway/test_pairing.py` | store 本体的完整规格(38 个用例):hash 存储、legacy 兼容、限流、锁定、过期、revoke、profile 作用域 |
| `tests/gateway/test_multiplex_pairing_stores.py` | 多 profile gateway 各读各的 store |
| `tests/gateway/test_pairing_allowlist_bypass.py` | allowlist 与 pairing 的 union 语义 |
| `tests/gateway/test_internal_event_bypass_pairing.py` | 内部事件不得绕过配对 |

**CLI 侧覆盖极薄**。唯一那个用例只走成功路径,并且用 monkeypatch 把 `PairingStore` 类整个换掉:
`tests/hermes_cli/test_pairing.py:13 @ 863e313`

```python
        with patch("gateway.pairing.PairingStore", return_value=store):
```

⇒ §5 的 D1/D2/D3/D4/D9 **全部没有测试覆盖**——CLI 的锁定分支、失败分支、退出码、
硬编码路径,一条测试都没有。相对地,store 侧对同一语义有精确测试:
`tests/gateway/test_pairing.py:332 @ 863e313`

```python
    def test_stale_request_id_never_locks_out_the_code_path(self, tmp_path):
```

这个用例名就是 D2 的规格——**store 保证了「过期 request-id 不影响 code 路径」,
但没人测「CLI 会不会因此误报」**。

REST 侧的 profile 隔离有测试:`tests/hermes_cli/test_dashboard_admin_endpoints.py:276 @ 863e313`

```python
    def test_pairing_is_isolated_per_profile(self):
```

而该测试的注释本身记录了 D8 的成因(模块级 `PAIRING_DIR` 在 import 时绑定):
`tests/hermes_cli/test_dashboard_admin_endpoints.py:308-310 @ 863e313`

```python
        # is still waiting. (Asserted against this user rather than an empty
        # list: the module-level PAIRING_DIR is bound at import, so the global
        # store carries whatever earlier cases in this class approved.)
```

---

## 9. 重实现要点(从零重写这套「批准入口」必须知道的)

1. **把「是 request-id 还是 code」做成显式参数,不要靠形状猜。**
   本仓库靠 `len==16 && all-hex` 判别(`gateway/pairing.py:733`),形状一旦判错就掉进
   「计入暴力破解失败次数」的另一条路(D3)。REST 侧已经用「字段名优先」修好了一半,
   CLI 因为只有一个位置参数修不了。设计时给 CLI 加 `--request-id` / `--code` 两个互斥 flag,
   或干脆只让 CLI 接受 request-id(code 只给用户看)。

2. **两类失败必须在返回值里区分,不能让调用方去猜。**
   `approve_code` 对「码错」和「平台锁定」都返回 `None`(`gateway/pairing.py:669-672` docstring 自陈),
   于是两个调用方各自去读私有的 `_is_locked_out`,并各自写了不同的判断逻辑——
   这就是 CLI/REST 语义分叉的直接原因。**返回结构化失败原因**
   (`{"ok": False, "reason": "locked_out", "retry_after_s": N}`)能一次性消灭 D1+D2+D9。

3. **request-id 路径与 code 路径的安全预算不一样,要写进类型里。**
   本仓库的判断是对的:code 是**跨消息信道**的 8 位秘密,需要锁定 + 计数;
   request-id 只在**已认证 admin 面**出现,失败只意味着「你点的那行过期了」
   (`gateway/pairing.py:745-751`)。重写时把这两条做成两个**不同的方法/不同的权限**,
   而不是一个方法两种入参——共用入口是所有下游不一致的源头。

4. **多入口必须共享同一个「批准用例」,UI 只做渲染。**
   本仓库有三个入口(CLI / REST / console),各自实现了分发 + 报错,于是有了 D2 与 D8。
   正确形状:一个 `approve(platform, target, kind) -> ApprovalResult`,
   CLI 渲染成文本 + 退出码,REST 渲染成 HTTP status,console 复用 CLI 渲染。

5. **进程作用域(profile / home)不能靠模块级常量。**
   `PAIRING_DIR = get_hermes_dir(...)` 在 import 时求值(`gateway/pairing.py:59`),
   短命 CLI 进程碰巧正确(env 先于 lazy import 设好),长驻 dashboard 进程就错(D8)。
   **凡是「每请求可能不同」的路径,必须在调用时解析**;想要缓存就把 home 作为 key 缓存。

6. **授权撤销必须是事务性的,或者至少要把部分失败上报。**
   pairing store 与 allowlist env 是 union 授权(`gateway/authz_mixin.py:582-587`),
   删一半等于没删。本仓库把镜像写入包在 `except Exception: pass` 里
   (`gateway/pairing.py:325-326`),而 managed 模式下写入函数根本不抛异常——
   于是 revoke 报成功、用户仍能进(D5)。**要么两处都成功才返回 True,要么返回
   「主记录已删 / 镜像未同步」的部分成功。**

7. **跨进程共享 JSON 存储要有文件锁。**
   `threading.RLock` 只保护实例内(`gateway/pairing.py:450`),而 CLI / gateway / dashboard
   是三个进程写同一批文件。原子替换只防「读到半截」,不防「丢更新」(D7)。
   重写时用 SQLite(自带 WAL + 锁)或 `fcntl.flock`,别用「JSON + tmp rename」当并发存储。

8. **CLI 必须有退出码。** 批准/撤销是运维动作,一定会被写进脚本。
   本仓库全部失败路径 exit 0(D4),脚本只能 grep 中文 stdout。
   最小成本修法:`pairing_command` 返回 int,`cmd_pairing` 加 `return`。
