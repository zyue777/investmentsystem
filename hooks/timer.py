"""执行计时 Hook — before 记录开始时间，after 计算耗时。"""
import time
from core.context import Context, HookManifest

MANIFEST = HookManifest(name="timer", phase="before", priority=30)

_TIMER_KEY = '_timer_start'


def handle(ctx: Context) -> Context:
    """before 阶段：记录开始时间。"""
    ctx.metadata[_TIMER_KEY] = time.time()
    return ctx


# ── After hook：计算耗时并打印 ──
def _handle_after(ctx: Context) -> None:
    """after 阶段：计算耗时。"""
    start = ctx.metadata.get(_TIMER_KEY, 0)
    if start:
        elapsed_ms = int((time.time() - start) * 1000)
        ctx.execution_time_ms = elapsed_ms
        print(f"[timer] {ctx.bot_name}/{ctx.matched_skill} 耗时 {elapsed_ms}ms")


# 额外 hook 注册（一个模块可以注册多个阶段）
EXTRA_HOOKS = [
    HookManifest(name="timer_after", phase="after", priority=30),
]

def get_extra_handler(name: str):
    """返回额外 hook 的 handler 函数。"""
    if name == "timer_after":
        return _handle_after
    return None
