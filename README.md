# Agent Hub — 多Bot平台

> 统一架构管理多个AI Bot，各自独立运行、互不影响。

## 快速启动

```bash
# 1. 激活环境
conda activate investment_bot

# 2. 设置环境变量（或写入 start.sh）
export FEISHU_INVEST_APP_ID=xxx
export FEISHU_INVEST_APP_SECRET=xxx
export FEISHU_DS_APP_ID=xxx
export FEISHU_DS_APP_SECRET=xxx
export DEEPSEEK_API_KEY=xxx

# 3. 启动
python main.py
# 或后台运行
nohup bash start.sh &
```

## 架构概览

```
agent_hub/
├── core/           # 核心引擎（Registry, Router, Executor, Middleware）
├── channels/       # 消息渠道（feishu_ws, cli）
├── providers/      # AI模型（claude_cli, deepseek_api）
├── tools/          # 共享工具（feishu_*, file_*, search_*, wechat_*）
├── hooks/          # 全局Hook（dedup, auth, timer, audit）
├── bots/           # Bot 目录（每个子目录 = 一个Bot）
│   ├── _template/  # 新Bot模板
│   ├── investment/ # 投研Bot (Claude)
│   ├── investment_ds/ # 投研Bot (DeepSeek)
│   └── health/     # 健康Bot（预留，disabled）
├── config/         # 全局配置
├── main.py         # 统一入口
├── run_single_bot.py  # 子进程Bot启动器
└── start.sh        # 启动脚本
```

## 5步创建新Bot

### 第1步：复制模板
```bash
cp -r bots/_template bots/my_bot
```

### 第2步：编辑 bot.yaml
```yaml
name: my_bot
label: "我的Bot"
enabled: true
channel: feishu_ws
channel_config:
  app_id: ${MY_BOT_APP_ID}
  app_secret: ${MY_BOT_APP_SECRET}
ai_provider: claude_cli
workspace: "/path/to/knowledge_base"
global_hooks: [dedup, auth, timer, audit]
```

### 第3步：编写 Skill
在 `bots/my_bot/skills/` 创建 `.py` 文件：

```python
from core.context import Context, ContextStatus, SkillManifest

MANIFEST = SkillManifest(
    name="greet",
    description="打招呼",
    triggers=["你好", "hello"],
)

def handle(ctx: Context) -> Context:
    ctx.reply_text = f"你好！我是 {ctx.bot_name}"
    ctx.status = ContextStatus.SUCCESS
    return ctx
```

### 第4步：设置环境变量
```bash
export MY_BOT_APP_ID=cli_xxx
export MY_BOT_APP_SECRET=xxx
```

### 第5步：启动
```bash
python main.py
# 控制台应显示：✅ 我的Bot (my_bot)
```

## CLI 调试模式

不需要飞书即可测试：

```bash
python run_single_bot.py my_bot
# 然后直接输入指令测试
```

> 注意：CLI 模式需要把 bot.yaml 中的 `channel: feishu_ws` 改为 `channel: cli`

## 目录说明

| 目录 | 说明 | 扩展方式 |
|------|------|----------|
| `tools/` | 所有Bot共享的工具 | 新建 `.py`，定义 `MANIFEST` + `handle()` |
| `hooks/` | 全局中间件 | 新建 `.py`，定义 `MANIFEST` + `handle()` |
| `providers/` | AI模型封装 | 新建 `.py`，继承 `ProviderBase` |
| `channels/` | 消息渠道 | 新建 `.py`，继承 `ChannelBase` |
| `bots/xxx/skills/` | Bot私有技能 | 新建 `.py`，定义 `MANIFEST` + `handle()` |
| `bots/xxx/hooks/` | Bot私有Hook | 同全局Hook |
| `bots/xxx/prompts/` | Bot私有Prompt | `phases/` 放Phase prompt，`system/` 放系统prompt |

## 设计原则

1. **零侵入**：新增Bot/Skill/Hook不需要修改任何现有代码
2. **可拔插**：删除任何模块，其余部分不受影响
3. **进程隔离**：多个飞书Bot各自运行在独立进程中（避免 asyncio event loop 冲突）
4. **审计可追溯**：所有执行记录自动写入 `memory/store/executions.jsonl`
