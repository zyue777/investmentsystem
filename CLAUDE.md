# investment_system — Claude Code 开发规范

## Git 规范

不要执行任何 git 命令，包括 commit、push、add、status。

---

## 项目结构

```
investment_system/
├── bot_claude/       # ClaudeBot — 飞书长连接，驱动 claude CLI，写知识库
├── bot_gemini/       # DeepSeekBot — 飞书长连接，调 DeepSeek API，快问答 + 日报推送
├── daily_reporter/   # 定时财经报告（apscheduler）
│   ├── data_fetcher.py   # 数据抓取（yfinance / akshare / tushare）
│   ├── report_builder.py # DeepSeek 生成报告文本
│   └── scheduler.py      # 定时任务入口
├── sentiment_monitor/ # 自选股情绪日记
├── shared/            # 公共工具（feishu_utils / memo_handler）
├── logs/              # 运行日志与 PID（自动生成，不入 git）
└── start.sh           # 一键后台启动
```

---

## 运行环境

- conda 环境：`investment_bot`（Python 解释器：`/home/zy/miniconda3/envs/investment_bot/bin/python3`）
- 启动：`bash ~/investment_system/start.sh`
- 日志：`tail -f logs/bot_claude.log` / `logs/bot_gemini.log`
- 停止：`kill $(cat logs/bot_claude.pid) $(cat logs/bot_gemini.pid) $(cat logs/daily_reporter.pid)`

---

## 配置文件

三个模块各有 `config.json`，**不入 git**（`.gitignore` 已屏蔽）。  
参照同目录 `config.json.example` 创建，填入真实的 `app_id` / `app_secret` / `api_key`。

---

## 知识库路径

两个 bot 共用外部知识库：`~/桌面/投研工作台/`

- ClaudeBot 写入：`知识库/行业/` 或 `知识库/个股/`（由 Claude 输出的 `FILE_PATH:` 行决定）
- DeepSeekBot 写入：`04_Private_Knowledge/` 前缀路径
- 临时文件只允许写入 `_Inbox/`，**禁止**在知识库根目录创建 `inbox/`、`draft/` 等目录

---

## 两个 Bot 的核心分工

| Bot | 底层 | 职责 |
|-----|------|------|
| bot_claude | `claude --print --dangerously-skip-permissions` | Phase 调度、录入确认、URL 全自动入库、知识库搜索 |
| bot_gemini | DeepSeek API (`deepseek-chat`) | 快速问答、URL 蒸馏确认入库、定时日报推送 |

---

## 数据原则

- **所有数字由 `data_fetcher.py` 抓取**，DeepSeek/Claude 不生成任何价格/涨跌幅
- 数据源：yfinance（美股/港股/大宗商品）、akshare（A股/财联社新闻）、tushare（A股指数/北向资金）
