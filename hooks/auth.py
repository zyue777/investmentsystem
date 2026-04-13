"""用户鉴权 Hook — 可选白名单过滤。"""
import os
from core.context import Context, ContextStatus, HookManifest

MANIFEST = HookManifest(name="auth", phase="before", priority=20)

# 从环境变量读取白名单（逗号分隔的 open_id 列表）
# 为空时不做限制（全部放行）
_WHITELIST_RAW = os.environ.get('AGENT_HUB_WHITELIST', '')
_WHITELIST = set(s.strip() for s in _WHITELIST_RAW.split(',') if s.strip()) if _WHITELIST_RAW else set()


def handle(ctx: Context) -> Context:
    """检查 user_id 是否在白名单中。白名单为空则放行所有用户。"""
    if not _WHITELIST:
        return ctx  # 未配置白名单 → 全部放行
    if ctx.user_id in _WHITELIST:
        return ctx
    ctx.status = ContextStatus.ERROR
    ctx.reply_text = "⚠️ 暂无权限使用此Bot"
    return ctx
