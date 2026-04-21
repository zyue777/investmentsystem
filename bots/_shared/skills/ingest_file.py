"""文件录入 — 接收 Word/PDF 文件，自动提取文本，分类为 P7(蒸馏) 或 P11(公司情报)，
直接写入知识库并回复结果（无需用户二次确认，与 ingest_url 动线一致）。

触发方式：
  - 用户直接发送 Word/PDF 文件到飞书（Channel 自动识别并注入 _file_info）

流程：
  文件下载 → 文本提取 → AI 分类(P7/P11) → AI 处理 → 直接写入 → 回复结果
"""
import os
import re
from datetime import datetime
from pathlib import Path
from core.context import Context, ContextStatus, SkillManifest

MANIFEST = SkillManifest(
    name="ingest_file",
    description="文件录入（Word/PDF自动识别并分类为蒸馏P7或公司情报P11，直接入库）",
    triggers=[],        # 无文字触发词，由 Channel 在检测到文件消息时直接注入 matched_skill
    version="2.0.0",
    tags=["录入", "文件", "AI"],
    priority=15,
)

NO_WRITE = "⚠️ 注意：请直接返回最终内容结果，无需尝试执行任何写入操作。切勿在输出中包含任何关于系统环境、模式、限制的警告语或多余的说明文字。\n\n"
REPLY_MAX_LEN = 2800


def handle(ctx: Context) -> Context:
    """入口：文件元信息在 ctx.metadata['_file_info'] 中。"""
    file_info = ctx.metadata.get('_file_info')

    if not file_info:
        ctx.reply_text = "⚠️ 请直接发送 Word 或 PDF 文件"
        ctx.status = ContextStatus.ERROR
        return ctx

    return _handle_file(ctx, file_info)


def _handle_file(ctx: Context, file_info: dict) -> Context:
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
    phase_choice = _classify_intent(text_content, provider, ws, runtime)
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
    full_path = Path(ws) / '知识库' / file_path

    # 直接写入（与 ingest_url 一致，无需二次确认）
    try:
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(card_content, encoding='utf-8')
    except Exception as e:
        ctx.reply_text = f"❌ 写入失败：{e}"
        ctx.status = ContextStatus.ERROR
        return ctx

    try:
        rel = full_path.relative_to(ws)
    except ValueError:
        rel = full_path

    card_preview = (card_content if len(card_content) <= REPLY_MAX_LEN
                    else card_content[:REPLY_MAX_LEN] + "\n\n…（内容过长）")
    ctx.reply_text = (f"✅ 已入库\n"
                      f"📎 文件：{file_name}\n"
                      f"🏷️ 类型：{phase_label}\n"
                      f"📁 {rel}\n\n"
                      f"📋 情报卡内容：\n\n{card_preview}")
    ctx.output_path = str(full_path)
    ctx.status = ContextStatus.SUCCESS
    return ctx


def _classify_intent(content: str, provider, ws: str, runtime=None) -> str:
    """分类文件内容为 P7(研报蒸馏) 或 P11(公司情报)。
    路径解析优先级：runtime.bot_dir > fallback prompt。
    """
    system_prompt = ''
    # 从当前 bot 的 prompts 目录加载（而非写死 _shared 的相对路径）
    if runtime and hasattr(runtime, 'bot_dir'):
        prompt_file = runtime.bot_dir / 'prompts' / 'system' / 'classify_intent.md'
        if prompt_file.exists():
            system_prompt = prompt_file.read_text(encoding='utf-8')
    if not system_prompt:
        system_prompt = (
            "判断这份文字的类型，只输出 p7 或 p11，不要有其他内容。\n"
            "p11：公司业绩说明会、投资者交流会、管理层访谈、路演纪要等【客观公司业绩交流汇报】 → 输出 p11\n"
            "p7：研究报告、行业分析、券商研报、宏观策略报告、专家电话会纪要等【主观研判/外部观点】 → 输出 p7\n"
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
        stem = Path(source_name).stem if source_name else '未命名'
        file_path = f"{today}_{stem}.md"
        content = raw
    # ── 路径净化（防御 AI 输出格式污染） ──
    file_path = _sanitize_path(file_path, today, source_name)
    return file_path, content


def _sanitize_path(file_path: str, today: str, source_name: str) -> str:
    """清理 AI 输出的文件路径，防止路径腐化。
    防御场景：反引号包裹、_Inbox/前缀、.pdf后缀、..路径逃逸、引号包裹。
    """
    # 1. 去除反引号、引号等格式字符
    file_path = file_path.strip('`\'\"')
    # 2. 去除已知的错误前缀（AI 从 prompt 上下文中误抄的路径）
    for prefix in ['知识库/行业/', '知识库/个股/', '知识库/',
                   '_Inbox/_Processed_Archive/', '_Inbox/', 'Inbox/']:
        if file_path.startswith(prefix):
            file_path = file_path[len(prefix):]
    # 3. 防止路径逃逸
    file_path = file_path.replace('..', '').lstrip('/')
    # 4. 强制 .md 后缀（AI 有时保留原始 .pdf 后缀）
    if not file_path.endswith('.md'):
        file_path = re.sub(r'\.(pdf|docx?|txt)$', '.md', file_path, flags=re.IGNORECASE)
        if not file_path.endswith('.md'):
            file_path += '.md'
    # 5. 归入正确的子目录
    if not file_path.startswith(('行业/', '个股/')):
        file_path = '行业/' + file_path
    # 6. 最终安全检查：路径中不应包含特殊字符
    file_path = file_path.replace('`', '').replace('"', '').replace("'", '')
    return file_path
