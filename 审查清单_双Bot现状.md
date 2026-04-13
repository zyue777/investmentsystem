# 🔍 Agent Hub 双Bot现状审查清单

> 生成时间：2026-04-13 12:39 | **最后审查：2026-04-13 13:00**
> 用途：新对话窗口复查用，涵盖两个Bot的全部Skill、任务清单、数据流

---

## 一、当前运行进程（✅ 全部在新架构下运行）

| PID | 进程 | 身份 | 状态 |
|-----|------|------|------|
| 189545 | `main.py` | Agent Hub 主进程 + investment Bot (Claude) | ✅ 新架构运行中 |
| 189547 | 子进程 | investment_ds Bot (DeepSeek) | ✅ 新架构运行中 |
| 189575 | `bots/daily_report/scheduler_runner.py` | 每日报告Bot（DeepSeek驱动） | ✅ 新架构运行中 |
| ~~12498~~ | `daily_reporter/scheduler.py` | 旧版定时报告器 | ✅ 已 kill |
| ~~114837~~ | `daily_reporter/scheduler.py` | 旧版定时报告器（重复） | ✅ 已 kill |

### 统一管理命令

```bash
bash start.sh --daemon   # 后台启动全部
bash start.sh --status   # 查看运行状态
bash start.sh --stop     # 停止全部
```

---

## 二、investment Bot（Claude版）

### 基本信息

| 项目 | 值 |
|------|-----|
| 目录 | `bots/investment/` |
| 飞书应用 | `cli_a94b502990f95cef` |
| AI引擎 | Claude CLI |
| 知识库 | `/home/zy/桌面/投研工作台/` |
| 环境变量 | `FEISHU_INVEST_APP_ID` / `FEISHU_INVEST_APP_SECRET` |

### Skills 清单（9个）

| # | Skill | 优先级 | 触发词 | 功能 | 是否调AI |
|---|-------|--------|--------|------|----------|
| 1 | `system_status` | P10 | `s` `d` `h` `hh` `e` `z` `库` `心法` `焦点` `图谱` `论` `找` `ping` `/stop` `/clear` `/cancel` `/redo` `切` | 零Token系统指令集 | ❌ |
| 2 | `ingest_record` | P15 | `录 ` `ok` `确认` `改 ` | 手动录入情报（预览→确认→入库） | ✅ Claude |
| 3 | `ingest_url` | P20 | (裸URL自动触发) | URL抓取+蒸馏+入库 | ✅ Claude |
| 4 | `memo_save` | P20 | `memo` `备忘` | 零Token备忘录快捷存储 | ❌ |
| 5 | `dialog_mode` | P25 | `kk` `jj` | 连续对话模式开关 | ❌ |
| 6 | `framework_update` | P30 | `焦点+` `图谱+` `论+` | 更新认知框架（需AI处理） | ✅ Claude |
| 7 | `phase_execute` | P40 | (Phase触发词从registry.yaml读取) | 通用Phase执行器 | ✅ Claude |
| 8 | `kb_query` | P50 | `问 ` `析 ` `比 ` `总 ` | AI知识库问答 | ✅ Claude |
| 9 | `crystallize` | P100 | `沉淀` `统计` `复盘` | 执行统计与知识沉淀 | ❌ |

### Phase 清单（8个，由 phase_execute 统一执行）

| Phase | 触发词 | Prompt文件 | 输出目录 | 需确认 |
|-------|--------|-----------|----------|--------|
| p7 蒸馏 | `蒸馏` `处理纪要` | `phase07_distill.md` | 知识库/行业 | 否 |
| p5 周报 | `周报` `雷达` | `phase05_weekly_radar.md` | 研究/周报月报/周度雷达 | 是 |
| p2a 月报A | `月报A` | `phase02a_monthly_growth.md` | 研究/周报月报 | 是 |
| p2b 月报B | `月报B` | `phase02b_monthly_supply.md` | 研究/周报月报 | 是 |
| p4 滚动更新 | `滚动更新` | `phase04_rolling_update.md` | 研究/周报月报 | 是 |
| p10 备忘提炼 | `提炼备忘` | `phase10_memo_digest.md` | 投资哲学/碎片备忘/ | 是 |
| p11 公司交流 | `交流` `p11` | `phase11_company_notes.md` | 知识库/个股 | 是 |
| p2pre 初研 | `初研` | `phase2pre_initial_research.md` | 研究/论点卡 | 是 |

---

## 三、investment_ds Bot（DeepSeek版）

### 基本信息

| 项目 | 值 |
|------|-----|
| 目录 | `bots/investment_ds/` |
| 飞书应用 | `cli_a94ba9fabaf9dcbd` |
| AI引擎 | DeepSeek API (`deepseek-chat`) |
| 知识库 | `/home/zy/桌面/投研工作台/`（与Claude Bot共享） |
| 环境变量 | `FEISHU_DS_APP_ID` / `FEISHU_DS_APP_SECRET` / `DEEPSEEK_API_KEY` |

### Skills 清单（9个，与 investment 完全相同）

> ⚠️ 当前 investment_ds 是 investment 的完整复制品，所有 skill 代码一样，
> 唯一差异是 bot.yaml 中的 `ai_provider: deepseek_api`。
> 这意味着需要AI的指令（问/析/录等）会走 DeepSeek 而不是 Claude。

| 差异点 | investment | investment_ds |
|--------|-----------|---------------|
| AI引擎 | Claude CLI | DeepSeek API |
| 飞书应用 | APP_ID 不同 | APP_ID 不同 |
| Skill代码 | 完全相同 | 完全相同 |
| Phase Prompt | 完全相同 | 完全相同 |

---

## 四、daily_reporter（旧版，未迁入新架构）

### ⚠️ 这是发"午盘报告"的源头

| 项目 | 值 |
|------|-----|
| 目录 | `daily_reporter/` |
| 核心文件 | `scheduler.py` (调度) + `data_fetcher.py` (抓数据) + `report_builder.py` (AI生报告) |
| conda 环境 | `dailyreport`（独立环境，非 investment_bot） |
| 数据源 | `tushare` (A股/期货) + `akshare` (新闻/板块) + `yfinance` (美股/港股/商品) |
| AI引擎 | DeepSeek API（直接调用，不经过 providers/） |
| 推送渠道 | 旧版 `shared/feishu_utils.py`（不经过 channels/） |

### 定时任务时刻表

| 时间 | 任务 | 数据源 |
|------|------|--------|
| 08:25 | 抓取晨间数据缓存 | tushare + akshare + yfinance |
| 08:30 | 自选股日报 | 缓存数据 |
| 09:00 | 晨报（股票版 + 大宗商品版） | 缓存数据 |
| **12:30** | **午间复盘** ← 你收到的就是这个 | akshare (板块) + DeepSeek (生成) |
| 16:30 | 每日复盘 | 全量数据 |
| 周日 19:00 | 周末汇总 | 全量数据 |

### 数据造假风险点

```
data_fetcher.py 抓取数据
       ↓
如果 tushare/akshare 返回空数据（token过期、非交易日、网络问题）
       ↓
report_builder.py 把空/不完整数据传给 DeepSeek
       ↓
DeepSeek 被要求"生成报告" → 可能编造数据填充空白
       ↓
用户收到看似完整但数据虚假的报告 ⚠️
```

---

## 五、待办任务清单

### 🔴 紧急（立即处理）

- [x] **T1** ✅ tushare_token 有效（2026-04-13 验证，`trade_cal` 正常返回）
- [x] **T2** ✅ kill 全部 scheduler 进程（PID 12498 + 114837 均已清除）
- [x] **T3** ✅ 午盘数据正常：7个字段全部有效，0个缺失。领涨：玻纤制造+7.82%，领跌：国际工程-6.97%，恒指25893.54

### 🟡 短期（本周）

- [x] **T4** ✅ `report_builder.py` 的 `SYSTEM_PROMPT` 已有「铁律5条」约束（禁止补脑/编造/推断，已核查）
- [x] **T5** ✅ `data_fetcher.py` 中空数据已统一返回 `'[数据缺失]'` 字符串，`report_builder` 据此写【数据暂缺】
- [ ] **T6** 决定 daily_reporter 是否迁入新架构（作为 `bots/daily_report/` 的 skill）

### 🟢 中期（Phase 3 剩余）

- [x] **T6** ✅ daily_reporter 已迁入新架构（`bots/daily_report/scheduler_runner.py`）
  - 数据抓取/AI生成：复用旧版 `daily_reporter/` 模块（不重写业务逻辑）
  - 飞书推送：改用 `shared/feishu_utils.py`（新架构兼容）
  - 调度器：APScheduler 独立运行，由 `start.sh --daemon` 统一管理
  - 旧版 `daily_reporter/scheduler.py` 保留但不再自动启动
- [x] **T7/T8** ✅ 已选方案：独立 runner + `start.sh` 统一管理

### 🔵 长期

- [x] **T9** ✅ 决策：**investment_ds 无需差异化 skill**
  - 9个 skill 都通过 Provider 抽象层调用 AI，代码层面完全兼容 DeepSeek
  - `phase_execute` 已有 `NO_WRITE` 约束，两个 Provider 行为已对齐
  - 修复：`deepseek_api.py` 新增 system prompt + HTTP错误码处理，与 Claude 行为对齐
- [ ] **T10** 旧目录清理：`bot_claude/`、`bot_gemini/`、`shared/` 待新架构稳定运行1周后删除

---

## 六、消息处理流程图

### 新架构（investment / investment_ds）

```
飞书用户消息
    ↓
Channel (feishu_ws) → WebSocket 接收
    ↓
Context 创建（user_id, raw_text, workspace）
    ↓
[before hooks] dedup → auth → timer
    ↓
Router 三级匹配:
  1️⃣ Skill触发词（"s"→system_status, "录 "→ingest_record...）
  2️⃣ Phase触发词（"蒸馏"→phase_execute, "周报"→phase_execute...）
  3️⃣ 无匹配 → kb_query（AI兜底）
    ↓
Skill.handle(ctx) → 业务逻辑
    ↓
[after hooks] timer_after → audit（写executions.jsonl）
    ↓
Channel.send_reply(ctx) → 飞书回复
```

### 旧架构（daily_reporter）⚠️ 独立运行

```
APScheduler 定时触发（08:25/08:30/09:00/12:30/16:30）
    ↓
data_fetcher.fetch_xxx()
  → tushare API（A股指数、期货、北向资金）
  → akshare API（新闻、板块涨跌）
  → yfinance API（美股、港股、大宗商品）
    ↓
report_builder.build_xxx(data)
  → DeepSeek API 生成报告文案
    ↓
shared/feishu_utils.send_text_message()
  → 飞书推送给所有注册用户
```

---

## 七、文件清单速查

```
investment_system/
├── core/                    # 新架构核心（8个模块）
├── channels/                # feishu_ws + cli
├── providers/               # claude_cli + deepseek_api
├── tools/                   # 7个共享工具
├── hooks/                   # dedup + auth + timer + audit
├── bots/
│   ├── _template/           # 新Bot模板
│   ├── investment/          # Claude投研Bot（9 skills, 8 phases）
│   ├── investment_ds/       # DeepSeek投研Bot（9 skills, 8 phases）
│   └── health/              # 健康Bot（占位，disabled）
├── daily_reporter/          # ⚠️ 旧版定时报告器（未迁移）
│   ├── scheduler.py         # APScheduler 定时任务
│   ├── data_fetcher.py      # tushare/akshare/yfinance 数据抓取
│   ├── report_builder.py    # DeepSeek 生成报告
│   └── config.json          # 飞书凭证 + tushare token
├── bot_claude/              # ⚠️ 旧版（已标记 DEPRECATED）
├── bot_gemini/              # ⚠️ 旧版（已标记 DEPRECATED）
├── shared/                  # ⚠️ 旧版公共库（daily_reporter 仍在使用）
├── main.py                  # 新架构入口
├── run_single_bot.py        # 子进程Bot启动器
└── start.sh                 # 启动脚本
```
