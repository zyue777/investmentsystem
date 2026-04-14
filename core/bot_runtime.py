"""BotRuntime — 单个Bot的隔离运行时容器。
📝 文档引用：CLAUDE.md「Skills 共享机制」/ docs/00_架构总览.md
⚠️ _load_skills() 支持 _shared + Bot 专属两级加载，修改加载顺序会影响覆盖行为。
"""
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
    # 文件消息类型 → Skill 名称映射（TD-04 修复：配置驱动，不在 Channel 层硬编码）
    # 在 bot.yaml 中可覆盖；新增文件类型只需改配置，无需动代码
    file_skill_routes: dict = field(default_factory=lambda: {
        'file': 'ingest_file',   # .docx / .pdf / .txt 等通用文件
        'doc':  'ingest_file',   # 飞书在线文档
    })
    # 启动时发送指令菜单的用户 open_id 列表（为空则不发）
    startup_notify_users: list = field(default_factory=list)



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
        self.router = Router(self.skill_registry, self._phase_configs, self.pending_store)

    def _load_skills(self):
        # 1. 先加载共享 Skills（bots/_shared/skills/）
        shared = self.bot_dir.parent / '_shared' / 'skills'
        if shared.exists():
            self.skill_registry.discover(str(shared), 'bots._shared.skills')
        # 2. 再加载 Bot 专属 Skills（同名会覆盖共享的，实现差异化）
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
                # 支持 EXTRA_HOOKS 模式（一个模块注册多个阶段，如 timer 的 before+after）
                mod = item.get('module')
                if mod:
                    extra_hooks = getattr(mod, 'EXTRA_HOOKS', [])
                    for extra_m in extra_hooks:
                        extra_fn = getattr(mod, 'get_extra_handler', lambda n: None)(extra_m.name)
                        if extra_fn:
                            self.pipeline.register_hook(extra_m.name, extra_m.phase, extra_fn, extra_m.priority)
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
