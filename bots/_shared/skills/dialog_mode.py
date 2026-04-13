"""连续对话模式 — kk 开启，jj 结束。"""
from collections import deque
from core.context import Context, ContextStatus, SkillManifest

MANIFEST = SkillManifest(
    name="dialog_mode",
    description="连续对话模式（kk开/jj关）",
    triggers=["kk", "开始对话", "jj", "结束对话"],
    version="1.0.0",
    tags=["对话"],
    priority=25,
)

MAX_ROUNDS = 10
COMPRESS_AFTER = 5


def handle(ctx: Context) -> Context:
    text = ctx.raw_text.strip()
    dialog_mode = ctx.metadata.get('_dialog_mode', {})
    dialog_history = ctx.metadata.get('_dialog_history', {})

    if text in ('kk', '开始对话'):
        dialog_mode[ctx.user_id] = True
        dialog_history[ctx.user_id] = deque(maxlen=MAX_ROUNDS)
        ctx.reply_text = "✅ 连续对话模式\n后续消息无需前缀\n发 jj 或 /clear 退出"
        ctx.status = ContextStatus.SUCCESS
        return ctx

    if text in ('jj', '结束对话'):
        dialog_mode.pop(ctx.user_id, None)
        dialog_history.pop(ctx.user_id, None)
        ctx.reply_text = "🗑️ 对话历史已清空"
        ctx.status = ContextStatus.SUCCESS
        return ctx

    # 不应该到这里，但做个兜底
    ctx.reply_text = "💡 发送 kk 开始对话，jj 结束对话"
    ctx.status = ContextStatus.SUCCESS
    return ctx
