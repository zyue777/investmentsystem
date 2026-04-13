"""Agent Hub 统一入口。"""
import sys, threading, signal
from pathlib import Path

# 确保项目根目录在 sys.path 中
_ROOT = str(Path(__file__).parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

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

    # 启动所有 Channel（主Bot在当前进程，其余走子进程）
    loader.start_channels(bots)

    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        print("\n[agent_hub] 已关闭")

if __name__ == '__main__':
    main()
