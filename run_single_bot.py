"""单Bot独立进程启动器。由 main.py 的 BotLoader 通过子进程调用。"""
import sys, threading
from pathlib import Path

_ROOT = str(Path(__file__).parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from core.bot_loader import BotLoader
from core.registry import Registry


def run_bot(bot_name: str):
    root = Path(__file__).parent
    loader = BotLoader(root)

    # 只加载指定的 bot
    bot_dir = root / 'bots' / bot_name
    if not bot_dir.exists():
        print(f"[run_single] ❌ Bot '{bot_name}' 不存在")
        sys.exit(1)

    config = loader._load_config(bot_dir / 'bot.yaml')
    if not config.enabled:
        print(f"[run_single] ⚠️ Bot '{bot_name}' 已禁用")
        sys.exit(0)

    from core.bot_runtime import BotRuntime
    runtime = BotRuntime(config, bot_dir,
        loader.global_tools, loader.global_hooks, loader.global_providers)

    print(f"[run_single] 启动 {config.label}（{runtime.skill_registry.count()} skills）")

    # 直接在当前进程启动 Channel（独占 event loop）
    loader._start_channel_inprocess(runtime)

    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        print(f"\n[run_single] {config.label} 已关闭")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法: python run_single_bot.py <bot_name>")
        sys.exit(1)
    run_bot(sys.argv[1])
