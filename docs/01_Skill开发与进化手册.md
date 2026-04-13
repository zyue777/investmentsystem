# Skill 开发与进化手册

---

## 一、Skill 是什么

Skill 是 Agent Hub 的**最小业务单元**。每个 Skill 是一个独立 Python 文件，负责处理一种用户意图。它：

- **只接收** `Context` 对象
- **只返回** `Context` 对象（修改后的）
- **不知道** 消息从哪来、发给谁
- **不关心** 用哪个 AI provider（由框架注入）

---

## 二、Skill 文件结构（最小模板）

```python
# bots/<bot_name>/skills/my_skill.py

from core.context import Context, ContextStatus, SkillManifest

# ── 必须：MANIFEST 声明 ──────────────────────────────────────────────────────
MANIFEST = SkillManifest(
    name="my_skill",           # 唯一标识符（全局唯一）
    description="一句话描述，≤50字，供 AI 意图分类使用",
    triggers=["指令前缀 "],    # 触发词列表，注意末尾空格
    version="1.0.0",
    tags=["分类标签"],
    priority=50,               # 数字越小优先级越高（P10最高，P100最低）
)


# ── 必须：handle 函数 ────────────────────────────────────────────────────────
def handle(ctx: Context) -> Context:
    """
    业务逻辑入口。

    可用的 ctx 字段：
    - ctx.raw_text        用户原始输入
    - ctx.parsed_args     Router 解析的参数 {'content': '...'}
    - ctx.user_id         用户飞书 open_id
    - ctx.workspace       知识库根目录路径
    - ctx.metadata        运行时注入的共享资源

    可用的 ctx.metadata 键：
    - _runtime            BotRuntime 实例（访问 phase_configs 等）
    - _pending_store      待确认状态存储
    - _dialog_history     对话历史
    - _dialog_mode        对话模式开关
    """
    text = ctx.raw_text.strip()

    # 调用 AI
    from core.executor import get_ai_provider
    provider = get_ai_provider(ctx)
    if not provider:
        ctx.reply_text = "❌ AI模型不可用"
        ctx.status = ContextStatus.ERROR
        return ctx

    result = provider.call_with_retry(f"处理以下内容：\n{text}", timeout=60)

    ctx.reply_text = result
    ctx.status = ContextStatus.SUCCESS
    return ctx
```

---

## 三、优先级设计规范

| 优先级 | 用途 | 示例 |
|--------|------|------|
| P10 | 系统指令（零Token）| `system_status` |
| P15 | 内容录入流程 | `ingest_record` |
| P20 | 自动触发（URL等）| `ingest_url`, `memo_save` |
| P25 | 模式切换 | `dialog_mode` |
| P30 | 框架更新（重量级AI）| `framework_update` |
| P40 | Phase 执行器 | `phase_execute` |
| P50 | 通用 AI 问答 | `kb_query` |
| P100 | 统计/沉淀（无AI）| `crystallize` |

---

## 四、触发词设计规范

```python
# ✅ 正确：末尾加空格，防止误触
triggers=["录 ", "问 ", "析 "]

# ✅ 正确：完整词，无歧义
triggers=["ping", "/stop", "/clear"]

# ❌ 错误：无空格会截断用户输入
triggers=["录"]   # "录音" 也会被匹配

# ❌ 错误：触发词过短，可能与其他 Skill 冲突
triggers=["s"]    # 已被 system_status 占用
```

---

## 五、Context 状态机

```
CREATED → ROUTED → EXECUTING → SUCCESS
                             ↘ ERROR
                             ↘ PENDING  (需确认，等待 ok/确认)
                             ↘ CANCELLED (dedup 静默丢弃)
```

- `PENDING`：Skill 把内容写入 `pending_store`，等用户回复 `ok`
- `CANCELLED`：**不发任何回复**，完全静默
- `ERROR`：框架自动用 `ctx.reply_text`（或 `ctx.error_message`）回复
- `SUCCESS`：用 `ctx.reply_text` 回复

---

## 六、Skill 进化路径（生命周期管理）

### 6.1 新增 Skill

```bash
# 1. 在对应 Bot 的 skills/ 目录新建文件
cp bots/_template/skills/example_skill.py bots/investment/skills/my_new_skill.py

# 2. 修改 MANIFEST（name/description/triggers/priority）

# 3. 实现 handle()

# 4. 重启 Bot（自动发现，无需改任何配置）
bash start.sh --daemon
```

### 6.2 修改已有 Skill

直接编辑 `.py` 文件，重启生效。`Registry` 在启动时动态加载，无缓存问题。

### 6.3 禁用 Skill（不删除代码）

```python
# 在 MANIFEST 中设置极低优先级 + 空触发词
MANIFEST = SkillManifest(
    name="my_skill",
    description="[DISABLED]",
    triggers=[],          # 无触发词 → 不会被自动匹配
    priority=999,
)
```

### 6.4 卸载 Skill

```bash
# 直接删除文件，重启后自动消失
rm bots/investment/skills/my_skill.py
bash start.sh --daemon
```

**零副作用**：Registry 只加载存在的文件，删除后不影响其他 Skill。

### 6.5 跨 Bot 共享 Skill

目前 investment 和 investment_ds **共享相同的 skill 文件**（各自目录内容一致）。

如果两个 Bot 需要**相同 Skill 但行为不同**：
```
方案 A：各自维护独立文件（当前方案，直观）
方案 B：skills/ 内 import 共享基类（适合差异较小时）
```

---

## 七、Skill 内部最佳实践

### 7.1 调用 AI 的标准写法

```python
from core.executor import get_ai_provider

provider = get_ai_provider(ctx)
if not provider:
    ctx.reply_text = "❌ AI模型不可用"
    ctx.status = ContextStatus.ERROR
    return ctx

# call_with_retry：内置指数退避重试
result = provider.call_with_retry(prompt, timeout=300, cwd=ctx.workspace)
```

### 7.2 调用 Tools 的标准写法

```python
# Tools 是全局无状态模块，直接 import 使用
from tools.file_write import write_file, git_commit
from tools.feishu_message import send_text
from tools.feishu_token import get_token
```

### 7.3 读取 Phase 配置

```python
runtime = ctx.metadata.get('_runtime')
phase_configs = runtime._phase_configs  # 来自 prompts/registry.yaml
p_cfg = phase_configs.get('p7', {})
```

### 7.4 禁止在 Skill 中做的事

```python
# ❌ 禁止：直接操作数据库、直接访问环境变量
import os; key = os.environ.get('DEEPSEEK_API_KEY')  # 应通过 Provider 层

# ❌ 禁止：直接 import 其他 Skill，形成硬依赖
from bots.investment.skills.phase_execute import handle as ph

# ❌ 禁止：在 Skill 中发飞书消息（绕过 Channel 层）
import requests; requests.post(feishu_url, ...)  # 应由 Channel 发送 ctx.reply_text

# ❌ 禁止：catch 所有异常并静默（影响 audit 日志）
try: ...
except: pass  # 至少记录一次
```

---

## 八、Skill 沉淀进化范式

```
阶段1（原型）：handle() 中直接写逻辑，硬编码 prompt
    ↓ 使用 10 次后
阶段2（提取）：把 prompt 移到 prompts/ 目录（.md 文件），handle() 只读取
    ↓ 需要跨 Bot 复用时
阶段3（Phase化）：把该 Skill 注册为 Phase，纳入 registry.yaml，
                  由 phase_execute 统一调度
    ↓ 需要更高频率或更强健壮性时
阶段4（Tool化）：把核心数据处理逻辑提取到 tools/，
                  Skill 只做编排
```
