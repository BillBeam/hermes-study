# data/inflight — 在途产出声明(R11B 立)

一个后台生产者(子代理 / 后台命令)被派发时,在这里放一个 `<slug>.claim`,
声明它**将要写哪些路径**。`scripts/verify_commit_safety.py` 在 `pre-commit` 钩子里读它:
**只要 `signal:` 还是 `OPEN`,被声明的路径就提交不进去。**

CLAUDE.md 早就有这条规矩(「异步产出的完成判定,只以完成信号为准,不以产物形态推断」),
但它此前只是一条**要靠人记住**的规矩,于是 R9B / R10B / R11A **连续三轮**在同一个形状上翻车:
一次 `git add` 匹配得比想的宽,把子代理正在写的文件扫进了提交,三次都靠人眼发现。

## 格式

```
agent: 片 A · 定案账普查
dispatched: 2026-08-10T05:12:00Z
signal: OPEN
path: notes/r11b-raw-rulings-census.md
path: data/r11b/probes/rulings-*.py
```

- `path:` 是 fnmatch 通配符,匹配**仓库相对路径**;一条 claim 可以有多条。
- `signal:` 是整个机制的开关。收到完成信号后改成
  `signal: RELEASED <完成信号是什么>`,那些路径才可提交。
  **要动这一行,就得把「信号到底到了没有」写下来**,而不是看文件写完了没有。
- claim 文件自己永远可提交——它是账。

## 这个机制拦不住什么(如实说)

1. **声明不全就拦不住**:agent 写了没声明的路径,只会命中那条**不阻断**的
   「新鲜但无人认领」提示。所以 `path:` 宁可写宽(用目录通配符)。
2. **`git commit --no-verify` 能绕过**。绕过是有意留的口子(钩子不是权限系统),
   代价是绕过这件事得**显式打出来**,而原来的失败形态是完全无声的。
3. **钩子不在版本控制里**。所以 `scripts/verify_ledger.py`(CLAUDE.md 要求每个会话
   开工第一件事)会调 `scripts/install_hooks.py` 把它装上;单独装用
   `python3 scripts/install_hooks.py`。

负控在 `data/r11b/probes/commit_guard_negative_control.sh`:它在一个临时克隆里
证明「信号未到时提交确实被拦住」,以及放行后同一条提交能过。
