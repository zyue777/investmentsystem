"""消息去重 Hook — 防止同一条飞书消息重复处理。"""
import threading
from core.context import Context, ContextStatus, HookManifest

MANIFEST = HookManifest(name="dedup", phase="before", priority=10)

_processed_ids: set = set()
_lock = threading.Lock()
_MAX_SIZE = 2000


def handle(ctx: Context) -> Context:
    """检查 request_id 是否已处理过。"""
    msg_id = ctx.request_id
    if not msg_id:
        return ctx
    with _lock:
        if msg_id in _processed_ids:
            ctx.status = ContextStatus.CANCELLED
            ctx.reply_text = ""  # 静默丢弃重复消息
            return ctx
        _processed_ids.add(msg_id)
        if len(_processed_ids) > _MAX_SIZE:
            _processed_ids.clear()
            _processed_ids.add(msg_id)
    return ctx
