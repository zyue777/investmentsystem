"""Bot 发现、加载、启动。"""
import os, re, yaml, threading, subprocess, sys
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
                runtimes.append(runtime)
                print(f"[loader] ✅ {config.label}（{runtime.skill_registry.count()} skills）")
            except Exception as e:
                # 单个Bot失败不影响其他Bot
                print(f"[loader] ❌ {bot_dir.name} 失败: {e}")
        return runtimes

    def start_channels(self, runtimes: list[BotRuntime]):
        """启动所有Bot的Channel。
        
        策略：第一个Bot在当前进程内启动（主Channel），
        其余Bot各自用独立子进程启动（避免 asyncio event loop 冲突）。
        """
        if not runtimes:
            return

        # 非主Bot：用子进程启动
        for rt in runtimes[1:]:
            self._start_channel_subprocess(rt)

        # 主Bot：在当前进程启动（阻塞）
        self._start_channel_inprocess(runtimes[0])

    def _start_channel_inprocess(self, runtime: BotRuntime):
        """在当前进程中启动Channel（阻塞）。"""
        ch_registry = Registry("channels")
        ch_registry.discover(str(self.root / 'channels'), 'channels')
        ch_instance = ch_registry.get_instance(runtime.config.channel)
        if not ch_instance:
            raise ValueError(f"Channel [{runtime.config.channel}] 未找到")
        t = threading.Thread(target=ch_instance.start, args=(runtime,),
                            daemon=True, name=f"ch_{runtime.config.name}")
        t.start()

    def _start_channel_subprocess(self, runtime: BotRuntime):
        """用独立子进程启动Channel（避免 event loop 共用）。"""
        bot_name = runtime.config.name
        proc = subprocess.Popen(
            [sys.executable, str(self.root / 'run_single_bot.py'), bot_name],
            cwd=str(self.root),
            env=os.environ.copy(),
        )
        print(f"[loader] 子进程启动 {bot_name} (PID={proc.pid})")

    def _load_config(self, path: Path) -> BotConfig:
        raw = path.read_text(encoding='utf-8')
        raw = re.sub(r'\$\{(\w+)\}', lambda m: os.environ.get(m.group(1), ''), raw)
        data = yaml.safe_load(raw)
        # 环境变量替换后 enabled 可能是空字符串，统一标准化为 bool
        if 'enabled' in data and not isinstance(data['enabled'], bool):
            v = str(data['enabled']).strip().lower()
            data['enabled'] = v in ('true', '1', 'yes')
        return BotConfig(**{k: v for k, v in data.items() if k in BotConfig.__dataclass_fields__})

