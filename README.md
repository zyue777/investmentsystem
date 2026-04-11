# investment_system — 飞书投研机器人系统

## 系统概览

```
investment_system/
├── bot_claude/          # ClaudeBot — 知识库主力（Phase 调度 / 录入确认 / URL 全自动入库）
├── bot_gemini/          # DeepSeekBot — 快速问答（蒸馏 / 报告生成）
├── daily_reporter/      # 定时财经报告（apscheduler + 多数据源）
├── sentiment_monitor/   # 自选股日记（港/美/中概）
├── shared/              # 公共工具（feishu_utils / memo_handler）
├── logs/                # 运行日志与 PID（自动生成）
└── start.sh             # 一键后台启动
```

知识库路径（两个 bot 共用）：
```
~/桌面/投研工作台/
```

---

## 快速启动

```bash
# 激活 conda 环境
conda activate investment_bot

# 后台启动三个服务
bash ~/investment_system/start.sh

# 查看日志
tail -f logs/bot_claude.log
tail -f logs/bot_gemini.log

# 停止服务
kill $(cat logs/bot_claude.pid) $(cat logs/bot_gemini.pid) $(cat logs/daily_reporter.pid)
```

> `daily_reporter` 使用独立的 `dailyreport` conda 环境（含 tushare / yfinance / akshare）。

---

## 两个 Bot 的分工

| 功能 | ClaudeBot | DeepSeekBot |
|------|-----------|-------------|
| 接入方式 | 飞书 WebSocket 长连接 | 飞书 WebSocket 长连接 |
| 底层模型 | Claude CLI (`claude --print`) | DeepSeek API (`deepseek-chat`) |
| URL 投喂→情报卡 | ✅ 全自动（wechat_parser → Phase 7 → 直接落盘） | ✅ 抓取→蒸馏→确认写入 |
| Phase 调度（p7/p5/p2a…） | ✅ 完整 Phase 管道 | ❌ 无 |
| 录入确认流程 | ✅（录 → 预览 → ok → 写入） | ✅（录入: → 确认 → 写入） |
| 定时财经报告 | ❌ 无 | ✅ 晨报 / 商品报 / 自选股 / 复盘 |
| 知识库搜索 | ✅ 本地 grep（零 Token） | ✅ DeepSeek 推理 |
| git 提交 | ❌ 无（用户手动 git） | ❌ 无（用户手动 git） |

---

## 文件写入规则（重要）

所有知识库正式内容写入 `知识库/行业/` 下：
- ClaudeBot 使用 `Path(kb) / '知识库' / '行业' / path`
- DeepSeekBot URL feed 自动补全 `知识库/行业/` 前缀

临时/预览文件只允许写入 `_Inbox/`，**禁止在知识库根目录创建 `inbox/`、`draft/` 等临时目录**（见知识库 CLAUDE.md）。

---

## 配置说明

三个模块各有 `config.json`，**不入 git**（`.gitignore` 已屏蔽）。  
首次部署参照各目录的 `config.json.example` 创建：

```bash
cp bot_claude/config.json.example   bot_claude/config.json
cp bot_gemini/config.json.example   bot_gemini/config.json
cp daily_reporter/config.json.example daily_reporter/config.json
# 然后填入真实的 app_id / app_secret / api_key
```

---

## 知识库目录结构

两个 bot 共用同一个外部知识库，**以下目录必须存在**：

```text
~/桌面/投研工作台/
├── 行业筛查/
│   └── prompts/          # Phase00/01/01.5/03/06/06X prompt 文件
├── 研究/
│   ├── prompts/          # Phase02A/02B/2Pre/2Maintain/04/05/07/08/09/10 prompt 文件
│   ├── 论点卡/           # 行业研究底稿（静态逻辑框架）
│   └── 周报月报/         # Phase 报告输出
├── 知识库/
│   └── 行业/             # 情报卡（平铺，YAML frontmatter含industry字段）
├── 投资哲学/              # 心法 / 当下关注焦点
├── 行业状态面板.md        # 动态现状面板（图谱）
├── _Inbox/               # 临时文件（URL原文 / 长回复溢出 / 初研预览）
├── 动线/README.md        # 人读速查表（触发词→Phase→文件）
└── CLAUDE.md             # Claude Code 路由索引（极简，~20行）
```

> **临时文件约定**：任何临时/预览文件只能写入 `_Inbox/`，**禁止**在知识库根目录创建 `inbox/`、`draft/` 等目录。

---

## 详细文档

- [ClaudeBot 工作流](bot_claude/README.md)
- [DeepSeekBot 工作流](bot_gemini/README.md)
- [工作流检查清单](WORKFLOW_CHECKLIST.md)
