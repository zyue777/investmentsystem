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
