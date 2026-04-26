# Agent Hub — 投研 & 报告双Bot平台

> 多Bot框架 · 飞书接入 · Claude + Gemini · 自动定时报告

---

## ⚡ 快速启动

```bash
cd /home/zy/investment_system
bash start.sh --daemon
```

**就这一条命令**。脚本会自动：
1. Kill 所有旧进程（幂等，可反复执行）
2. 启动 Claude 投研 Bot（飞书群1）
3. 启动 Gemini 投研 Bot（飞书群2）
4. 启动每日报告调度器（晨报/午盘/收盘）

```bash
bash start.sh --status   # 查看状态
bash start.sh --stop     # 停止全部
tail -f logs/main.log    # 查看实时日志
```

---

## 🤖 更换 AI 模型

系统的 AI 调用分两条独立路径，按需修改对应位置即可。

### 路径一：每日报告（晨报 / 复盘 / 自选股等）

**文件**：`daily_reporter/report_builder.py`

顶部初始化区域（约第 17 行）写死了使用哪个 Provider：

```python
from providers.gemini_api import GeminiProvider as _GeminiProvider
_gemini = _GeminiProvider()
```

换成其他 Provider 只需改这两行，例如换回 DeepSeek：

```python
from providers.deepseek_api import DeepSeekProvider as _GeminiProvider
_gemini = _GeminiProvider()
```

> 注意：`_call_gemini()` 函数名只是内部别名，无需改名，直接改 import 即可。

---

### 路径二：Bot 对话（用户主动发消息触发的 AI 回复）

**文件**：`providers/gemini_api.py`（当前主力 Provider）

修改默认模型型号：

```python
# GeminiProvider.call() 方法内（约第 22 行）
model = kwargs.get('model', 'gemini-2.5-flash')   # ← 改这里
```

**常用可用模型**（2026年）：

| 模型名 | 特点 |
|---|---|
| `gemini-2.5-flash` | 当前默认，速度快，性价比最高 ✅ |
| `gemini-2.5-pro` | 更强推理，token 消耗更高 |
| `gemini-2.0-flash` | 上一代 Flash，稳定备用 |

---

### 路径三：整体换成其他 Provider（如 DeepSeek / OpenAI）

1. 确认 `providers/` 下已有对应文件（如 `deepseek_api.py`）
2. 在 `.env` 配置对应 API Key：
   ```
   DEEPSEEK_API_KEY=sk-xxx
   ```
3. 修改 `report_builder.py` 顶部 import（见路径一）
4. 修改 `providers/gemini_api.py` 如不再需要可保持不动，bot 层另配
5. 重启服务：`bash start.sh --daemon`

> ⚠️ **费用提醒**：
> - DeepSeek `deepseek-chat`（V3）**按 token 计费**，大报告单次可达数千 token，一次晨报可能扣 10 元+。
> - **Gemini 2.5 Flash** 有较大免费额度，日常报告几乎零成本，**强烈建议优先使用 Gemini**。
> - 如需切回 DeepSeek，务必确认 `DEEPSEEK_API_KEY` 在 `.env` 中配置正确（当前保留但不使用）。

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

### 核心数据机制：扁平文件 + YAML标签 + Grep极速检索

投研知识库摈弃了沉重的结构化数据库或向量库，采用了一种**极低成本、极速、天然抗幻觉**的底层数据设计：
1. **统一扁平化存储**：所有行业研报统一平铺放入 `知识库/行业/` 目录下，**杜绝任何子文件夹**嵌套。
2. **标准化 YAML 元数据**：由 AI 蒸馏文章后，强制在所有的 `.md` 最顶部生成严谨的 YAML 头部（囊括明确的 DATE 和 TAGS：品种、标签、研报类型）。
3. **Grep 全文极速命中**：利用操作系统纯文本的正则 `grep`，直接对请求关键词（其实就是隐形的 TAGS 筛查）进行全局强命中，白嫖 OS 倒排索引的速度。
4. **Token 硬件截断**：`kb_search.py` 读取命中文件时，仅仅截断抽取最前方的精华信息区块（含 YAML 及量化事实），精准控制 AI 的 Token 消耗并避免冗长无用阅读。

## 目录结构

```
investment_system/
├── main.py              # 系统入口
├── start.sh             # 一键启动/停止/状态
├── run_single_bot.py    # 子进程启动入口
│
├── core/                # 框架核心（勿改）
├── channels/            # 渠道适配：feishu_ws / cli
├── providers/           # AI引擎：claude_cli / gemini_api / deepseek_api（备用）
├── hooks/               # 全局中间件：dedup/auth/timer/audit
├── tools/               # 共享工具：文件/飞书/搜索
│
├── bots/
│   ├── _template/       # 新Bot模板（复制此目录开始）
│   ├── investment/      # Claude 投研 Bot
│   ├── investment_ds/   # Gemini 投研 Bot
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

电脑开机后 **无需任何手动操作**，两套服务自动启动：

| 服务 | 触发方式 | 说明 |
|------|---------|------|
| 云端 Bot（investment_ds）| crontab `@reboot` | 30s 后执行 `start.sh --daemon`，日志：`logs/boot.log` |
| Claude relay 转发服务 | GNOME autostart | 登录桌面后 20s 执行 `启动Claude转发服务.sh`，日志：`logs/autostart.log` |

**Claude relay** 启动后会自动：建立 cloudflared 隧道 → 更新云端 .env → 重启云端 Claude Bot → 发送飞书上线通知。

```bash
# 查看 crontab 自启配置
crontab -l

# 查看 GNOME autostart 配置
cat ~/.config/autostart/claude-relay.desktop

# 手动重新启动 relay 服务
bash ~/桌面/CLOUD/启动Claude转发服务.sh
```

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
- 环境变量：在 `start.sh` 中统一配置（主要：`GEMINI_API_KEY`、`FEISHU_*`）

---

## 运行状态

当前三个服务均健康运行：

```
bash start.sh --status
=== Agent Hub 进程状态 ===
  ✅ main.py (PID xxxx)
  ✅ scheduler_runner.py (PID xxxx)
```
