"""手动录入 — 智能判定p7/p11 → AI生成 → 预览 → 等确认。"""
import re
from datetime import datetime
from pathlib import Path
from core.context import Context, ContextStatus, SkillManifest

MANIFEST = SkillManifest(
    name="ingest_record",
    description="手动录入情报（含确认流程）",
    triggers=["录 ", "ok", "确认", "改 "],
    version="1.0.0",
    tags=["录入", "AI"],
    priority=15,
)

NO_WRITE = "⚠️ 注意：请直接返回最终内容结果，无需尝试执行任何写入操作。切勿在输出中包含任何关于系统环境、模式、限制的警告语或多余的说明文字。\n\n"
REPLY_MAX_LEN = 2800


def handle(ctx: Context) -> Context:
    text = ctx.raw_text.strip()
    pending_store = ctx.metadata.get('_pending_store')

    # ── ok/确认 → 写入 ──
    if text.lower() in ('ok', '确认'):
        return _handle_confirm(ctx, pending_store)

    # ── 改 [意见] → 修改 ──
    if text.startswith('改 '):
        return _handle_modify(ctx, text[2:].strip(), pending_store)

    # ── 录 [内容] → 生成 ──
    content = ctx.parsed_args.get('content', '')
    if not content:
        ctx.reply_text = "⚠️ 请在 录 后附上内容"
        ctx.status = ContextStatus.ERROR
        return ctx

    return _handle_record(ctx, content, pending_store)


def _handle_record(ctx: Context, content: str, pending_store) -> Context:
    from core.executor import get_ai_provider

    ws = ctx.workspace
    provider = get_ai_provider(ctx)
    if not provider:
        ctx.reply_text = "❌ AI模型不可用"
        ctx.status = ContextStatus.ERROR
        return ctx

    # 智能前置路由
    phase_choice = _classify_intent(content, provider, ws)

    # 加载 Phase prompt
    runtime = ctx.metadata.get('_runtime')
    phase_configs = runtime._phase_configs if runtime else {}
    p_cfg = phase_configs.get(phase_choice, {})
    p_prompt = _load_phase_prompt(runtime, p_cfg) if p_cfg else ''

    prompt = (NO_WRITE +
              f"{p_prompt}\n\n" if p_prompt else NO_WRITE)
    prompt += (f"请将以下原始信息依照上面要求的结构进行处理。\n"
               f"第一行严格输出 FILE_PATH: [路径]：\n{content[:20000]}")

    raw = provider.call_with_retry(prompt, timeout=600, cwd=ws)
    if raw.startswith('❌') or raw.startswith('⏸️'):
        ctx.reply_text = raw
        ctx.status = ContextStatus.ERROR
        return ctx

    today = datetime.now().strftime('%Y-%m-%d')
    file_path, card_content = _parse_output(raw, today)

    if pending_store:
        pending_store.set(ctx.user_id, {
            'path': file_path, 'content': card_content,
            'original': content, 'kb': ws, 'type': 'new',
            '_skill': 'ingest_record',
        })

    preview = (f"📋 预览（回复 ok 确认写入）\n"
               f"📁 知识库/{file_path}\n"
               f"{'─' * 30}\n"
               f"{card_content[:2400]}\n"
               f"{'─' * 30}\n"
               f"回复 ok 确认 | 改 [意见] 修改 | /cancel 取消")
    ctx.reply_text = preview
    ctx.status = ContextStatus.PENDING
    return ctx


def _handle_confirm(ctx: Context, pending_store) -> Context:
    if not pending_store:
        ctx.reply_text = "⚠️ 没有待确认的内容"
        ctx.status = ContextStatus.SUCCESS
        return ctx

    pending = pending_store.pop(ctx.user_id)
    if not pending:
        ctx.reply_text = "⚠️ 没有待确认的内容"
        ctx.status = ContextStatus.SUCCESS
        return ctx

    ws = pending['kb']
    ptype = pending.get('type', 'new')

    if ptype == 'new':
        full_path = Path(ws) / '知识库' / pending['path']
    elif ptype == 'phase':
        full_path = Path(ws) / pending['path']
    else:  # 'update'
        full_path = Path(pending['path'])

    try:
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(pending['content'], encoding='utf-8')
    except Exception as e:
        ctx.reply_text = f"❌ 写入失败：{e}"
        ctx.status = ContextStatus.ERROR
        return ctx

    try:
        rel = full_path.relative_to(ws)
    except ValueError:
        rel = full_path

    ctx.reply_text = f"✅ 已入库\n📁 {rel}"
    ctx.output_path = str(full_path)
    ctx.status = ContextStatus.SUCCESS
    return ctx


def _handle_modify(ctx: Context, modification: str, pending_store) -> Context:
    from core.executor import get_ai_provider

    if not pending_store:
        ctx.reply_text = "⚠️ 没有待修改的内容"
        ctx.status = ContextStatus.SUCCESS
        return ctx

    pending = pending_store.get(ctx.user_id)
    if not pending:
        ctx.reply_text = "⚠️ 没有待修改的内容"
        ctx.status = ContextStatus.SUCCESS
        return ctx

    provider = get_ai_provider(ctx)
    if not provider:
        ctx.reply_text = "❌ AI模型不可用"
        ctx.status = ContextStatus.ERROR
        return ctx

    prompt = (NO_WRITE +
              f"以下是上一次生成的情报卡：\n{pending['content']}\n\n"
              f"用户修改意见：{modification}\n\n"
              f"请按照修改意见重新输出完整情报卡。\n"
              f"第一行保持 FILE_PATH: 格式。")

    raw = provider.call_with_retry(prompt, timeout=120, cwd=ctx.workspace)
    if raw.startswith('❌') or raw.startswith('⏸️'):
        ctx.reply_text = raw
        ctx.status = ContextStatus.ERROR
        return ctx

    today = datetime.now().strftime('%Y-%m-%d')
    file_path, card_content = _parse_output(raw, today)

    pending_store.set(ctx.user_id, {
        'path': file_path, 'content': card_content,
        'original': pending.get('original', ''),
        'kb': pending.get('kb', ctx.workspace), 'type': pending.get('type', 'new'),
    })

    preview = (f"📋 修改后预览\n📁 知识库/{file_path}\n"
               f"{'─' * 30}\n{card_content[:2400]}\n{'─' * 30}\n"
               f"回复 ok 确认 | 改 [意见] 继续修改")
    ctx.reply_text = preview
    ctx.status = ContextStatus.PENDING
    return ctx


def _classify_intent(content: str, provider, ws: str) -> str:
    """判断使用 p7 还是 p11。"""
    prompt_file = Path(__file__).parent.parent / 'prompts' / 'system' / 'classify_intent.md'
    if prompt_file.exists():
        system_prompt = prompt_file.read_text(encoding='utf-8')
    else:
        system_prompt = ("判断文本类别：公司业绩交流→p11，研报/行业分析→p7。"
                         "只输出 p11 或 p7。")
    prompt = NO_WRITE + system_prompt + f"\n\n待分类正文前段：\n{content[:2000]}"
    res = provider.call(prompt, timeout=60, cwd=ws).strip().lower()
    return 'p11' if 'p11' in res else 'p7'


def _load_phase_prompt(runtime, phase_cfg: dict) -> str:
    """加载 Phase prompt 文件内容。"""
    if not runtime or not phase_cfg:
        return ''
    prompt_file = runtime.bot_dir / 'prompts' / phase_cfg.get('prompt_file', '')
    if prompt_file.exists():
        return prompt_file.read_text(encoding='utf-8')
    return ''


def _parse_output(raw: str, today: str) -> tuple[str, str]:
    """解析 AI 输出为 (相对路径, 内容)。"""
    # 尝试 JSON 格式
    try:
        import json
        m = re.search(r'```json\s*\n(.*?)\n```', raw, re.DOTALL)
        if m:
            data = json.loads(m.group(1))
            return data.get('file_path', ''), data.get('content', '')
    except Exception:
        pass

    # FILE_PATH 格式
    lines = raw.strip().split('\n')
    file_path = ''
    content_start = 0
    for i, line in enumerate(lines):
        if line.strip().upper().startswith('FILE_PATH:'):
            file_path = line.split(':', 1)[1].strip()
            content_start = i + 1
            break
    while content_start < len(lines) and not lines[content_start].strip():
        content_start += 1
    content = '\n'.join(lines[content_start:]) if content_start < len(lines) else raw

    if not file_path:
        file_path = f"{today}_情报卡_未分类.md"
        content = raw

    # 规范路径
    file_path = file_path.replace('知识库/行业/', '').replace('知识库/个股/', '')
    if not file_path.startswith('行业/') and not file_path.startswith('个股/'):
        file_path = '行业/' + file_path

    return file_path, content
