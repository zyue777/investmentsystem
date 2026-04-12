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

## 两个 Bot 是如何工作和分工的？（通俗版）

整个系统里有两个 Bot 在飞书上为你服务，它们的分工和运行机制非常明确：

### 1. ClaudeBot（深度大脑 / 主力知识库管家）
* **如何传导工作的？** 
  它是一个你**本地电脑**上的程序。当你在飞书给它发消息时，它接收到指令后，会调动你电脑里的 Claude (CLI) 开始思考。思考完成后，它会**直接在你的本地文件夹**（`~/桌面/投研工作台/`）里创建或修改 Markdown 文件。
* **日常工作内容是什么？** 
  - **全自动提取归档**：你只要往里面丢微信文章等网络链接，它会自动抓取网页、套用最好的深度提示词（Phase 7），把口水文压缩成干货情报卡，然后自动存入本地知识库。
  - **驱动深度投研框架**：支持你运行各种核心的投研指令（如 `p5` 行业高频雷达、 `p2a/p2b` 月报等），它是整个投研工作台的“核心管家”。

### 2. DeepSeekBot（快问快答助手 / 定时数据播报员）
* **如何传导工作的？**
  它同样是一个本地程序，但它**不使用**本地引擎，而是**通过网络去呼叫云端的 DeepSeek 网页接口**。因为它直接调云端 API，没有复杂的本地渲染，所以它的反应速度极快，适合轻量级任务。
* **日常工作内容是什么？** 
  - **快速问答和简单处理**：平时有些碎片问题、随便复制一段文字需要立马总结的，可以直接丢给它，回答很快。
  - **定时推送报告**：系统里自带每日全自动跑的数据脚本（`daily_reporter`），每天会在股市盘前盘后自动抓数据，再借用这个 Bot 以早晨简报、商品异动报、自选股复盘等形式弹送到你的飞书里。

> **💡 极简总结点拨：**
> - 做长篇深度研究、发一篇干货链接要长久存入知识库的 👉 必须找 **ClaudeBot**。
> - 每天看自动发过来的炒股与商品行情日报、随便问个小问题 👉 用 **DeepSeekBot**。
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
