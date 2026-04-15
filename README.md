# Agent Hub — 投研 & 报告双Bot平台

> 多Bot框架 · 飞书接入 · Claude + DeepSeek · 自动定时报告

---

## ⚡ 快速启动

```bash
cd /home/zy/investment_system
bash start.sh --daemon
```

**就这一条命令**。脚本会自动：
1. Kill 所有旧进程（幂等，可反复执行）
2. 启动 Claude 投研 Bot（飞书群1）
3. 启动 DeepSeek 投研 Bot（飞书群2）
4. 启动每日报告调度器（晨报/午盘/收盘）

```bash
bash start.sh --status   # 查看状态
bash start.sh --stop     # 停止全部
tail -f logs/main.log    # 查看实时日志
```

---

## 架构概览

```
用户消息 → 飞书 WS Channel
              ↓
         Context 对象创建
              ↓
         Hooks（去重→鉴权→计时）
              ↓
         Router（Session拦截→触发词→Phase→AI兜底）
              ↓
         Skill.handle(ctx)
              ↓
         Hooks（计时→审计日志）
              ↓
         飞书回复
```

五层结构：`Channel → Core → Bot/Skills → Tools → Providers`

---

## 目录结构

```
investment_system/
├── main.py              # 系统入口
├── start.sh             # 一键启动/停止/状态
├── run_single_bot.py    # 子进程启动入口
│
├── core/                # 框架核心（勿改）
├── channels/            # 渠道适配：feishu_ws / cli
├── providers/           # AI引擎：claude_cli / deepseek_api
├── hooks/               # 全局中间件：dedup/auth/timer/audit
├── tools/               # 共享工具：文件/飞书/搜索
│
├── bots/
│   ├── _template/       # 新Bot模板（复制此目录开始）
│   ├── investment/      # Claude 投研 Bot
│   ├── investment_ds/   # DeepSeek 投研 Bot
│   └── daily_report/    # 每日报告 Bot（定时驱动）
│
├── daily_reporter/      # 数据抓取层（被 daily_report 复用）
├── logs/                # 运行日志
└── docs/                # 开发文档（见下方）
```

---

## 文档

| 文档 | 说明 |
|------|------|
| [CLAUDE.md](CLAUDE.md) | Agent 入口文档（路由速查、Skill表、触发器） |
| [docs/00_架构总览](docs/00_架构总览.md) | 五层架构、消息流转、进程模型、已知问题 |
| [docs/01_开发手册](docs/01_开发手册.md) | Skill/Hook/Channel/Provider/Tool/Phase 开发规范 |
| [docs/02_运维与债务](docs/02_运维与债务.md) | 启动运维、定时任务、功能速查、技术债务 |
| [docs/03_架构知识卡](docs/03_架构知识卡.md) | 可复用的架构设计原则与铁律 |

---

## 新增 Bot（30秒）

```bash
cp -r bots/_template bots/my_bot
# 修改 bots/my_bot/bot.yaml（name/label/channel_config/ai_provider）
# 在 start.sh 中加入对应的飞书环境变量
bash start.sh --daemon   # 重启，自动发现新 Bot
```

## 新增 Skill（30秒）

```bash
# 在 bots/investment/skills/ 新建 .py 文件
# 实现 MANIFEST + handle(ctx) 函数
bash start.sh --daemon   # 重启生效，无需修改其他文件
```

---

## 🔄 开机自启（已配置）

电脑开机后 **自动启动所有服务**，无需手动操作。

原理：`crontab @reboot` → 等待 30 秒（网络就绪）→ 执行 `bash start.sh --daemon`

```bash
# 查看当前自启配置
crontab -l

# 关闭开机自启（编辑后删掉那一行即可）
crontab -e

# 重新开启
(crontab -l 2>/dev/null; echo "@reboot sleep 30 && cd /home/zy/investment_system && /bin/bash start.sh --daemon >> /home/zy/investment_system/logs/boot.log 2>&1") | crontab -
```


启动日志：`logs/boot.log`

---

## 🧹 缓存清理 & 定时维护

系统内置了 `clean.sh` 工具，用于清理 Python 字节码缓存、残留进程 ID 及历史冗余数据。

### 手动执行
```bash
bash clean.sh              # 默认安全清理（__pycache__ + PID）
bash clean.sh --all        # 深度清理（含日志及 executions.jsonl 历史）
bash clean.sh --dry-run    # 预览模式（不实际删除）
```

### 定时任务（已配置）
为保证服务器空间与系统响应速度，系统已配置 **每周五 10:00** 自动执行默认清理。

- **原理**：`crontab` 定时驱动
- **任务核查**：`crontab -l`
- **维护日志**：`logs/clean.log`

---

## 环境要求

- Python 3.10+（conda 环境 `investment_bot`）
- 依赖：`akshare tushare yfinance lark-oapi apscheduler openai python-docx pdfplumber`
- 环境变量：在 `start.sh` 中统一配置

---

## 运行状态

当前三个服务均健康运行：

```
bash start.sh --status
=== Agent Hub 进程状态 ===
  ✅ main.py (PID xxxx)
  ✅ scheduler_runner.py (PID xxxx)
```
