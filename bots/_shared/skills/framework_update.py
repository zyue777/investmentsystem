"""认知框架更新 — 焦点+/图谱+/论+ 走确认流程。"""
import re
from pathlib import Path
from core.context import Context, ContextStatus, SkillManifest

MANIFEST = SkillManifest(
    name="framework_update",
    description="更新认知框架（焦点/图谱/论点卡），需AI处理",
    triggers=["焦点+", "图谱+", "论+"],
    version="1.0.0",
    tags=["框架", "AI"],
    priority=30,
)

REPLY_MAX_LEN = 2800
NO_WRITE = "⚠️ 注意：请直接返回最终内容结果，无需尝试执行任何写入操作。切勿在输出中包含任何关于系统环境、模式、限制的警告语或多余的说明文字。\n\n"


def handle(ctx: Context) -> Context:
    from core.executor import get_ai_provider

    text = ctx.raw_text.strip()
    ws = ctx.workspace
    kb = Path(ws)
    pending_store = ctx.metadata.get('_pending_store')

    # 解析指令
    if text.startswith('焦点+'):
        content = text[3:].strip()
        target = kb / '投资哲学' / '当下关注焦点.md'
        if not target.exists():
            ctx.reply_text = "⚠️ 焦点文件不存在"
            ctx.status = ContextStatus.ERROR
            return ctx
        current = target.read_text(encoding='utf-8')
        prompt = (NO_WRITE + f"当前焦点文件：\n{current}\n\n"
                  f"请按用户意见更新，保持格式不变：\n{content}\n"
                  f"输出更新后的完整文件内容。")

    elif text.startswith('图谱+'):
        parts = text[3:].strip().split(None, 1)
        arg = parts[0] if parts else ''
        content = parts[1] if len(parts) > 1 else ''
        target = kb / '行业状态面板.md'
        if not target.exists():
            ctx.reply_text = "⚠️ 行业状态面板不存在"
            ctx.status = ContextStatus.ERROR
            return ctx
        current = target.read_text(encoding='utf-8')
        section = _extract_section(current, arg)
        prompt = (NO_WRITE + f"行业状态面板'{arg}'段落：\n{section}\n\n"
                  f"请按以下新数据更新该段落（只更新关键数据和触发信号字段）：\n{content}\n"
                  f"只输出更新后的该段落。")

    elif text.startswith('论+'):
        parts = text[2:].strip().split(None, 1)
        arg = parts[0] if parts else ''
        content = parts[1] if len(parts) > 1 else ''
        cards_dir = kb / '研究' / '论点卡'
        matches = [f for f in cards_dir.glob('*.md') if arg in f.stem]
        if not matches:
            ctx.reply_text = f"⚠️ 未找到'{arg}'底稿"
            ctx.status = ContextStatus.ERROR
            return ctx
        target = matches[0]
        current = target.read_text(encoding='utf-8')
        prompt = (NO_WRITE + f"当前底稿：\n{current}\n\n"
                  f"请根据新信息更新对应章节：\n{content}\n"
                  f"输出更新后的完整底稿。")
    else:
        ctx.reply_text = "⚠️ 未识别的框架更新指令"
        ctx.status = ContextStatus.ERROR
        return ctx

    # 调用 AI
    provider = get_ai_provider(ctx)
    if not provider:
        ctx.reply_text = "❌ AI模型不可用"
        ctx.status = ContextStatus.ERROR
        return ctx

    raw = provider.call_with_retry(prompt, timeout=300, cwd=ws)
    if raw.startswith('❌') or raw.startswith('⏸️'):
        ctx.reply_text = raw
        ctx.status = ContextStatus.ERROR
        return ctx

    # 存入 pending
    if pending_store:
        pending_store.set(ctx.user_id, {
            'path': str(target), 'content': raw,
            'original': content, 'kb': ws, 'type': 'update',
        })

    preview = (f"📋 更新预览\n📁 {target.name}\n"
               f"{'─' * 30}\n{raw[:2400]}\n{'─' * 30}\n"
               f"回复 ok 确认 | /cancel 取消")
    ctx.reply_text = preview
    ctx.status = ContextStatus.PENDING
    return ctx


def _extract_section(content: str, keyword: str) -> str:
    sections = re.split(r'(?=^## )', content, flags=re.MULTILINE)
    matched = [s for s in sections if keyword in s]
    if matched:
        result = '\n'.join(matched)
        return result[:REPLY_MAX_LEN] if len(result) > REPLY_MAX_LEN else result
    return f"⚠️ 未找到'{keyword}'相关段落"
