"""Agent Hub 统一入口。"""
import sys, threading, signal
from pathlib import Path

# 确保项目根目录在 sys.path 中
_ROOT = str(Path(__file__).parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# 加载 .env 环境变量（PM2 直接启动时不经过 start.sh，必须在此加载）
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / '.env', override=True)

from core.bot_loader import BotLoader


def _clear_stale_sessions(root: Path):
    """启动时清空所有 Bot 的 Session 文件，防止旧研究模式阻塞路由。"""
    cleared = []
    for session_dir in root.glob('bots/*/memory/sessions'):
        for f in session_dir.glob('*.json'):
            f.unlink()
            cleared.append(f.name)
    if cleared:
        print(f"[startup] 已清空旧 Session: {cleared}")


def main():
    root = Path(__file__).parent
    _clear_stale_sessions(root)
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

    # 启动所有 Channel（主Bot在当前进程，其余走子进程）
    loader.start_channels(bots)

    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        print("\n[agent_hub] 已关闭")

if __name__ == '__main__':
    main()
