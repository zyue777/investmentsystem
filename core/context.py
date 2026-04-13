"""统一数据结构定义。
📝 文档引用：CLAUDE.md「项目结构」/ docs/03_架构知识卡.md「铁律3 单一写入者」
⚠️ 修改字段会影响所有层。新增字段前请更新 Context docstring 的归属表。
"""
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
    """贯穿所有层的统一对象。

    字段归属（谁设置 → 谁读取）：
    ┌──────────────┬──────────────┬──────────────────────────────────┐
    │ 字段          │ 由谁设置      │ 由谁读取                        │
    ├──────────────┼──────────────┼──────────────────────────────────┤
    │ request_id    │ Channel      │ Hook(dedup), Audit              │
    │ user_id       │ Channel      │ Router, Skill, Hook(auth)       │
    │ raw_text      │ Channel      │ Router, Skill                   │
    │ matched_skill │ Router       │ Executor                        │
    │ parsed_args   │ Router       │ Skill                           │
    │ workspace     │ BotRuntime   │ Skill                           │
    │ ai_provider   │ Executor     │ get_ai_provider()               │
    │ reply_text    │ Skill        │ Channel(发回复)                  │
    │ status        │ Skill/Router │ Channel(决定是否发回复)           │
    │ metadata      │ Executor注入 │ Skill(通过 key 访问运行时资源)    │
    └──────────────┴──────────────┴──────────────────────────────────┘

    ⛔ 不要随意新增字段。新增字段会影响所有层的序列化和日志。
       如需传递 Skill 专属数据，使用 metadata dict。
    """
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
