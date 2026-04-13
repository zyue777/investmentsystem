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

---

## 🧩 如何沉淀 Skill（核心扩展能力）

### 放在哪里？

| 位置 | 作用域 | 适用场景 |
|------|--------|----------|
| `bots/investment/skills/xxx.py` | 仅投研Bot可用 | 投研专属功能 |
| `bots/health/skills/xxx.py` | 仅健康Bot可用 | 健康专属功能 |
| `tools/xxx.py` | **所有Bot**共享 | 通用工具（文件操作、搜索等） |

> **零侵入原则**：新建 `.py` 文件放到目录里即可，**不需要修改任何现有文件**。
> 系统启动时自动发现、注册、路由。

### Skill 文件结构（必须遵守）

```python
"""一句话描述这个 Skill 做什么。"""
from core.context import Context, ContextStatus, SkillManifest

# ⬇️ 必须：模块级变量 MANIFEST
MANIFEST = SkillManifest(
    name="my_skill",           # 唯一标识符（英文+下划线）
    description="功能简述",     # ≤50字
    triggers=["触发词1", "触发词2"],  # 用户消息开头匹配这些词就路由到此 Skill
    version="1.0.0",           # 版本号
    tags=["分类标签"],          # 用于分组展示
    priority=50,               # 数字越小优先级越高（10=系统级, 50=普通, 100=兜底）
)

# ⬇️ 必须：handle 函数，接收 Context，返回 Context
def handle(ctx: Context) -> Context:
    # 你的业务逻辑
    ctx.reply_text = "回复内容"
    ctx.status = ContextStatus.SUCCESS  # 必须设置状态
    return ctx
```

### MANIFEST 字段详解

| 字段 | 必填 | 说明 |
|------|------|------|
| `name` | ✅ | 唯一ID，如 `memo_save`、`kb_query` |
| `description` | ✅ | 简短描述，会出现在日志和帮助中 |
| `triggers` | ✅ | 触发词列表。用户消息以此开头时路由到该 Skill |
| `version` | 否 | 版本号，默认 `1.0.0` |
| `tags` | 否 | 标签列表，用于分类 |
| `priority` | 否 | 优先级（默认100）。多个 Skill 触发词冲突时，数字小的优先 |
| `ai_provider` | 否 | 指定AI模型。空=用 bot.yaml 的默认模型 |

### Context 对象（你能用的数据）

```python
def handle(ctx: Context) -> Context:
    ctx.raw_text        # 用户原始消息全文，如 "录 某某纪要内容"
    ctx.user_id         # 飞书 open_id
    ctx.bot_name        # 当前Bot名称
    ctx.workspace       # 知识库根目录（来自 bot.yaml）
    ctx.parsed_args     # Router 解析的参数，如 {'content': '某某纪要内容'}
    ctx.metadata        # 扩展字典，可自由读写
    ctx.metadata.get('_runtime')       # BotRuntime 对象（可访问 phase_configs 等）
    ctx.metadata.get('_pending_store') # PendingStore（待确认内容管理）

    # ⬇️ 你需要设置的
    ctx.reply_text = "回复给用户的文字"
    ctx.status = ContextStatus.SUCCESS   # SUCCESS / ERROR / PENDING
    ctx.error_message = "出错原因"        # 仅 ERROR 时设置
    ctx.output_path = "/path/to/file"    # 如果产出了文件
    return ctx
```

### 三种常见 Skill 模式

#### 模式A：零Token（不调AI，最快）
```python
# 适用：状态查询、文件读取、搜索、系统指令
def handle(ctx: Context) -> Context:
    ctx.reply_text = "直接返回结果"
    ctx.status = ContextStatus.SUCCESS
    return ctx
```

#### 模式B：调用AI处理
```python
# 适用：问答、分析、生成报告
def handle(ctx: Context) -> Context:
    from core.executor import get_ai_provider
    provider = get_ai_provider(ctx)
    result = provider.call_with_retry("你的prompt", timeout=300, cwd=ctx.workspace)
    ctx.reply_text = result
    ctx.status = ContextStatus.SUCCESS
    return ctx
```

#### 模式C：需要确认的写入操作
```python
# 适用：录入、更新文件（先预览再写入）
def handle(ctx: Context) -> Context:
    pending_store = ctx.metadata.get('_pending_store')
    # ... 生成内容 ...
    pending_store.set(ctx.user_id, {'path': 'xxx', 'content': '...'})
    ctx.reply_text = "预览内容...\n回复 ok 确认"
    ctx.status = ContextStatus.PENDING  # 注意是 PENDING 不是 SUCCESS
    return ctx
```

### 实战示例：30秒沉淀一个新 Skill

假设你要加一个"日历"功能——用户发 `日历` 显示本周待跟踪事项：

```bash
# 1. 创建文件
touch bots/investment/skills/calendar_view.py
```

```python
# bots/investment/skills/calendar_view.py
"""查看本周跟踪日历。"""
from pathlib import Path
from core.context import Context, ContextStatus, SkillManifest

MANIFEST = SkillManifest(
    name="calendar_view",
    description="查看本周跟踪日历",
    triggers=["日历", "本周"],
    priority=30,
)

def handle(ctx: Context) -> Context:
    cal_file = Path(ctx.workspace) / "研究/跟踪日历.md"
    if cal_file.exists():
        ctx.reply_text = cal_file.read_text(encoding='utf-8')[:2800]
    else:
        ctx.reply_text = "📅 暂无跟踪日历"
    ctx.status = ContextStatus.SUCCESS
    return ctx
```

```bash
# 2. 重启（或者等下次启动就自动加载了）
# 不需要修改任何其他文件！
```

---

## 🪝 如何沉淀 Hook（中间件）

### Hook 是什么？

Hook 是在每个消息处理前/后自动执行的中间件，用于**横切关注点**：
- 计时、审计、去重、鉴权、限流、日志...
- **不关心具体业务逻辑**，对所有 Skill 统一生效

### 放在哪里？

| 位置 | 作用域 |
|------|--------|
| `hooks/xxx.py` | **全局**：所有Bot共用 |
| `bots/investment/hooks/xxx.py` | **私有**：仅该Bot使用 |

> 还需要在 `bot.yaml` 的 `global_hooks` 列表中声明才会启用（白名单机制）。

### Hook 文件结构

```python
"""一句话描述。"""
from core.context import Context, HookManifest

# ⬇️ 必须：MANIFEST
MANIFEST = HookManifest(
    name="my_hook",       # 唯一ID
    phase="before",       # before（处理前）| after（处理后）| on_error | on_success
    priority=50,          # 数字越小越先执行
)

# ⬇️ 必须：handle 函数
def handle(ctx: Context) -> Context:
    # before 阶段：可以修改 ctx、拦截请求
    # after 阶段：可以读取结果、做统计
    return ctx
```

### Hook 的 4 个执行阶段

```
用户消息 → [before hooks] → Router → Skill → [after hooks] → 回复
                                        ↓
                                  [on_error hooks]（如果出错）
                                  [on_success hooks]（如果成功）
```

| phase | 时机 | 典型用途 |
|-------|------|----------|
| `before` | Skill 执行**前** | 去重、鉴权、计时开始、请求日志 |
| `after` | Skill 执行**后** | 计时结束、审计记录、结果后处理 |
| `on_error` | Skill **报错**时 | 错误告警、错误统计 |
| `on_success` | Skill **成功**时 | 成功统计、触发后续流程 |

### 一个文件注册多个阶段（EXTRA_HOOKS 模式）

像 `timer.py` 需要在 before 记录开始时间、在 after 计算耗时。用 `EXTRA_HOOKS` 模式：

```python
"""执行计时 Hook。"""
import time
from core.context import Context, HookManifest

MANIFEST = HookManifest(name="timer", phase="before", priority=30)

def handle(ctx: Context) -> Context:
    ctx.metadata['_timer_start'] = time.time()
    return ctx

# ── 额外注册一个 after 阶段 ──
EXTRA_HOOKS = [
    HookManifest(name="timer_after", phase="after", priority=30),
]

def get_extra_handler(name: str):
    if name == "timer_after":
        return _handle_after
    return None

def _handle_after(ctx: Context) -> None:
    start = ctx.metadata.get('_timer_start', 0)
    if start:
        elapsed = int((time.time() - start) * 1000)
        ctx.execution_time_ms = elapsed
        print(f"[timer] {ctx.bot_name}/{ctx.matched_skill} 耗时 {elapsed}ms")
```

### 启用 Hook

光创建文件不够，还需要在 `bot.yaml` 中声明：

```yaml
# bot.yaml
global_hooks: [dedup, auth, timer, audit, my_hook]  # ← 加上你的 hook 名
```

### 实战示例：限流 Hook

```python
# hooks/rate_limit.py
"""请求限流 — 每用户每分钟最多10条。"""
import time
from collections import defaultdict
from core.context import Context, ContextStatus, HookManifest

MANIFEST = HookManifest(name="rate_limit", phase="before", priority=15)

_user_requests = defaultdict(list)

def handle(ctx: Context) -> Context:
    now = time.time()
    uid = ctx.user_id
    # 清除1分钟前的记录
    _user_requests[uid] = [t for t in _user_requests[uid] if now - t < 60]
    if len(_user_requests[uid]) >= 10:
        ctx.reply_text = "⚠️ 请求过于频繁，请稍后再试"
        ctx.status = ContextStatus.CANCELLED
        return ctx
    _user_requests[uid].append(now)
    return ctx
```

然后在 bot.yaml 的 global_hooks 加上 `rate_limit` 即可。

---

## 🔧 如何添加共享 Tool

Tool 放在 `tools/` 目录，所有Bot的所有Skill都能 `from tools.xxx import ...`。

```python
# tools/my_tool.py
"""我的工具描述。"""
from core.context import ToolManifest

MANIFEST = ToolManifest(name="my_tool", description="做某事")

def my_function(arg1, arg2):
    """工具的核心函数，Skill 会直接调用。"""
    return result

def handle(ctx):
    return ctx  # Tool 的 handle 通常是空的
```

在 Skill 中使用：
```python
from tools.my_tool import my_function
result = my_function(...)
```

---

## 🤖 如何添加 AI Provider

```python
# providers/my_model.py
"""我的模型接入。"""
from providers.base import ProviderBase
from core.context import ProviderManifest

MANIFEST = ProviderManifest(name="my_model", description="xxx API")

class MyProvider(ProviderBase):
    def call(self, prompt, timeout=300, cwd="", **kwargs):
        # 调用你的 API
        return "AI的回复"
    def check_available(self):
        return True  # 检查API可用性

def create_provider():
    return MyProvider()
```

在 bot.yaml 中切换：
```yaml
ai_provider: my_model  # ← 直接用 MANIFEST.name
```

---

## 📋 消息处理完整流程

```
飞书消息
  ↓
Channel (feishu_ws) 解析消息体
  ↓
build_context() → 创建 Context 对象
  ↓
[before hooks]  dedup → auth → timer → ...
  ↓
Router 三级匹配：
  1️⃣ Skill 触发词精确匹配（如 "s" → system_status）
  2️⃣ Phase 触发词匹配（如 "蒸馏" → phase_execute）
  3️⃣ AI fallback（无匹配时走 kb_query）
  ↓
Skill.handle(ctx) 执行业务逻辑
  ↓
[after hooks]  timer_after → audit → ...
  ↓
Channel.send_reply(ctx)  → 飞书回复
```

## 设计原则

1. **零侵入**：新增Bot/Skill/Hook不需要修改任何现有代码
2. **可拔插**：删除任何模块，其余部分不受影响
3. **进程隔离**：多个飞书Bot各自运行在独立进程中（避免 asyncio event loop 冲突）
4. **审计可追溯**：所有执行记录自动写入 `memory/store/executions.jsonl`
5. **白名单Hook**：Hook 创建后需在 bot.yaml 声明才生效，避免意外副作用
