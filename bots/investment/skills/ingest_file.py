"""文件录入 — 接收 Word/PDF 文件，自动提取文本，分类为 P7(蒸馏) 或 P11(公司情报)，
预览后用户确认写入知识库。

触发方式：
  - 用户直接发送 Word/PDF 文件到飞书（Channel 自动识别并注入 _file_info）
  - 发 "文件录入" + 文件（配合 Channel 扩展）

流程：
  文件下载 → 文本提取 → AI 分类(P7/P11) → AI 处理 → 预览 → ok 确认写入
"""
import os
import tempfile
from datetime import datetime
from pathlib import Path
from core.context import Context, ContextStatus, SkillManifest

MANIFEST = SkillManifest(
    name="ingest_file",
    description="文件录入（Word/PDF自动识别并分类为蒸馏P7或公司情报P11）",
    triggers=[],        # 无文字触发词，由 Channel 在检测到文件消息时直接注入 matched_skill
    version="1.0.0",
    tags=["录入", "文件", "AI"],
    priority=15,
)

NO_WRITE = "⚠️ 重要：本次执行请勿直接写入或创建任何文件。只在 stdout 输出内容。\n\n"


def handle(ctx: Context) -> Context:
    """入口：文件元信息在 ctx.metadata['_file_info'] 中。"""
    file_info = ctx.metadata.get('_file_info')
    pending_store = ctx.metadata.get('_pending_store')

    # ── ok/确认 → 写入（复用 ingest_record 的确认流程）──────────────────────
    text = ctx.raw_text.strip()
    if text.lower() in ('ok', '确认'):
        return _handle_confirm(ctx, pending_store)
    if text.startswith('改 '):
        return _handle_modify(ctx, text[2:].strip(), pending_store)

    # ── 处理文件 ──────────────────────────────────────────────────────────────
    if not file_info:
        ctx.reply_text = "⚠️ 请直接发送 Word 或 PDF 文件"
        ctx.status = ContextStatus.ERROR
        return ctx

    return _handle_file(ctx, file_info, pending_store)


def _handle_file(ctx: Context, file_info: dict, pending_store) -> Context:
    from core.executor import get_ai_provider
    from tools.feishu_token import get_token
    from tools.feishu_file_download import download_file, extract_text_from_file

    file_name = file_info.get('file_name', '未知文件')
    file_key  = file_info.get('file_key', '')
    message_id = file_info.get('message_id', '')
    ws = ctx.workspace

    # 下载文件
    runtime = ctx.metadata.get('_runtime')
    cfg = runtime.config.channel_config if runtime else {}
    token = get_token(cfg.get('app_id', ctx.metadata.get('app_id', '')),
                      cfg.get('app_secret', ctx.metadata.get('app_secret', '')))
    if not token:
        ctx.reply_text = "❌ 获取飞书 token 失败，无法下载文件"
        ctx.status = ContextStatus.ERROR
        return ctx

    tmp_path = None
    try:
        tmp_path = download_file(token, message_id, file_key, file_name)
        text_content = extract_text_from_file(tmp_path)
    except Exception as e:
        ctx.reply_text = f"❌ 文件处理失败：{e}\n支持格式：.docx / .pdf / .txt / .md"
        ctx.status = ContextStatus.ERROR
        return ctx
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

    if not text_content or len(text_content.strip()) < 100:
        ctx.reply_text = (f"⚠️ [{file_name}] 提取的文字太少（{len(text_content)}字），"
                          f"可能是扫描版PDF或加密文档")
        ctx.status = ContextStatus.ERROR
        return ctx

    provider = get_ai_provider(ctx)
    if not provider:
        ctx.reply_text = "❌ AI模型不可用"
        ctx.status = ContextStatus.ERROR
        return ctx

    # AI 分类（P7 研报蒸馏 / P11 公司情报）
    phase_choice = _classify_intent(text_content, provider, ws)
    phase_label = '研报蒸馏（P7）' if phase_choice == 'p7' else '公司交流情报卡（P11）'

    # 加载 Phase prompt
    phase_configs = ctx.metadata.get('_phase_configs', {})
    p_cfg = phase_configs.get(phase_choice, {})
    p_prompt = _load_phase_prompt(runtime, p_cfg) if p_cfg else ''

    prompt = (NO_WRITE +
              (f"{p_prompt}\n\n" if p_prompt else '') +
              f"以下是从文件【{file_name}】中提取的文字内容，请按照上面的要求处理。\n"
              f"第一行严格输出 FILE_PATH: [路径]\n\n"
              f"原文内容：\n{text_content[:20000]}")

    raw = provider.call_with_retry(prompt, timeout=600, cwd=ws)
    if raw.startswith('❌') or raw.startswith('⏸️'):
        ctx.reply_text = raw
        ctx.status = ContextStatus.ERROR
        return ctx

    today = datetime.now().strftime('%Y-%m-%d')
    file_path, card_content = _parse_output(raw, today, file_name)

    if pending_store:
        pending_store.set(ctx.user_id, {
            'path': file_path, 'content': card_content,
            'original': text_content, 'kb': ws, 'type': 'new',
        })

    preview = (f"📎 文件：{file_name}\n"
               f"🏷️ 自动识别：{phase_label}\n"
               f"📁 将存入：知识库/{file_path}\n"
               f"{'─' * 32}\n"
               f"{card_content[:2400]}\n"
               f"{'─' * 32}\n"
               f"回复 ok 确认写入 | 改 [意见] 修改 | /cancel 取消")
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
    full_path = Path(ws) / '知识库' / pending['path']
    try:
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(pending['content'], encoding='utf-8')
    except Exception as e:
        ctx.reply_text = f"❌ 写入失败：{e}"
        ctx.status = ContextStatus.ERROR
        return ctx

    from tools.file_write import git_commit
    git_commit(str(full_path), ws, f"file_ingest: {full_path.name}")
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
              f"请按照修改意见重新输出完整情报卡，第一行保持 FILE_PATH: 格式。")

    raw = provider.call_with_retry(prompt, timeout=120, cwd=ctx.workspace)
    if raw.startswith('❌') or raw.startswith('⏸️'):
        ctx.reply_text = raw
        ctx.status = ContextStatus.ERROR
        return ctx

    today = datetime.now().strftime('%Y-%m-%d')
    file_path, card_content = _parse_output(raw, today, '')
    pending_store.set(ctx.user_id, {
        'path': file_path, 'content': card_content,
        'original': pending.get('original', ''), 'kb': pending.get('kb', ctx.workspace), 'type': 'new',
    })
    ctx.reply_text = (f"📋 修改后预览\n📁 知识库/{file_path}\n"
                      f"{'─' * 32}\n{card_content[:2400]}\n{'─' * 32}\n"
                      f"回复 ok 确认 | 改 [意见] 继续修改")
    ctx.status = ContextStatus.PENDING
    return ctx


def _classify_intent(content: str, provider, ws: str) -> str:
    prompt_file = Path(__file__).parent.parent / 'prompts' / 'system' / 'classify_intent.md'
    if prompt_file.exists():
        system_prompt = prompt_file.read_text(encoding='utf-8')
    else:
        system_prompt = (
            "判断这份文字的类型，只输出 p7 或 p11，不要有其他内容。\n"
            "p11：公司业绩说明会、投资者交流会、管理层访谈、路演纪要 → 输出 p11\n"
            "p7：研究报告、行业分析、券商研报、宏观策略报告 → 输出 p7\n"
            "不确定时默认 p7"
        )
    prompt = NO_WRITE + system_prompt + f"\n\n待分类内容前段：\n{content[:2000]}"
    res = provider.call(prompt, timeout=60, cwd=ws).strip().lower()
    return 'p11' if 'p11' in res else 'p7'


def _load_phase_prompt(runtime, phase_cfg: dict) -> str:
    if not runtime or not phase_cfg:
        return ''
    prompt_file = runtime.bot_dir / 'prompts' / phase_cfg.get('prompt_file', '')
    if prompt_file.exists():
        return prompt_file.read_text(encoding='utf-8')
    return ''


def _parse_output(raw: str, today: str, source_name: str) -> tuple:
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
        # 用文件名作为兜底
        stem = Path(source_name).stem if source_name else '未命名'
        file_path = f"{today}_{stem}.md"
        content = raw
    # 规范路径前缀
    for prefix in ['知识库/行业/', '知识库/个股/']:
        file_path = file_path.replace(prefix, '')
    if not file_path.startswith(('行业/', '个股/')):
        file_path = '行业/' + file_path
    return file_path, content
