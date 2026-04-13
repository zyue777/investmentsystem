# 🏗️ Agent Hub — 多Bot平台架构改造实施计划 v4（终版）

> **本文档是交付给新对话窗口的完整执行指南。**
> 新 AI 无需任何前置上下文，仅凭本文档即可完成全部改造。

---

## 0. 现状快照（新AI必读）

### 0.1 项目位置与技术栈

- **当前项目目录**：`/home/zy/investment_system/`（改造后重命名为 `agent_hub`）
- **知识库目录**：`/home/zy/桌面/投研工作台/`（纯数据仓库，**禁止写入任何代码/配置**）
- **语言**：Python 3（conda 环境 `investment_bot`）
- **飞书接入**：lark_oapi WebSocket 长连接（非 Webhook）
- **AI调用**：Claude CLI（`claude --print --dangerously-skip-permissions`）+ DeepSeek API
- **持久化**：纯文件系统（Markdown + JSON），无数据库
- **启动方式**：`bash start.sh`（nohup 后台运行）

### 0.2 现有核心文件清单

| 文件 | 行数 | 职责 |
|------|------|------|
| `bot_claude/bot.py` | 1275 | ⚠️ 上帝文件：路由+调度+录入+框架更新+对话+格式化+git |
| `bot_claude/config.json` | 9 | 飞书凭证 + 知识库路径 |
| `shared/feishu_utils.py` | 129 | ✅ 飞书API封装（4个函数） |
| `shared/memo_handler.py` | 56 | ✅ 备忘录存储 + git 提交 |
| `bot_gemini/bot.py` | ~700 | DeepSeek 快问答 bot |
| `daily_reporter/scheduler.py` | ~300 | APScheduler 定时任务 |
| `daily_reporter/data_fetcher.py` | ~900 | 数据抓取 |
| `daily_reporter/report_builder.py` | ~500 | DeepSeek 生成报告 |
| `start.sh` | 73 | 启动3个服务 |

### 0.3 现有功能清单（bot_claude 的全部指令）

**零Token指令**：`s`(状态) `d`(目录) `h`(帮助) `hh`(更多帮助) `e`(额度) `z`(最新) `库`(当前KB) `心法` `焦点` `图谱` `图谱 [行业]` `论 [行业]` `找 [关键词]` `memo [内容]`

**控制指令**：`/stop` `/clear` `/cancel` `/redo` `ok` `确认` `改 [意见]` `kk`(开始对话) `jj`(结束对话) `切 [KB名]`

**消耗Token指令**：`录 [内容]` `问 [问题]` `析 [行业] [问题]` `比 [A] [B]` `总 [主题]` `焦点+ [内容]` `图谱+ [行业] [内容]` `论+ [行业] [内容]` `初研 [行业]`

**URL投喂**：发送裸URL → 自动抓取+分类(p7/p11)+蒸馏+入库

**Phase触发**：`蒸馏/处理纪要`(p7) `周报/雷达`(p5) `月报A/B`(p2a/p2b) `滚动更新`(p4) `提炼备忘`(p10) `交流/p11`(p11)

### 0.4 用户核心要求

1. **多Bot共存**：投研Bot、健康Bot、未来更多Bot，各自skills/tasks隔离
2. **通用工具复用**：飞书API、文件操作等所有Bot可直接调用
3. **Channel即插即连**：飞书、微信、HTTP等接入渠道可插拔
4. **AI Provider可切换**：Claude、DeepSeek、GPT等AI模型可按Bot或按Skill切换
5. **新增功能零改动**：新skill/tool/hook/channel/provider = 新建文件，不改现有代码
6. **投研工作台是纯数据**：bot的代码/配置/prompt全在agent_hub内，工作台只被读写数据
7. **运行时简明**：消息到回复的链路尽量短，不走冗余流程
8. **Token节约**：能不调AI就不调，context裁剪到最小
9. **知识沉淀容易**：自动记录+人工一键沉淀，不增加工作量

---

## 1. 目标架构设计

### 1.1 分层架构

```
L0 — Channel 层：协议适配（飞书WS/微信/HTTP/CLI/定时器）→ 统一 Context
L1 — Core 层：Router（意图识别）→ Executor（执行引擎）→ Middleware（Hook管道）
L2 — Bot 层：每个Bot独立的 skills/ + prompts/ + hooks/ + memory/
L3 — Tool 层：所有Bot共享的原子操作（飞书API/文件/搜索）
L3 — Provider 层：AI模型抽象（Claude CLI/DeepSeek API/OpenAI API）
```

### 1.2 完整目录结构

```
agent_hub/
│
├── main.py                              # 统一入口
│
├── core/                                # 框架核心（所有Bot共享）
│   ├── __init__.py
│   ├── context.py                       # Context + 所有数据结构定义
│   ├── router.py                        # 三层路由器
│   ├── executor.py                      # 统一执行引擎
│   ├── middleware.py                    # Hook 中间件管道
│   ├── registry.py                      # 通用注册表（自动发现）
│   ├── bot_runtime.py                   # BotRuntime 运行时容器
│   ├── bot_loader.py                    # Bot 发现与加载
│   └── pending_store.py                 # 待确认状态管理
│
├── channels/                            # Channel 抽象层（即插即连）
│   ├── __init__.py
│   ├── base.py                          # ChannelBase 抽象类
│   ├── feishu_ws.py                     # 飞书 WebSocket
│   ├── wechat.py                        # 微信（预留）
│   ├── http_api.py                      # HTTP API（预留）
│   └── cli.py                           # 命令行（调试用）
│
├── providers/                           # AI Provider 抽象层（可切换）
│   ├── __init__.py
│   ├── base.py                          # ProviderBase（含重试+降级）
│   ├── claude_cli.py                    # Claude CLI
│   ├── deepseek_api.py                  # DeepSeek API
│   └── openai_api.py                    # OpenAI（预留）
│
├── tools/                               # 共享工具箱（无状态原子操作）
│   ├── __init__.py
│   ├── feishu_message.py
│   ├── feishu_file.py
│   ├── feishu_token.py
│   ├── file_read.py
│   ├── file_write.py
│   ├── search_grep.py
│   ├── wechat_fetch.py
│   └── data_fetch.py
│
├── hooks/                               # 全局 Hook
│   ├── __init__.py
│   ├── dedup.py
│   ├── auth.py
│   ├── timer.py
│   └── audit.py
│
├── bots/                                # 每个Bot完全隔离
│   ├── _template/                       # 空白模板
│   │   ├── bot.yaml
│   │   ├── skills/__init__.py + hello.py
│   │   ├── hooks/__init__.py
│   │   ├── prompts/registry.yaml
│   │   └── memory/store/
│   │
│   ├── investment/                      # 投研Bot
│   │   ├── bot.yaml
│   │   ├── skills/ (9个)
│   │   ├── hooks/
│   │   ├── prompts/ (registry.yaml + phases/ + system/)
│   │   └── memory/store/
│   │
│   ├── gemini/                          # DeepSeek快问答Bot
│   └── daily_report/                    # 每日报告Bot
│
├── config/
│   ├── settings.py
│   └── global.yaml
│
├── logs/
├── start.sh
├── requirements.txt
└── README.md
```

---

## 2. 核心数据结构（完整代码）

### 2.1 `core/context.py`

```python
"""统一数据结构定义。"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class ContextStatus(str, Enum):
    CREATED = "created"
    ROUTED = "routed"
    EXECUTING = "executing"
    PENDING = "pending"
    SUCCESS = "success"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass
class Context:
    """贯穿所有层的统一对象。"""
    # ── Channel 层创建 ──
    request_id: str = ""
    bot_name: str = ""
    channel: str = "feishu"
    user_id: str = ""
    raw_text: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    # ── Router 层填充 ──
    matched_skill: str = ""
    match_confidence: float = 1.0
    parsed_args: dict = field(default_factory=dict)
    # ── Skill 层填充 ──
    status: ContextStatus = ContextStatus.CREATED
    workspace: str = ""
    phase_key: str = ""
    ai_provider: str = ""
    ai_raw_output: str = ""
    output_path: str = ""
    output_content: str = ""
    # ── 结果 ──
    reply_text: str = ""
    error_message: str = ""
    execution_time_ms: int = 0
    # ── 扩展 ──
    metadata: dict = field(default_factory=dict)


@dataclass
class SkillManifest:
    name: str
    description: str                       # ≤50字
    triggers: list[str] = field(default_factory=list)
    version: str = "1.0.0"
    tags: list[str] = field(default_factory=list)
    priority: int = 100
    ai_provider: str = ""                  # 空=用Bot默认


@dataclass
class ToolManifest:
    name: str
    description: str
    version: str = "1.0.0"


@dataclass
class HookManifest:
    name: str
    phase: str                             # before | after | on_error | on_success
    priority: int = 100
    enabled: bool = True


@dataclass
class ChannelManifest:
    name: str
    description: str
    version: str = "1.0.0"


@dataclass
class ProviderManifest:
    name: str
    description: str
    version: str = "1.0.0"


@dataclass
class PhaseConfig:
    key: str
    label: str
    prompt_file: str
    triggers: list[str] = field(default_factory=list)
    timeout: int = 300
    output_dir: str = ""
    needs_confirm: bool = True
    accepts_inline: bool = False
    ai_provider: str = ""


@dataclass
class ExecutionRecord:
    request_id: str
    timestamp: str
    bot_name: str
    user_id: str
    channel: str
    matched_skill: str
    ai_provider: str
    status: str
    execution_time_ms: int
    input_summary: str
    output_path: str = ""
    error_message: str = ""
```

---

## 3. Channel 抽象层

### 3.1 `channels/base.py`

```python
"""Channel 抽象基类。"""
from abc import ABC, abstractmethod
from core.context import Context


class ChannelBase(ABC):
    @abstractmethod
    def start(self, runtime):
        """启动监听（可阻塞）。"""
        pass
    
    @abstractmethod
    def send_reply(self, ctx: Context):
        """将结果发回用户。"""
        pass
    
    def build_context(self, runtime, **kwargs) -> Context:
        return Context(
            bot_name=runtime.config.name,
            channel=getattr(self, 'MANIFEST', type('', (), {'name': 'unknown'})).name,
            workspace=runtime.config.workspace,
            **kwargs,
        )
```

### 3.2 `channels/feishu_ws.py`

```python
"""飞书 WebSocket 长连接渠道。"""
import json
import threading
import lark_oapi as lark
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1
from channels.base import ChannelBase
from core.context import Context, ChannelManifest

MANIFEST = ChannelManifest(name="feishu_ws", description="飞书WebSocket长连接")


class FeishuWSChannel(ChannelBase):
    
    def start(self, runtime):
        cfg = runtime.config.channel_config
        self._runtime = runtime
        self._app_id = cfg.get('app_id', '')
        self._app_secret = cfg.get('app_secret', '')
        
        def on_message(data: P2ImMessageReceiveV1):
            try:
                msg = data.event.message
                sender = data.event.sender
                if not msg or not sender or msg.message_type != 'text':
                    return
                content = json.loads(msg.content or '{}')
                raw_text = content.get('text', '').strip()
                if not raw_text:
                    return
                open_id = sender.sender_id.open_id if sender.sender_id else ''
                if not open_id:
                    return
                ctx = self.build_context(runtime,
                    request_id=msg.message_id or '', user_id=open_id,
                    raw_text=raw_text,
                    metadata={'app_id': self._app_id, 'app_secret': self._app_secret},
                )
                threading.Thread(target=self._handle, args=(ctx,), daemon=True).start()
            except Exception as e:
                print(f"[feishu/{runtime.config.name}] 异常: {e}")
        
        handler = (lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(on_message).build())
        print(f"[feishu/{runtime.config.name}] 连接飞书...")
        lark.ws.Client(self._app_id, self._app_secret,
                       event_handler=handler, log_level=lark.LogLevel.INFO).start()
    
    def _handle(self, ctx: Context):
        from core.executor import execute_in_runtime
        ctx = execute_in_runtime(self._runtime, ctx)
        self.send_reply(ctx)
    
    def send_reply(self, ctx: Context):
        if not ctx.reply_text:
            return
        from tools.feishu_token import get_token
        from tools.feishu_message import send_text
        token = get_token(ctx.metadata.get('app_id', ''), ctx.metadata.get('app_secret', ''))
        send_text(token, ctx.user_id, ctx.reply_text)

def create_channel():
    return FeishuWSChannel()
```

新增 Channel 只需实现 `ChannelBase` 的 `start` 和 `send_reply`。Bot 配置中 `channel: wechat` 一行切换。

---

## 4. AI Provider 抽象层（含重试与降级）

### 4.1 `providers/base.py`（含重试装饰器 + 降级机制）

```python
"""AI Provider 抽象基类，内置重试和降级能力。"""
import time
from abc import ABC, abstractmethod


class ProviderBase(ABC):
    @abstractmethod
    def call(self, prompt: str, timeout: int = 300, cwd: str = "", **kwargs) -> str:
        pass
    
    @abstractmethod
    def check_available(self) -> bool:
        pass
    
    def call_with_retry(self, prompt: str, timeout: int = 300,
                        cwd: str = "", max_retries: int = 2,
                        backoff: float = 2.0, **kwargs) -> str:
        """带指数退避重试的调用。Provider 不可用时抛出异常供 executor 降级。"""
        last_error = ""
        for attempt in range(max_retries + 1):
            result = self.call(prompt, timeout, cwd, **kwargs)
            # 正常结果
            if not result.startswith("❌") and not result.startswith("⏸️"):
                return result
            last_error = result
            # 限流 → 重试
            if "⏸️" in result and attempt < max_retries:
                wait = backoff ** attempt
                print(f"[provider] 限流，{wait}s后重试 ({attempt+1}/{max_retries})")
                time.sleep(wait)
                continue
            # 硬错误 → 不重试
            if "❌" in result:
                break
        return last_error
```

### 4.2 `providers/claude_cli.py`

```python
"""Claude CLI Provider。"""
import subprocess
from providers.base import ProviderBase
from core.context import ProviderManifest

MANIFEST = ProviderManifest(name="claude_cli", description="本地Claude CLI调用")

class ClaudeCLIProvider(ProviderBase):
    def call(self, prompt: str, timeout: int = 300, cwd: str = "", **kwargs) -> str:
        try:
            proc = subprocess.Popen(
                ['claude', '--print', '--dangerously-skip-permissions', prompt],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                cwd=cwd or None,
            )
            stdout, stderr = proc.communicate(timeout=timeout)
            if stdout.strip():
                return stdout.strip()
            err = stderr.strip()
            if err and ('rate' in err.lower() or 'limit' in err.lower()):
                return "⏸️ AI 额度暂时耗尽"
            return err if err else "（无输出）"
        except subprocess.TimeoutExpired:
            proc.kill()
            return f"❌ 超时（{timeout}s）"
        except FileNotFoundError:
            return "❌ 未找到 claude 命令"
        except Exception as e:
            return f"❌ 异常: {e}"
    
    def check_available(self) -> bool:
        try:
            r = subprocess.run(['claude', '--version'], capture_output=True, text=True, timeout=5)
            return r.returncode == 0
        except Exception:
            return False

def create_provider():
    return ClaudeCLIProvider()
```

### 4.3 `providers/deepseek_api.py`

```python
"""DeepSeek API Provider。"""
import os, requests
from providers.base import ProviderBase
from core.context import ProviderManifest

MANIFEST = ProviderManifest(name="deepseek_api", description="DeepSeek Chat API")

class DeepSeekProvider(ProviderBase):
    API_URL = "https://api.deepseek.com/chat/completions"
    def call(self, prompt, timeout=300, cwd="", **kwargs):
        api_key = kwargs.get('api_key') or os.environ.get('DEEPSEEK_API_KEY', '')
        model = kwargs.get('model', 'deepseek-chat')
        if not api_key:
            return "❌ 未设置 DEEPSEEK_API_KEY"
        try:
            resp = requests.post(self.API_URL,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": model, "messages": [{"role": "user", "content": prompt}]},
                timeout=timeout)
            return resp.json()['choices'][0]['message']['content']
        except Exception as e:
            return f"❌ DeepSeek 失败: {e}"
    def check_available(self):
        return bool(os.environ.get('DEEPSEEK_API_KEY'))

def create_provider():
    return DeepSeekProvider()
```

Provider 解析优先级：`Skill指定 > Phase指定 > Bot默认 > 全局兜底(claude_cli)`。
切换AI = 改 `bot.yaml` 的 `ai_provider` 字段或 Skill 的 `MANIFEST.ai_provider`。

---

## 5. 核心框架完整代码

### 5.1 `core/registry.py`

```python
"""通用注册表，支持自动发现。"""
import importlib, pkgutil
from pathlib import Path
from typing import Any, Callable, Optional

class Registry:
    def __init__(self, name: str):
        self.name = name
        self._items: dict[str, dict] = {}
    
    def discover(self, package_path: str, package_name: str):
        pkg_dir = Path(package_path)
        if not pkg_dir.exists():
            return
        for info in pkgutil.iter_modules([str(pkg_dir)]):
            if info.name.startswith('_'):
                continue
            try:
                mod = importlib.import_module(f"{package_name}.{info.name}")
                manifest = getattr(mod, 'MANIFEST', None)
                handler = (getattr(mod, 'handle', None)
                          or getattr(mod, 'create_channel', None)
                          or getattr(mod, 'create_provider', None))
                if manifest:
                    self._items[manifest.name] = {
                        'manifest': manifest, 'handler': handler, 'module': mod}
            except Exception as e:
                print(f"[{self.name}] 跳过 {info.name}: {e}")
        print(f"[{self.name}] 已注册 {len(self._items)} 项")
    
    def get(self, name: str) -> Optional[dict]:
        return self._items.get(name)
    
    def get_handler(self, name: str) -> Optional[Callable]:
        item = self._items.get(name)
        return item['handler'] if item else None
    
    def get_instance(self, name: str) -> Any:
        handler = self.get_handler(name)
        return handler() if handler and callable(handler) else None
    
    def match_by_trigger(self, text: str) -> list[dict]:
        matches = []
        text_lower = text.lower()
        for name, item in self._items.items():
            for trigger in getattr(item['manifest'], 'triggers', []):
                tl = trigger.lower()
                if text_lower == tl or text_lower.startswith(tl + ' ') or text_lower.startswith(tl + '\n'):
                    matches.append({'name': name, 'manifest': item['manifest'],
                                    'handler': item['handler'], 'trigger': trigger})
                    break
        matches.sort(key=lambda m: getattr(m['manifest'], 'priority', 100))
        return matches
    
    def all_items(self) -> list[dict]:
        return list(self._items.values())
    
    def count(self) -> int:
        return len(self._items)
    
    def to_ai_index(self) -> str:
        lines = []
        for item in self._items.values():
            m = item['manifest']
            triggers = ', '.join(getattr(m, 'triggers', [])[:3])
            lines.append(f"- {m.name}: {m.description}" + (f" [触发:{triggers}]" if triggers else ""))
        return '\n'.join(lines)
```

### 5.2 `core/middleware.py`

```python
"""洋葱模型中间件管道。"""
from typing import Callable
from core.context import Context, ContextStatus

class MiddlewarePipeline:
    def __init__(self):
        self._before: list[tuple[int, str, Callable]] = []
        self._after: list[tuple[int, str, Callable]] = []
        self._on_error: list[tuple[int, str, Callable]] = []
        self._on_success: list[tuple[int, str, Callable]] = []
    
    def register_hook(self, name, phase, fn, priority=100):
        target = {'before': self._before, 'after': self._after,
                  'on_error': self._on_error, 'on_success': self._on_success}.get(phase)
        if target is not None:
            target.append((priority, name, fn))
            target.sort(key=lambda x: x[0])
    
    def execute(self, ctx: Context, handler: Callable) -> Context:
        # Before hooks
        for _, name, hook in self._before:
            try:
                ctx = hook(ctx)
                if ctx.status in (ContextStatus.ERROR, ContextStatus.CANCELLED):
                    return ctx
            except Exception as e:
                print(f"[hook/{name}] before 异常: {e}")
        
        # 核心执行
        try:
            ctx.status = ContextStatus.EXECUTING
            ctx = handler(ctx)
        except Exception as e:
            ctx.status = ContextStatus.ERROR
            ctx.error_message = str(e)
            for _, name, hook in self._on_error:
                try: hook(ctx)
                except: pass
            return ctx
        
        # Success hooks
        if ctx.status == ContextStatus.SUCCESS:
            for _, _, hook in self._on_success:
                try: hook(ctx)
                except: pass
        
        # After hooks（倒序，洋葱模型）
        for _, name, hook in reversed(self._after):
            try: hook(ctx)
            except Exception as e:
                print(f"[hook/{name}] after 异常: {e}")
        
        return ctx
```

### 5.3 `core/pending_store.py`

```python
"""待确认状态管理（ok/改/cancel），按 bot_name+user_id 隔离。"""
import time, threading

class PendingStore:
    TIMEOUT = 1800
    def __init__(self, namespace: str):
        self._ns = namespace
        self._store: dict = {}
        self._lock = threading.Lock()
    
    def set(self, user_id: str, data: dict):
        with self._lock:
            data['_ts'] = time.time()
            self._store[user_id] = data
    
    def get(self, user_id: str) -> dict | None:
        self._clean()
        with self._lock:
            return self._store.get(user_id)
    
    def pop(self, user_id: str) -> dict | None:
        with self._lock:
            return self._store.pop(user_id, None)
    
    def _clean(self):
        now = time.time()
        with self._lock:
            expired = [k for k, v in self._store.items() if now - v.get('_ts', 0) > self.TIMEOUT]
            for k in expired:
                del self._store[k]
```

### 5.4 `core/executor.py`（完整实现）

```python
"""统一执行引擎。这是消息处理的核心函数。"""
from core.context import Context, ContextStatus
from core.bot_runtime import BotRuntime


def execute_in_runtime(runtime: BotRuntime, ctx: Context) -> Context:
    """完整的消息处理链路：Route → Middleware → Skill → Reply。
    
    这个函数是系统的"心脏"，整个调用链条如下：
    Channel.on_message → execute_in_runtime → Channel.send_reply
    """
    try:
        # ── Step 1: 路由 ──
        ctx = runtime.router.route(ctx)
        
        if ctx.status == ContextStatus.ERROR:
            ctx.reply_text = ctx.error_message or "无法识别指令"
            return ctx
        
        # ── Step 2: 查找 skill handler ──
        handler = runtime.skill_registry.get_handler(ctx.matched_skill)
        if handler is None:
            ctx.status = ContextStatus.ERROR
            ctx.reply_text = f"技能 [{ctx.matched_skill}] 未注册"
            return ctx
        
        # ── Step 3: 注入运行时依赖到 metadata ──
        # skill 通过 ctx.metadata 访问 runtime 提供的共享资源
        ctx.metadata['_runtime'] = runtime
        ctx.metadata['_pending_store'] = runtime.pending_store
        ctx.metadata['_dialog_history'] = runtime.dialog_history
        ctx.metadata['_dialog_mode'] = runtime.dialog_mode
        
        # ── Step 4: 解析 AI Provider ──
        skill_item = runtime.skill_registry.get(ctx.matched_skill)
        skill_manifest = skill_item['manifest'] if skill_item else None
        ctx.ai_provider = _resolve_provider_name(
            skill_manifest, ctx.phase_key, runtime)
        
        # ── Step 5: 通过 Middleware 管道执行 ──
        ctx = runtime.pipeline.execute(ctx, handler)
        
        # ── Step 6: 兜底回复 ──
        if not ctx.reply_text and ctx.status == ContextStatus.ERROR:
            ctx.reply_text = ctx.error_message or "处理失败"
        
        return ctx
    
    except Exception as e:
        ctx.status = ContextStatus.ERROR
        ctx.error_message = str(e)
        ctx.reply_text = f"❌ 系统异常: {e}"
        return ctx


def _resolve_provider_name(skill_manifest, phase_key, runtime) -> str:
    """Provider 优先级：Skill指定 > Phase指定 > Bot默认 > claude_cli"""
    # 1. Skill 级
    if skill_manifest and getattr(skill_manifest, 'ai_provider', ''):
        return skill_manifest.ai_provider
    # 2. Phase 级
    if phase_key and phase_key in runtime._phase_configs:
        phase_provider = runtime._phase_configs[phase_key].get('ai_provider', '')
        if phase_provider:
            return phase_provider
    # 3. Bot 级
    if runtime.config.ai_provider:
        return runtime.config.ai_provider
    # 4. 全局兜底
    return 'claude_cli'


def get_ai_provider(ctx: Context):
    """Skill 内部调用此函数获取 AI Provider 实例。"""
    runtime = ctx.metadata.get('_runtime')
    if not runtime:
        return None
    provider_name = ctx.ai_provider or 'claude_cli'
    provider = runtime.provider_registry.get_instance(provider_name)
    if not provider:
        # 降级：如果指定 provider 不可用，尝试 Bot 默认
        fallback = runtime.config.ai_provider or 'claude_cli'
        if fallback != provider_name:
            print(f"[executor] {provider_name} 不可用，降级到 {fallback}")
            provider = runtime.provider_registry.get_instance(fallback)
    return provider
```

### 5.5 `core/router.py`

```python
"""三层路由器：精确触发词 → Phase触发词 → AI fallback。"""
import re
from core.context import Context, ContextStatus

class Router:
    def __init__(self, skill_registry, phase_configs: dict):
        self._skill_reg = skill_registry
        self._phase_configs = phase_configs
        self._url_re = re.compile(r'https?://\S+')
    
    def route(self, ctx: Context) -> Context:
        text = ctx.raw_text.strip()
        
        # URL 投喂检测
        url_m = self._url_re.search(text)
        if url_m and text.strip() == url_m.group(0):
            ctx.matched_skill = 'ingest_url'
            ctx.parsed_args = {'url': url_m.group(0)}
            ctx.match_confidence = 1.0
            ctx.status = ContextStatus.ROUTED
            return ctx
        
        # 第1层：Skill 触发词
        matches = self._skill_reg.match_by_trigger(text)
        if matches:
            best = matches[0]
            ctx.matched_skill = best['name']
            ctx.match_confidence = 1.0
            remainder = text[len(best['trigger']):].strip()
            ctx.parsed_args = {'content': remainder} if remainder else {}
            ctx.status = ContextStatus.ROUTED
            return ctx
        
        # 第2层：Phase 触发词
        for key, cfg in self._phase_configs.items():
            for trigger in cfg.get('triggers', []):
                tl = trigger.lower()
                if text.lower() == tl or text.lower().startswith(tl + ' '):
                    ctx.matched_skill = 'phase_execute'
                    ctx.phase_key = cfg['key']
                    ctx.parsed_args = {'phase_key': cfg['key'],
                                       'extra': text[len(trigger):].strip()}
                    ctx.match_confidence = 1.0
                    ctx.status = ContextStatus.ROUTED
                    return ctx
        
        # 第3层：AI fallback（消耗 token）
        ai_result = self._ai_match(text, ctx)
        if ai_result:
            ctx.matched_skill = ai_result
            ctx.match_confidence = 0.7
            ctx.status = ContextStatus.ROUTED
            return ctx
        
        # Fallback → 通用问答
        ctx.matched_skill = 'kb_query'
        ctx.match_confidence = 0.5
        ctx.parsed_args = {'question': text}
        ctx.status = ContextStatus.ROUTED
        return ctx
    
    def _ai_match(self, text, ctx):
        index = self._skill_reg.to_ai_index()
        if not index:
            return None
        from core.executor import get_ai_provider
        provider = get_ai_provider(ctx)
        if not provider:
            return None
        prompt = ("意图分类器。只输出JSON: {\"skill\":\"名称或null\"}\n"
                  f"可用技能:\n{index}\n\n用户消息: {text[:300]}")
        try:
            import json
            result = provider.call(prompt, timeout=30, cwd=ctx.workspace)
            return json.loads(result).get('skill')
        except: return None
```

### 5.6 `core/bot_runtime.py`

```python
"""BotRuntime — 单个Bot的隔离运行时容器。"""
import yaml
from dataclasses import dataclass, field
from pathlib import Path
from collections import deque
from core.registry import Registry
from core.router import Router
from core.middleware import MiddlewarePipeline
from core.pending_store import PendingStore


@dataclass
class BotConfig:
    name: str
    label: str = ""
    enabled: bool = True
    channel: str = "feishu_ws"
    channel_config: dict = field(default_factory=dict)
    ai_provider: str = "claude_cli"
    workspace: str = ""
    description: str = ""
    max_concurrent: int = 5
    default_timeout: int = 300
    global_hooks: list = field(default_factory=lambda: ['dedup', 'auth', 'timer', 'audit'])


class BotRuntime:
    def __init__(self, config: BotConfig, bot_dir: Path,
                 global_tool_registry: Registry,
                 global_hook_registry: Registry,
                 global_provider_registry: Registry):
        self.config = config
        self.bot_dir = bot_dir
        
        # 共享层
        self.tool_registry = global_tool_registry
        self.provider_registry = global_provider_registry
        
        # 隔离层
        self.skill_registry = Registry(f"{config.name}/skills")
        self.pipeline = MiddlewarePipeline()
        self.pending_store = PendingStore(namespace=config.name)
        self.dialog_history: dict[str, deque] = {}
        self.dialog_mode: dict[str, bool] = {}
        
        # 加载
        self._load_skills()
        self._load_hooks(global_hook_registry)
        self._load_phase_configs()
        self.router = Router(self.skill_registry, self._phase_configs)
    
    def _load_skills(self):
        d = self.bot_dir / 'skills'
        if d.exists():
            self.skill_registry.discover(str(d), f"bots.{self.config.name}.skills")
    
    def _load_hooks(self, global_hooks):
        # 注入用户选择的全局 hook
        allowed = set(self.config.global_hooks)
        for item in global_hooks.all_items():
            if item['manifest'].name in allowed:
                m = item['manifest']
                fn = item.get('handler')
                if fn: self.pipeline.register_hook(m.name, m.phase, fn, m.priority)
        # Bot 专属 hook
        d = self.bot_dir / 'hooks'
        if d.exists():
            bot_hooks = Registry(f"{self.config.name}/hooks")
            bot_hooks.discover(str(d), f"bots.{self.config.name}.hooks")
            for item in bot_hooks.all_items():
                m = item['manifest']
                fn = item.get('handler')
                if fn: self.pipeline.register_hook(m.name, m.phase, fn, m.priority)
    
    def _load_phase_configs(self):
        reg_file = self.bot_dir / 'prompts' / 'registry.yaml'
        if reg_file.exists():
            with open(reg_file, 'r', encoding='utf-8') as f:
                self._phase_configs = yaml.safe_load(f).get('phases', {})
        else:
            self._phase_configs = {}
```

### 5.7 `core/bot_loader.py`

> [!IMPORTANT]
> **施工勘误（v4.1）**：原设计用 `threading.Thread` 启动多个飞书 WebSocket Channel，
> 但 `lark_oapi.ws.Client.start()` 内部使用 `asyncio.get_event_loop().run_until_complete()`，
> 多个线程共用同一个 event loop 会导致 `RuntimeError: This event loop is already running`。
> **修正方案**：第1个Bot在主进程内线程启动，第2个及后续Bot各自使用独立子进程（`subprocess.Popen`）。
> 新增 `run_single_bot.py` 作为子进程入口。

```python
"""Bot 发现、加载、启动。"""
import os, re, yaml, threading
from pathlib import Path
from core.registry import Registry
from core.bot_runtime import BotRuntime, BotConfig


class BotLoader:
    def __init__(self, project_root: Path):
        self.root = project_root
        self.global_tools = Registry("global/tools")
        self.global_hooks = Registry("global/hooks")
        self.global_providers = Registry("global/providers")
        
        # 加载全局共享层
        self.global_tools.discover(str(project_root / 'tools'), 'tools')
        self.global_hooks.discover(str(project_root / 'hooks'), 'hooks')
        self.global_providers.discover(str(project_root / 'providers'), 'providers')
    
    def discover_and_load(self) -> list[BotRuntime]:
        runtimes = []
        bots_dir = self.root / 'bots'
        for bot_dir in sorted(bots_dir.iterdir()):
            if not bot_dir.is_dir() or bot_dir.name.startswith('_'):
                continue
            cfg_file = bot_dir / 'bot.yaml'
            if not cfg_file.exists():
                continue
            try:
                config = self._load_config(cfg_file)
                if not config.enabled:
                    print(f"[loader] 跳过 {config.label}（disabled）")
                    continue
                runtime = BotRuntime(config, bot_dir,
                    self.global_tools, self.global_hooks, self.global_providers)
                self._start_channel(runtime)
                runtimes.append(runtime)
                print(f"[loader] ✅ {config.label}（{runtime.skill_registry.count()} skills）")
            except Exception as e:
                # 单个Bot失败不影响其他Bot
                print(f"[loader] ❌ {bot_dir.name} 失败: {e}")
        return runtimes
    
    def _load_config(self, path: Path) -> BotConfig:
        raw = path.read_text(encoding='utf-8')
        raw = re.sub(r'\$\{(\w+)\}', lambda m: os.environ.get(m.group(1), ''), raw)
        data = yaml.safe_load(raw)
        return BotConfig(**{k: v for k, v in data.items() if k in BotConfig.__dataclass_fields__})
    
    def _start_channel(self, runtime: BotRuntime):
        channel_name = runtime.config.channel
        channel = self.global_providers  # providers registry 也扫描 channels
        # 在 channels/ 目录中查找
        ch_registry = Registry("channels")
        ch_registry.discover(str(self.root / 'channels'), 'channels')
        ch_instance = ch_registry.get_instance(channel_name)
        if not ch_instance:
            raise ValueError(f"Channel [{channel_name}] 未找到")
        t = threading.Thread(target=ch_instance.start, args=(runtime,),
                            daemon=True, name=f"ch_{runtime.config.name}")
        t.start()
```

### 5.8 `main.py`

```python
"""Agent Hub 统一入口。"""
import sys, threading
from pathlib import Path
from core.bot_loader import BotLoader

def main():
    root = Path(__file__).parent
    loader = BotLoader(root)
    bots = loader.discover_and_load()
    if not bots:
        print("[agent_hub] 没有 enabled 的 Bot")
        sys.exit(1)
    print(f"\n{'='*50}")
    print(f"  agent_hub — {len(bots)} 个Bot运行中")
    for b in bots:
        print(f"  ✅ {b.config.label} ({b.config.name})")
    print(f"{'='*50}\n")
    # 启动所有Channel（主Bot在当前进程，其余走子进程）
    loader.start_channels(bots)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        print("\n[agent_hub] 已关闭")

if __name__ == '__main__':
    main()
```

### 5.9 `run_single_bot.py`（v4.1 新增）

> 子进程入口，由 BotLoader 自动调用，每个Bot独占一个进程和 asyncio event loop。

```python
"""单Bot独立进程启动器。"""
import sys, threading
from pathlib import Path
from core.bot_loader import BotLoader
from core.bot_runtime import BotRuntime

def run_bot(bot_name: str):
    root = Path(__file__).parent
    loader = BotLoader(root)
    config = loader._load_config(root / 'bots' / bot_name / 'bot.yaml')
    runtime = BotRuntime(config, root / 'bots' / bot_name,
        loader.global_tools, loader.global_hooks, loader.global_providers)
    loader._start_channel_inprocess(runtime)
    threading.Event().wait()

if __name__ == '__main__':
    run_bot(sys.argv[1])
```

---

## 6. prompts/registry.yaml 完整示例

```yaml
# bots/investment/prompts/registry.yaml
# Phase 配置注册表 — 所有 Phase 的唯一定义处
# 新增Phase = 加一条 + 对应prompt文件

phases:
  p7:
    key: "p7"
    label: "Phase07 蒸馏"
    prompt_file: "phases/phase07_distill.md"
    triggers: ["蒸馏", "处理纪要"]
    timeout: 300
    output_dir: "知识库/行业"
    needs_confirm: false
    accepts_inline: true

  p5:
    key: "p5"
    label: "Phase05 周报"
    prompt_file: "phases/phase05_weekly_radar.md"
    triggers: ["周报", "雷达", "跑周报"]
    timeout: 600
    output_dir: "研究/周报月报/周度雷达"
    needs_confirm: true

  p2a:
    key: "p2a"
    label: "Phase02A 月报（成长周期型）"
    prompt_file: "phases/phase02a_monthly_growth.md"
    triggers: ["月报A", "月报a"]
    timeout: 600
    output_dir: "研究/周报月报"
    needs_confirm: true

  p2b:
    key: "p2b"
    label: "Phase02B 月报（刚需供需型）"
    prompt_file: "phases/phase02b_monthly_supply.md"
    triggers: ["月报B", "月报b"]
    timeout: 600
    output_dir: "研究/周报月报"
    needs_confirm: true

  p4:
    key: "p4"
    label: "Phase04 滚动更新"
    prompt_file: "phases/phase04_rolling_update.md"
    triggers: ["滚动更新", "差异化更新"]
    timeout: 600
    output_dir: "研究/周报月报"
    needs_confirm: true

  p10:
    key: "p10"
    label: "Phase10 备忘提炼"
    prompt_file: "phases/phase10_memo_digest.md"
    triggers: ["提炼备忘", "消化memo"]
    timeout: 300
    output_dir: "投资哲学/碎片备忘/_Weekly_Digest"
    needs_confirm: true

  p11:
    key: "p11"
    label: "Phase11 公司交流"
    prompt_file: "phases/phase11_company_notes.md"
    triggers: ["交流", "p11"]
    timeout: 600
    output_dir: "知识库/个股"
    needs_confirm: true

  p2pre:
    key: "p2pre"
    label: "初研"
    prompt_file: "phases/phase2pre_initial_research.md"
    triggers: ["初研"]
    timeout: 600
    output_dir: "研究/论点卡"
    needs_confirm: true
```

---

## 7. bot.yaml 配置格式

```yaml
# bots/investment/bot.yaml
name: investment
label: "投研Bot"
enabled: true
description: "AI投研助手：情报蒸馏、知识库管理、Phase调度"
channel: feishu_ws
channel_config:
  app_id: ${FEISHU_INVEST_APP_ID}
  app_secret: ${FEISHU_INVEST_APP_SECRET}
ai_provider: claude_cli
workspace: "/home/zy/桌面/投研工作台"
max_concurrent: 5
default_timeout: 300
global_hooks: [dedup, auth, timer, audit]
```

```yaml
# bots/_template/bot.yaml
name: my_bot
label: "我的Bot"
enabled: false
description: ""
channel: feishu_ws
channel_config:
  app_id: ${FEISHU_MYBOT_APP_ID}
  app_secret: ${FEISHU_MYBOT_APP_SECRET}
ai_provider: claude_cli
workspace: ""
max_concurrent: 3
default_timeout: 300
global_hooks: [dedup, auth, timer, audit]
```

---

## 8. Skill 文件模板 + Skill 调用AI的标准方式

```python
# bots/_template/skills/hello.py
"""示例技能"""
from core.context import Context, ContextStatus, SkillManifest

MANIFEST = SkillManifest(
    name="hello",
    description="测试Bot运行状态",
    triggers=["你好", "ping", "test"],
    version="1.0.0",
    tags=["系统"],
)

def handle(ctx: Context) -> Context:
    ctx.status = ContextStatus.SUCCESS
    ctx.reply_text = f"✅ {ctx.bot_name} Bot 运行正常！"
    return ctx
```

```python
# Skill 中调用 AI 的标准方式（以 kb_query 为例）
def handle(ctx: Context) -> Context:
    from core.executor import get_ai_provider
    
    provider = get_ai_provider(ctx)             # 自动解析应该用哪个AI
    if not provider:
        ctx.status = ContextStatus.ERROR
        ctx.reply_text = "❌ AI模型不可用"
        return ctx
    
    prompt = f"你是投研助手。\n\n问题：{ctx.parsed_args.get('question', '')}"
    result = provider.call_with_retry(           # 带重试的调用
        prompt, timeout=120, cwd=ctx.workspace
    )
    
    ctx.status = ContextStatus.SUCCESS
    ctx.reply_text = result
    return ctx
```

---

## 9. 运行时简明性审查

> **核心问题**：消息从用户到回复，经过了多少步？是否每步都是必要的？

### 9.1 消息处理全链路

```
用户发飞书消息 "心法"
  │
  ├─ Channel: 解析JSON，构建 Context                    [~1ms，必要]
  │
  ├─ Executor Step 1: Router.route()                   [~0.5ms，必要]
  │     └─ 第1层: skill_registry.match_by_trigger("心法")
  │     └─ 命中 framework_view skill (confidence=1.0)
  │     └─ 跳过第2/3层                                  [零token ✅]
  │
  ├─ Executor Step 2: 查找 handler                      [~0.1ms]
  │
  ├─ Executor Step 3: Middleware Before                  [~0.5ms]
  │     └─ dedup: request_id 检查
  │     └─ auth: user_id 白名单
  │     └─ timer: 记录 start_time
  │     └─ audit: 记录日志
  │
  ├─ Executor Step 4: skill.handle(ctx)                  [~5ms，读文件]
  │     └─ framework_view: Path.read_text() → ctx.reply_text
  │     └─ 零AI调用                                     [零token ✅]
  │
  ├─ Executor Step 5: Middleware After                   [~0.5ms]
  │     └─ timer: 计算耗时
  │     └─ audit: 写入 executions.jsonl
  │
  └─ Channel: send_reply → 飞书API                      [~100ms，网络]

总计: ~110ms, 0 token
```

```
用户发飞书消息 "录 某某公司董事长在电话会上说..."
  │
  ├─ Channel: 构建 Context                               [~1ms]
  ├─ Router: match_by_trigger("录") → ingest_record      [~0.5ms, 零token]
  ├─ Middleware Before                                    [~0.5ms]
  ├─ Skill: ingest_record.handle()
  │     ├─ classify_intent: AI判断 p7/p11                [~3s, ~200 token]
  │     ├─ 加载 Phase prompt                              [~1ms]
  │     ├─ AI 执行蒸馏/保真                                [~30s, ~2000 token]
  │     ├─ 解析输出，存入 pending_store                     [~5ms]
  │     └─ 回复预览给用户                                   [~100ms]
  ├─ Middleware After                                     [~0.5ms]
  └─ Channel: send_reply                                  [~100ms]

总计: ~35s, ~2200 token（绝大部分是AI处理本身，框架开销<1%）
```

### 9.2 框架自身开销评估

| 环节 | 开销 | 是否必要 | 可否省略 |
|------|------|---------|---------|
| Context 构建 | <1ms | ✅ 必要 | 否 |
| Router 三层匹配 | <1ms | ✅ 必要（第1层命中则跳过2/3） | 已优化 |
| 4个 Hook 执行 | <1ms | ✅ 必要（去重防重复处理） | 可在 bot.yaml 禁用 |
| Registry 查找 | <0.5ms | ✅ 必要 | 否 |
| audit 写 JSONL | <1ms | 可选 | 可在 bot.yaml 移除 audit |

**结论：框架自身开销 < 5ms，占总处理时间 < 0.01%。不是瓶颈。**

### 9.3 Token 消耗分布

```
         零 Token                  少量 Token              大量 Token
    ┌──────────────┐         ┌──────────────┐        ┌──────────────┐
    │ s, d, h, e   │         │ AI fallback  │        │ 录, 析, 比   │
    │ 心法,焦点,图谱│         │ 路由(~100)   │        │ (~2000/次)   │
    │ 找, memo     │         │              │        │ Phase执行    │
    │ ok, 改, cancel│        │ classify     │        │ (~3000/次)   │
    │ kk, jj, 切   │         │ intent(~200) │        │              │
    └──────────────┘         └──────────────┘        └──────────────┘
      约60%的指令                 约10%                    约30%
```

---

## 10. Token 优化策略

### 10.1 三级 Token 节约机制

**第一级：路由层 — 能不调AI就不调**

```python
# Router 的三层设计就是为了节约 token
# 第1层：关键词精确匹配 → 零token（覆盖约60%指令）
# 第2层：Phase 触发词匹配 → 零token（覆盖约30%指令）
# 第3层：AI fallback → 消耗token（仅约10%的模糊输入才触发）
```

**第二级：Prompt 层 — 传最少的 context**

```python
# 当前问题：bot.py 每次都注入完整 kb_file_tree（随知识库膨胀）
# 改造后：按需注入

def handle(ctx: Context) -> Context:
    question = ctx.parsed_args.get('question', '')
    
    # 只在需要时才构建目录树，且只取相关子目录
    if '行业' in question or '情报' in question:
        tree = _get_subtree(ctx.workspace, '知识库/行业')  # 只取行业子树
    elif '个股' in question:
        tree = _get_subtree(ctx.workspace, '知识库/个股')
    else:
        tree = _get_tree_summary(ctx.workspace)  # 只给目录名，不展开文件

    prompt = f"知识库结构：\n{tree}\n\n问题：{question}"
    # ...
```

**第三级：对话层 — 历史压缩**

```python
# bots/investment/skills/dialog_mode.py
from collections import deque

MAX_ROUNDS = 10       # 保留最近10轮
COMPRESS_AFTER = 5    # 超过5轮后压缩前5轮为摘要

def _build_dialog_prompt(history: deque, new_msg: str, ctx: Context) -> str:
    """构建带压缩的对话 prompt。"""
    if len(history) <= COMPRESS_AFTER:
        # 短对话：原文拼接
        lines = [f"{'用户' if h['role']=='user' else '助手'}：{h['text'][:100]}"
                 for h in history]
        return f"对话历史：\n{'chr(10)'.join(lines)}\n\n用户最新消息：{new_msg}"
    else:
        # 长对话：前半段用AI生成100字摘要，后半段保留原文
        # 摘要只生成一次，缓存到 metadata 中
        summary = ctx.metadata.get('_dialog_summary', '')
        if not summary:
            old_part = list(history)[:COMPRESS_AFTER]
            old_text = '\n'.join(f"{h['role']}：{h['text'][:80]}" for h in old_part)
            from core.executor import get_ai_provider
            provider = get_ai_provider(ctx)
            summary = provider.call(
                f"用100字总结这段对话的要点：\n{old_text}",
                timeout=30, cwd=ctx.workspace
            )
            ctx.metadata['_dialog_summary'] = summary
        
        recent = list(history)[COMPRESS_AFTER:]
        recent_lines = [f"{'用户' if h['role']=='user' else '助手'}：{h['text'][:100]}"
                       for h in recent]
        return (f"对话摘要：{summary}\n\n"
                f"最近对话：\n{'chr(10)'.join(recent_lines)}\n\n"
                f"用户最新消息：{new_msg}")
```

### 10.2 AI 输出 JSON Schema 标准化

```python
# 旧方式（不稳定，需兜底解析）
FILE_PATH: 知识库/行业/2026-04-13_情报卡_原奶.md
---
date: 2026-04-13
...

# 新方式：在 prompt 尾部注入 JSON 输出指令
NO_WRITE_INSTRUCTION = """
【输出格式要求】
请严格按以下JSON格式输出，不要输出任何JSON之外的文字：
```json
{
  "file_path": "知识库/行业/YYYY-MM-DD_情报卡_品种_主题.md",
  "content": "--- \\ndate: ...\\n---\\n# 标题\\n正文..."
}
```
"""

# 解析（稳定，无兜底）
import json, re
def parse_ai_output(raw: str) -> tuple[str, str]:
    """从 AI 输出中提取 JSON 格式的 file_path 和 content。"""
    # 尝试提取 ```json ``` 块
    m = re.search(r'```json\s*\n(.*?)\n```', raw, re.DOTALL)
    text = m.group(1) if m else raw
    try:
        data = json.loads(text)
        return data.get('file_path', ''), data.get('content', '')
    except json.JSONDecodeError:
        # 降级：兼容旧的 FILE_PATH: 格式
        lines = raw.strip().split('\n')
        for i, line in enumerate(lines):
            if line.strip().upper().startswith('FILE_PATH:'):
                return line.split(':', 1)[1].strip(), '\n'.join(lines[i+1:]).strip()
        return '', raw  # 最终兜底
```

---

## 11. 知识沉淀机制

### 11.1 设计原则

```
自动沉淀 = 每次执行自动写日志（零人工）
手动沉淀 = 用户发一条"沉淀"指令，把成功经验固化为模板（一键，不增加工作量）
```

### 11.2 自动沉淀：执行日志（hooks/audit.py）

```python
# hooks/audit.py
"""操作审计 Hook — 每次执行自动写入 JSONL 日志。"""
import json
from pathlib import Path
from core.context import Context, HookManifest, ExecutionRecord

MANIFEST = HookManifest(name="audit", phase="after", priority=20)

def handle(ctx: Context) -> None:
    """执行完成后自动写入日志（零人工）。"""
    runtime = ctx.metadata.get('_runtime')
    if not runtime:
        return
    
    log_file = runtime.bot_dir / 'memory' / 'store' / 'executions.jsonl'
    log_file.parent.mkdir(parents=True, exist_ok=True)
    
    record = ExecutionRecord(
        request_id=ctx.request_id,
        timestamp=ctx.created_at,
        bot_name=ctx.bot_name,
        user_id=ctx.user_id,
        channel=ctx.channel,
        matched_skill=ctx.matched_skill,
        ai_provider=ctx.ai_provider,
        status=ctx.status.value,
        execution_time_ms=ctx.execution_time_ms,
        input_summary=ctx.raw_text[:100],
        output_path=ctx.output_path,
        error_message=ctx.error_message,
    )
    
    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(json.dumps(record.__dict__, ensure_ascii=False) + '\n')
```

每次执行完成后：
- ✅ **零操作**自动写入 `bots/xxx/memory/store/executions.jsonl`
- 包含：谁、什么时候、做了什么、成功/失败、耗时、AI模型

### 11.3 手动沉淀：一键固化（Skill: crystallize）

```python
# bots/investment/skills/crystallize.py
"""手动沉淀技能 — 用户发"沉淀"查看最近成功记录并标记为模板。"""
import json
from pathlib import Path
from core.context import Context, ContextStatus, SkillManifest

MANIFEST = SkillManifest(
    name="crystallize",
    description="查看执行统计或将成功经验标记为可复用模板",
    triggers=["沉淀", "统计", "复盘"],
    tags=["系统", "沉淀"],
)


def handle(ctx: Context) -> Context:
    """
    "统计" → 展示7天执行统计
    "沉淀" → 展示最近10条成功记录，用户回复序号可标记为模板
    """
    runtime = ctx.metadata.get('_runtime')
    log_file = runtime.bot_dir / 'memory' / 'store' / 'executions.jsonl'
    
    if not log_file.exists():
        ctx.status = ContextStatus.SUCCESS
        ctx.reply_text = "暂无执行记录"
        return ctx
    
    records = _load_recent(log_file, days=7)
    subcmd = ctx.parsed_args.get('content', '').strip()
    
    if ctx.raw_text.startswith('统计'):
        # ── 统计模式 ──
        total = len(records)
        success = sum(1 for r in records if r['status'] == 'success')
        by_skill = {}
        for r in records:
            s = r['matched_skill']
            by_skill[s] = by_skill.get(s, 0) + 1
        
        lines = [f"📊 近7天执行统计（{total}次，成功率 {success/total*100:.0f}%）\n"]
        for skill, count in sorted(by_skill.items(), key=lambda x: -x[1]):
            lines.append(f"  {skill}: {count}次")
        
        ctx.reply_text = '\n'.join(lines)
    
    else:
        # ── 沉淀模式：展示最近成功记录 ──
        success_records = [r for r in records if r['status'] == 'success'][-10:]
        if not success_records:
            ctx.reply_text = "近7天无成功记录"
        else:
            lines = ["🧊 最近成功执行（可标记为模板）：\n"]
            for i, r in enumerate(success_records):
                lines.append(f"  [{i+1}] {r['matched_skill']} | {r['input_summary'][:40]} | {r['timestamp'][:10]}")
            lines.append("\n💡 回复序号可将该记录标记为常用模式（如：沉淀 3）")
            
            # 如果用户带了序号，标记为模板
            if subcmd.isdigit():
                idx = int(subcmd) - 1
                if 0 <= idx < len(success_records):
                    _mark_as_template(runtime, success_records[idx])
                    ctx.reply_text = f"✅ 已标记为常用模式：{success_records[idx]['matched_skill']}"
                else:
                    ctx.reply_text = "序号超出范围"
            else:
                ctx.reply_text = '\n'.join(lines)
    
    ctx.status = ContextStatus.SUCCESS
    return ctx


def _load_recent(log_file, days=7):
    from datetime import datetime, timedelta
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    records = []
    with open(log_file, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                r = json.loads(line)
                if r.get('timestamp', '') >= cutoff:
                    records.append(r)
    return records


def _mark_as_template(runtime, record):
    """将记录写入 templates.jsonl 供未来 AI 检索。"""
    tpl_file = runtime.bot_dir / 'memory' / 'store' / 'templates.jsonl'
    record['_is_template'] = True
    record['_marked_at'] = __import__('datetime').datetime.now().isoformat()
    with open(tpl_file, 'a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False) + '\n')
```

### 11.4 沉淀使用流程（用户视角）

```
用户："统计"
Bot ：📊 近7天执行统计（47次，成功率 89%）
       ingest_url: 15次
       phase_execute: 12次
       framework_view: 8次
       ...

用户："沉淀"
Bot ：🧊 最近成功执行（可标记为模板）：
       [1] ingest_url | https://mp.weixin.qq.com/... | 2026-04-12
       [2] phase_execute | p7 蒸馏 华新水泥 | 2026-04-11
       [3] kb_query | 铜的供需格局 | 2026-04-10
       💡 回复序号可将该记录标记为常用模式（如：沉淀 3）

用户："沉淀 2"
Bot ：✅ 已标记为常用模式：phase_execute
```

**工作量 = 0**（自动记录）+ **一条消息**（手动标记）。

---

## 12. 分阶段改造路线图

### Phase 1：地基 + 多Bot骨架（7个工作日）

**目标**：框架核心就位，_template Bot 通过飞书 ping 通。

| # | 任务 | 产出文件 | 依赖 |
|---|------|---------|------|
| 1.1 | 创建项目骨架目录（core/ channels/ providers/ tools/ hooks/ bots/ config/） | 所有 `__init__.py` | 无 |
| 1.2 | `core/context.py` | 上文 §2 完整代码 | 无 |
| 1.3 | `core/registry.py` | 上文 §5.1 | 1.2 |
| 1.4 | `core/middleware.py` | 上文 §5.2 | 1.2 |
| 1.5 | `core/pending_store.py` | 上文 §5.3 | 1.2 |
| 1.6 | `core/router.py` | 上文 §5.5 | 1.2, 1.3 |
| 1.7 | `core/executor.py` | 上文 §5.4 | 1.2-1.6 |
| 1.8 | `core/bot_runtime.py` | 上文 §5.6 | 1.2-1.7 |
| 1.9 | `core/bot_loader.py` | 上文 §5.7 | 1.8 |
| 1.10 | `channels/base.py` | 上文 §3.1 | 1.2 |
| 1.11 | `channels/feishu_ws.py` | 上文 §3.2 | 1.10 |
| 1.12 | `providers/base.py` | 上文 §4.1 | 无 |
| 1.13 | `providers/claude_cli.py` | 上文 §4.2 | 1.12 |
| 1.14 | `tools/feishu_message.py` — 从 `shared/feishu_utils.py` L29-56 提取 | | 无 |
| 1.15 | `tools/feishu_file.py` — 从 `shared/feishu_utils.py` L59-128 提取 | | 无 |
| 1.16 | `tools/feishu_token.py` — 从 `shared/feishu_utils.py` L9-26 提取 | | 无 |
| 1.17 | 4个全局 Hook：`hooks/{dedup,auth,timer,audit}.py` | | 1.2 |
| 1.18 | `bots/_template/` 模板目录 + hello.py | | 1.2 |
| 1.19 | `config/settings.py` + `config/global.yaml` | | 无 |
| 1.20 | `main.py` | 上文 §5.8 | 1.9 |
| 1.21 | `requirements.txt`（pyyaml, requests, lark-oapi） | | 无 |
| 1.22 | ⭐ 验证：复制_template为test_bot，飞书发"ping"收到回复 | | 全部 |

**验收**：`python main.py` 启动成功 + 飞书 "ping" 收到回复 + audit.py 写入日志

---

### Phase 2：投研Bot 迁移（10个工作日）

**目标**：全部投研功能迁移到 `bots/investment/`。

**迁移映射表**：

| 新文件 | 源位置 (`bot_claude/bot.py` 行号) |
|--------|-------------------------------|
| `tools/file_read.py` | 新建 |
| `tools/file_write.py` | L949-961 + `memo_handler.py` L40-55 |
| `tools/search_grep.py` | L398-433 |
| `tools/wechat_fetch.py` | `投研工作台/_系统/tools/wechat_parser.py` |
| `providers/deepseek_api.py` | `bot_gemini/bot.py` 中 API 调用逻辑 |
| `skills/system_status.py` | L221-307 |
| `skills/memo_save.py` | L1071-1083 + `memo_handler.py` |
| `skills/framework_view.py` | L313-355 |
| `skills/framework_update.py` | L673-723 |
| `skills/kb_query.py` | L839-898 |
| `skills/dialog_mode.py` | L1057-1065 + L1189-1208 |
| `skills/ingest_record.py` | L521-667 |
| `skills/ingest_url.py` | L458-518 |
| `skills/phase_execute.py` | L729-803 |
| `skills/crystallize.py` | 新建（沉淀功能） |
| `prompts/registry.yaml` | L83-123 五个字典合并 |
| `prompts/system/*.md` | L41-77 + L449-453 |
| `prompts/phases/*.md` | 从投研工作台复制 |

**逐日计划**：D1 tools → D2 prompts配置 → D3 简单skills → D4-D5 中等skills → D6-D7 复杂skills → D8 集成 → D9 对比测试 → D10 切换

---

### Phase 3：扩展（5个工作日）

| 任务 | 说明 |
|------|------|
| T3.1 | `bots/gemini/` 迁入 |
| T3.2 | `bots/daily_report/` 迁入 |
| T3.3 | `bots/health/` 占位骨架 |
| T3.4 | `channels/cli.py` 调试渠道 |
| T3.5 | README.md 新Bot创建指南 |
| T3.6 | 考虑重命名 `investment_system` → `agent_hub` |

---

## 13. 风险与注意事项

### 13.1 渐进式迁移

```
Phase 1: 在 investment_system/ 内新建子目录开发，旧 bot.py 不动
Phase 2: 新架构用测试飞书应用验证，正式切换选周末，保留 bot_legacy.py 可回滚
Phase 3: 纯新增，不改已迁移代码
```

### 13.2 易踩的坑

| 坑 | 规避 |
|---|------|
| pending_store 跨 skill | 同一Bot内所有skill共享pending_store |
| Claude CLI cwd | Provider.call() 传 ctx.workspace |
| 全局 dict 残留 | 全部迁入 BotRuntime 实例变量 |
| tool 有状态 | Provider 无状态，进程管理移入 skill |
| 单Bot失败拖垮全部 | bot_loader try/except 跳过失败Bot |
| channel 找不到 | bot_loader 报错但不退出 |
| provider 找不到 | executor 降级到 Bot 默认 provider |

### 13.3 扩展性

| 规模 | 状态 |
|------|------|
| 3 bots, 30 skills | ✅ 完全可行 |
| 10 bots, 100 skills | ✅ 可行 |
| 新增 Channel | 实现 ChannelBase 的2个方法 |
| 新增 Provider | 实现 ProviderBase 的2个方法 |
| 天花板 ~200 skills | 超过需向量检索 |
