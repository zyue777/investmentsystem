# investment_system — Agent 开发规范

> ⚠️ **此文件是 Claude Code / 其他 agent 读取项目的第一入口，必须保持与实际代码同步。**

---

## Git 规范

不要执行任何 git 命令，包括 commit、push、add、status。用户手动管理 git。

---

## 项目结构（当前架构：Agent Hub）

```
investment_system/
├── core/           # 框架核心（路由/执行/注册/中间件）——轻易不动
│                   # ⛔ 高风险文件（修改前必须说明理由）：
│                   #    context.py — 所有层的数据契约，改字段会级联崩溃
│                   #    executor.py — 所有 Bot 的执行链，改错影响全局
│                   #    feishu_ws.py (channels/) — 所有消息入口，改错全部失联
├── channels/       # 渠道适配器（目前只有 feishu_ws）
├── providers/      # AI 引擎适配器（claude_cli / deepseek_api）
├── hooks/          # 全局横切钩子（dedup / auth / timer / audit）
├── tools/          # 无状态共享工具（飞书API / 文件IO / 搜索 / 联网搜索 / 会话记忆）
├── bots/           # 各 Bot 业务代码
│   ├── _shared/           # ⭐ 共享 Skills（所有 Bot 共用，只维护一份）
│   │   └── skills/        #    12 个 Skill 文件（含 research_session）
│   ├── investment/        # Claude 投研 Bot（主进程）
│   │   ├── bot.yaml       #    配置（ai_provider / channel / workspace）
│   │   ├── skills/        #    空目录（如需覆盖共享 Skill，放同名文件到此处）
│   │   └── prompts/       #    Phase prompt 文件 + registry.yaml
│   ├── investment_ds/     # DeepSeek 投研 Bot（子进程）
│   │   ├── bot.yaml
│   │   ├── skills/        #    空目录
│   │   └── prompts/
│   ├── daily_report/      # 每日报告 Bot（独立调度器，不走 BotLoader）
│   └── health/            # 健康 Bot（占位）
├── docs/           # 架构文档（优先阅读 00_架构总览.md）
├── main.py         # 系统入口
└── start.sh        # 统一后台启动脚本
```

> **已废弃目录**（保留历史，不要修改）：`bot_claude/`  `bot_gemini/`  `archive/`

---

## ⭐ Skills 共享机制

`bots/_shared/skills/` 是所有 Bot **共用**的 Skill 目录（只维护一份）。

加载顺序：`_shared/skills/` 先加载 → Bot 专属 `skills/` 后加载（同名覆盖）

- **修改共享 Skill**：直接改 `bots/_shared/skills/<file>.py`，所有 Bot 生效
- **某个 Bot 需要特殊行为**：在该 Bot 的 `skills/` 下放同名文件，自动覆盖共享版本
- **新增 Skill**：放入 `_shared/skills/`，重启即生效

---

## 运行环境

- conda 环境：`investment_bot`
- Python 解释器：`/home/zy/miniconda3/envs/investment_bot/bin/python3`
- 启动：`bash ~/investment_system/start.sh`
- 日志：`tail -f logs/investment.log` / `logs/investment_ds.log`

---

## 知识库路径

两个 Bot 共用外部知识库：`~/桌面/投研工作台/`

- 写入路径：`知识库/行业/` 或 `知识库/个股/`（由 AI 输出的 `FILE_PATH:` 行决定）
- 临时文件：仅允许写入 `_Inbox/`

---

## 两个投研 Bot 的核心分工

| Bot | 目录 | AI Provider | 职责 |
|-----|------|-------------|------|
| investment | `bots/investment/` | claude_cli | Phase 调度、知识库写入、URL/文件/手动录入、问答 |
| investment_ds | `bots/investment_ds/` | deepseek_api | 同上（DeepSeek 驱动，独立飞书应用） |

两个 Bot 共用 `_shared/skills/`，功能完全一致，仅 AI 引擎不同。

---

## 消息路由速查（定位路由 Bug 必读）

```
Router 五层优先级（core/router.py）：

第0层  pending-confirm：用户说 ok/确认/改.../cancel
       → 检查 pending_store 是否有该用户的待确认记录
       → 有则直接路由回发起 skill（ingest_record 和 phase_execute 均使用此流程）

第0.5层  Session 模式拦截：检查 session_memory 是否有活跃 Session
       → 有则路由到 session 的 target_skill（如 research_session）
       → 归档/clear/jj 等退出指令也路由到同一 skill，由它内部处理
       → 可拔插：session_memory 不存在时自动降级跳过

第1层  Skill 触发词：精确前缀匹配 MANIFEST.triggers
       例：「录 xxx」→ ingest_record
           「研究 xxx」→ research_session
           「请联网回答 xxx」→ kb_query

第2层  Phase 触发词：registry.yaml 里配置的触发词
       例：「蒸馏 xxx」→ phase_execute (p7)
           「跑周报」→ phase_execute (p5)
           「初研 xxx」→ phase_execute (p2pre)

第3层  AI fallback：消耗 token，让 AI 判断意图

兜底   kb_query（通用问答）
```

**特殊路由（不走 Router）：**
- 文件消息（PDF/Word）→ Channel 层直接注入 `matched_skill=ingest_file`
- URL（裸链接）→ Router URL 检测，路由到 `ingest_url`

---

## Skill 流程类型说明

| Skill | 流程 | 说明 |
|-------|------|------|
| `ingest_file` | 单步直接入库 | 文件下载→提取→AI蒸馏→写入 |
| `ingest_url` | 单步直接入库 | URL抓取→蒸馏→写入 |
| `ingest_record` | 两步确认流程 | 生成预览→用户回复 ok→写入 |
| `kb_query` | 单步问答 | 支持联网搜索+知识库搜索+反幻觉 |
| `research_session` | 多轮会话+归档 | 研究→多轮联网/KB对话→归档为情报卡 |
| `phase_execute` | 单步或两步 | 由 registry.yaml 的 `needs_confirm` 字段控制 |

---

## Phase 注册表速查

> 两个 Bot 各自维护独立的 `prompts/registry.yaml`。DS Bot 已对齐新投研体系。

**investment_ds（DeepSeek版）当前 Phase 列表：**

| Phase | 触发词 | 需确认 | 输出路径 |
|-------|--------|--------|----------|
| p7 蒸馏 | `蒸馏` `处理纪要` | ❌ 直接写入 | 知识库/行业 |
| p11 公司交流 | `交流` `p11` | ✅ | 知识库/个股 |
| p5 周报 | `周报` `雷达` `跑周报` | ✅ | 研究/周报月报/周度雷达 |
| p4 滚动更新 | `滚动更新` `差异化更新` | ✅ | 研究/周报月报 |
| p10 备忘提炼 | `提炼备忘` `消化memo` | ✅ | 投资哲学/碎片备忘/_Weekly_Digest |
| p2pre 初研 | `初研` | ✅ | 研究/论点卡 |
| p2maintain 底稿维护 | `更新底稿` `检查底稿` | ✅ | 研究/论点卡 |
| p8 精选个股 | `挑标的` `精选个股` | ✅ | 研究/自选股 |

> ⚠️ **investment（Claude版）** 仍保留旧的 p2a/p2b，未对齐新体系。日常使用以 DS Bot 为主。

---

## research_session 研究模式用法

| 用户输入 | 行为 |
|---------|------|
| `研究 xxx` | 开启研究模式，创建 Session |
| 研究模式中：`请联网 xxx` | 联网搜索 + 历史上下文 → AI 回答 |
| 研究模式中：`结合知识库 xxx` | 知识库检索 + 历史上下文 → AI 回答 |
| 研究模式中：其他文字 | 仅历史上下文 → AI 纯推理 |
| `归档` | AI 整理为情报卡 → 写入知识库 → 清空 Session |
| `clear` / `jj` | 清空 Session，不保存 |

存储：`tools/session_memory.py`（JSON 文件持久化，24h 自动过期）

---

## kb_query 联网搜索用法

| 用户输入 | 行为 |
|---------|------|
| `请联网回答 xxx` | 仅联网搜索后回答 |
| `请结合联网与知识库信息回答 xxx` | 联网 + 知识库搜索后回答 |
| `问 xxx` / `析 xxx` / `比 A B` / `总 xxx` | 仅知识库问答 |
| 其他文字（兜底） | 纯 AI 回答 |

联网信息会在回答末尾标注 `📡 以上部分信息来源于联网搜索`。

---

## docs/ 目录说明（共 4 个文件，从 10 个精简合并而来）

| 文件 | 内容 |
|------|------|
| `docs/00_架构总览.md` | 系统架构、数据流、已知问题 |
| `docs/01_开发手册.md` | Skill/Hook/Channel/Provider/Tool 开发规范 |
| `docs/02_运维与债务.md` | 启动运维、定时任务、技术债务 |
| `docs/03_架构知识卡.md` | 可复用的架构设计原则与实战经验 |

---

## 文档更新触发器（Agent 必须遵守）

| 你修改了什么 | 必须同步更新 |
|-------------|-------------|
| `core/*.py` | CLAUDE.md + docs/00_架构总览.md |
| 新增/修改 Skill | CLAUDE.md（Skill 流程类型表）|
| `core/router.py` | CLAUDE.md（消息路由速查）|
| 新增 `tools/*.py` | CLAUDE.md（项目结构）|
| 修改目录结构 | CLAUDE.md + docs/00 |
| 修改定时任务 | docs/02_运维与债务.md |
| 新增技术债务 | docs/02_运维与债务.md |
| 修改 Phase prompt 或 registry.yaml | 评估是否需同步到另一个 Bot 的 prompts/ |

> 如果不确定是否需要更新文档，默认更新 CLAUDE.md。

---

## 用户偏好（精简版）

### 设计偏好
- 宁可多建文件也不写上帝函数
- 新增功能 = 新增文件，不改旧代码
- 能在代码层控制的事不在 Prompt 层控制
- 能单步完成的流程不用两步
- **Shared Skill 访问 Bot 级资源（prompt/config）必须通过 `runtime.bot_dir`，禁止 `Path(__file__)` 硬编码**
- **AI 输出进入文件系统前，必须经过 `_sanitize_path()` 净化（AI 是不可信输入源）**
- **Prompt 中的文件系统操作指令，必须区分 CLI 模式和管道模式**

### 行为偏好
- **不要执行任何 git 命令**
- 不要编造数据，不知道就说不知道
- 做完后简洁总结，不重复描述已做的事
- 做完大改动后主动更新 CLAUDE.md
- 联网获取的信息必须标注来源

### 技术偏好
- Python，conda 环境 `investment_bot`
- 配置 YAML，不用 JSON
- AI 调用用 `call_with_retry` 内置重试
- 搜索优先本地 grep，联网用 DuckDuckGo

