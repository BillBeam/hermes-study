<!-- 本文件由 scripts/build_reading_layer.py 生成,请勿直接编辑。
     真源是 chapters/;改源章后运行 --restamp 再 --write。 -->

# 问题索引 · 从「我遇到了什么问题」进书

> **这份文档是什么**:一份**倒排索引**——入口是**问题**,不是模块名。
> 你在造自己的 harness 时撞见一个具体麻烦(模型返回空了、工具输出把上下文撑爆了、定时任务重启后跑了两遍……),
> 从这里查它,直接落到某一章的某一节。
>
> **为什么入口必须是问题**:按模块名建的索引只有「已经知道答案在哪」的人用得上;
> 而工作中真正的入口是**症状**。这一层的用途是随时检索,所以它按症状组织。
>
> 每条指向 `章 § 小节`,链接可点击可定位。链接与小节标题由 `scripts/build_reading_layer.py` 在构建时从 `chapters/` 解析,不手写。

**规模**:1 个问题入口 · 1 个问题域 · 指向 1 章 / 1 个小节。

## 问题域目录

- [模型这一层出问题](#模型这一层出问题) —— 1 条

---

## 模型这一层出问题

### 模型返回了空响应,循环该怎么办?

- [第 2 章 · 回合主循环与模型接入 § 4. 可迁移的设计原则(造你自己的 harness 时怎么做)](../chapters/r2-turn-loop-and-model-access.md#4-可迁移的设计原则造你自己的-harness-时怎么做) —— 占位

---

## 未被任何问题指向的章

以下章没有出现在上面任何一条问题里。列出来而不是掩盖,因为「查不到」和「没有」对读者是两回事:

- **第 1 章 · hermes-agent 是什么:全仓地图与阅读顺序**([`chapters/r1-what-is-hermes-agent.md`](../chapters/r1-what-is-hermes-agent.md))
- **第 3 章 · 工具系统:让 LLM 安全地对真实世界动手**([`chapters/r3-tool-infrastructure.md`](../chapters/r3-tool-infrastructure.md))
- **第 4 章 · 执行环境:一条命令到底在哪、怎么跑起来**([`chapters/r4-execution-environments.md`](../chapters/r4-execution-environments.md))
- **第 5 章 · 会话状态与持久化**([`chapters/r5-session-state-and-persistence.md`](../chapters/r5-session-state-and-persistence.md))
- **第 6 章 · 记忆 provider 生态**([`chapters/r6-memory-provider-ecosystem.md`](../chapters/r6-memory-provider-ecosystem.md))
- **第 7 章 · 网关会话核心与多路复用**([`chapters/r7-gateway-session-core.md`](../chapters/r7-gateway-session-core.md))
- **第 8 章 · 平台接入面**([`chapters/r7b-platform-integration.md`](../chapters/r7b-platform-integration.md))
- **第 9 章 · 网关外围面与定时调度**([`chapters/r7c-gateway-periphery-and-scheduling.md`](../chapters/r7c-gateway-periphery-and-scheduling.md))
- **第 10 章 · 配置面:一个键从哪里来,到哪里去**([`chapters/r8a-configuration-surface.md`](../chapters/r8a-configuration-surface.md))
- **第 11 章 · CLI 主干与交互**([`chapters/r8b-cli-trunk-and-interaction.md`](../chapters/r8b-cli-trunk-and-interaction.md))
- **第 12 章 · dashboard 与 web 面**([`chapters/r8c-dashboard-and-web.md`](../chapters/r8c-dashboard-and-web.md))
- **第 13 章 · 自持面**([`chapters/r8d-self-custody.md`](../chapters/r8d-self-custody.md))
- **第 14 章 · 能力的组织、扩展与委派**([`chapters/r9a-capability-organization.md`](../chapters/r9a-capability-organization.md))
- **第 15 章 · 多模态交付面**([`chapters/r9b-multimodal-delivery.md`](../chapters/r9b-multimodal-delivery.md))
- **第 16 章 · 对外接驳面**([`chapters/r9c-external-interfaces.md`](../chapters/r9c-external-interfaces.md))
- **第 17 章 · 工具面:守卫装在哪一层**([`chapters/r9d-tool-surface-and-guard-placement.md`](../chapters/r9d-tool-surface-and-guard-placement.md))
- **第 18 章 · 客户端接驳面**([`chapters/r10-client-interface-layer.md`](../chapters/r10-client-interface-layer.md))
- **第 19 章 · 桌面应用**([`chapters/r10b-desktop-application.md`](../chapters/r10b-desktop-application.md))
- **第 20 章 · 交付面:从源码到一台跑着的机器**([`chapters/r11a-ops-and-delivery.md`](../chapters/r11a-ops-and-delivery.md))
- **第 21 章 · 没人写的那一层:harness 边角上的欠账**([`chapters/r11b-the-unwritten-layer.md`](../chapters/r11b-the-unwritten-layer.md))
