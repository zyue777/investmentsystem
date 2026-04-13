# Hook 开发手册

---

## 一、Hook 是什么

Hook 是**横切关注点**（Cross-cutting Concerns）的实现机制。它不属于任何业务逻辑，而是在消息处理管道中自动插入，无需 Skill 感知。

**典型用途**：去重、鉴权、计时、审计、限流、日志、监控。

---

## 二、Hook 的执行时机

```
[before hooks]     ← 在 Skill 执行之前（按 priority 升序）
    dedup (P10)
    auth  (P20)
    timer (P30)
    ↓
Skill.handle(ctx)
    ↓
[after hooks]      ← 在 Skill 执行之后（按 priority 降序，洋葱模型）
    timer_after (P30)
    audit       (P20)

[on_error hooks]   ← Skill 抛出未捕获异常时
[on_success hooks] ← ctx.status == SUCCESS 时
```

---

## 三、Hook 文件结构

```python
# hooks/my_hook.py

from core.context import Context, ContextStatus, HookManifest

# ── 必须：MANIFEST 声明 ──────────────────────────────────────────────────────
MANIFEST = HookManifest(
    name="my_hook",
    phase="before",    # "before" | "after" | "on_error" | "on_success"
    priority=50,       # 数字越小越靠近 Skill 执行（before越早，after越晚）
    enabled=True,
)


# ── 必须：handle 函数 ────────────────────────────────────────────────────────
def handle(ctx: Context) -> Context:
    """
    before hook 必须返回 ctx。
    after/on_error/on_success hook 可以返回 None（只做副作用）。
    """
    # 若要中断后续处理：
    # ctx.status = ContextStatus.CANCELLED  # 静默中断
    # ctx.status = ContextStatus.ERROR      # 返回错误给用户
    return ctx
```

### 一个模块注册多个阶段（如 timer）

```python
# hooks/timer.py

MANIFEST     = HookManifest(name="timer",       phase="before", priority=30)
EXTRA_HOOKS  = [HookManifest(name="timer_after", phase="after",  priority=30)]

def handle(ctx):        # before: 记录开始时间
    ctx.metadata['_start_ms'] = time.time() * 1000
    return ctx

def get_extra_handler(name):   # after: 计算耗时
    if name == "timer_after":
        def after_handler(ctx):
            elapsed = int(time.time() * 1000 - ctx.metadata.get('_start_ms', 0))
            ctx.execution_time_ms = elapsed
        return after_handler
```

---

## 四、全局 Hook vs Bot 专属 Hook

| 类型 | 目录 | 激活方式 |
|------|------|---------|
| **全局 Hook** | `hooks/` | 在 `bot.yaml` 的 `global_hooks` 列表中声明 |
| **Bot 专属 Hook** | `bots/<name>/hooks/` | 自动加载，无需声明 |

```yaml
# bot.yaml
global_hooks: [dedup, auth, timer, audit]   # 引用 hooks/ 目录下的模块名
```

Bot 专属 Hook 会在全局 Hook 之后加载，相同 priority 时 Bot Hook 靠后执行。

---

## 五、当前四个全局 Hook 说明

### dedup（P10，before）

```python
# 防止飞书重发导致重复处理
# 用 message_id 做去重，内存 set，上限 2000 条
# ctx.status = CANCELLED → 静默丢弃（不回复用户）
```

**注意**：`_processed_ids` 是进程内变量。多 Bot 各有独立集合，但因为各 Bot 使用独立的飞书应用，message_id 天然不跨 Bot，无问题。

### auth（P20，before）

```python
# 白名单鉴权（可选）
# 环境变量：AGENT_HUB_WHITELIST=open_id1,open_id2
# 未设置环境变量 → 全部放行
```

**扩展**：如需接入企业权限系统，在此 Hook 中替换校验逻辑即可，Skill 层零修改。

### timer（P30，before+after）

```python
# before：记录 ctx.metadata['_start_ms']
# after：计算 ctx.execution_time_ms（毫秒）
# 供 audit hook 读取写入日志
```

### audit（P20，after）

```python
# 每次执行后写 executions.jsonl
# 路径：bots/<name>/memory/store/executions.jsonl
# 字段：request_id, timestamp, skill, ai_provider, status, execution_time_ms, input_summary
```

---

## 六、新增 Hook 完整步骤

```bash
# 场景：限流 Hook，每用户每分钟最多 10 条
```

**Step 1**：新建文件

```python
# hooks/rate_limit.py
import time, threading
from core.context import Context, ContextStatus, HookManifest

MANIFEST = HookManifest(name="rate_limit", phase="before", priority=15)

_counters = {}   # {user_id: [timestamps]}
_lock = threading.Lock()
LIMIT = 10
WINDOW = 60

def handle(ctx: Context) -> Context:
    uid = ctx.user_id
    now = time.time()
    with _lock:
        times = _counters.get(uid, [])
        times = [t for t in times if now - t < WINDOW]
        if len(times) >= LIMIT:
            ctx.status = ContextStatus.ERROR
            ctx.reply_text = f"⚠️ 请求过于频繁，每分钟最多 {LIMIT} 条"
            return ctx
        times.append(now)
        _counters[uid] = times
    return ctx
```

**Step 2**：在需要的 Bot 中激活

```yaml
# bots/investment/bot.yaml
global_hooks: [dedup, rate_limit, auth, timer, audit]   # 加入 rate_limit
```

**Step 3**：重启

```bash
bash start.sh --daemon
```

---

## 七、卸载 Hook

```bash
# 方法1：从 bot.yaml 的 global_hooks 列表中移除（不删文件）
# 方法2：删除文件（全部 Bot 生效）
# 方法3：设置 enabled=False（框架尊重此字段）
```

---

## 八、Hook 设计禁忌

```python
# ❌ 禁止：before hook 不返回 ctx
def handle(ctx):
    do_something()
    # 忘记 return ctx → 管道断裂，后续 hook 和 Skill 全部跳过

# ❌ 禁止：after hook 修改 ctx.reply_text（用户已看不到）
def handle(ctx):
    ctx.reply_text = "我再加点东西"  # 无效，reply 已发出

# ❌ 禁止：Hook 中调用 AI（加重每条消息的延迟和 Token 成本）
result = provider.call(...)  # 不应在 Hook 中出现

# ❌ 禁止：Hook 抛出异常而不 try/except
# middleware.py 会 catch 并 print，但最好自己处理
```
