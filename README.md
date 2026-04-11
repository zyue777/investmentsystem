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
~/桌面/研究workflow优化/周期行业研究/
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

所有知识库正式内容写入 `04_Private_Knowledge/[子目录]/` 下：
- ClaudeBot 使用 `Path(kb) / '04_Private_Knowledge' / path`
- DeepSeekBot URL feed 自动补全 `04_Private_Knowledge/` 前缀

临时/预览文件只允许写入 `04_Private_Knowledge/_Raw_Inbox/`，**禁止在知识库根目录创建 `inbox/`、`draft/` 等临时目录**（见知识库 CLAUDE.md）。

---

## 详细文档

- [ClaudeBot 工作流](bot_claude/README.md)
- [DeepSeekBot 工作流](bot_gemini/README.md)
- [工作流检查清单](WORKFLOW_CHECKLIST.md)
