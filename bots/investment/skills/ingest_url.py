"""URL投喂 — 发送裸URL自动抓取+分类+蒸馏+入库。"""
import re
from datetime import datetime
from pathlib import Path
from core.context import Context, ContextStatus, SkillManifest

MANIFEST = SkillManifest(
    name="ingest_url",
    description="URL自动抓取蒸馏入库",
    triggers=[],  # 由 Router 的 URL 检测触发，不需要文本触发词
    version="1.0.0",
    tags=["录入", "AI"],
    priority=20,
)

NO_WRITE = "⚠️ 重要：本次执行请勿直接写入或创建任何文件。只在 stdout 输出内容。\n\n"
REPLY_MAX_LEN = 2800


def handle(ctx: Context) -> Context:
    from core.executor import get_ai_provider

    url = ctx.parsed_args.get('url', '')
    if not url:
        ctx.reply_text = "⚠️ 请附上文章 URL"
        ctx.status = ContextStatus.ERROR
        return ctx

    ws = ctx.workspace
    provider = get_ai_provider(ctx)
    if not provider:
        ctx.reply_text = "❌ AI模型不可用"
        ctx.status = ContextStatus.ERROR
        return ctx

    # 抓取文章
    from tools.wechat_fetch import fetch_article
    result = fetch_article(url)

    if 'error' in result:
        ctx.reply_text = f"❌ 文章抓取失败：{result['error']}"
        ctx.status = ContextStatus.ERROR
        return ctx

    raw_content = result['content']
    title = result.get('title', '未命名')

    # 智能路由
    phase_choice = _classify_intent(raw_content, provider, ws)

    # 加载 Phase prompt
    runtime = ctx.metadata.get('_runtime')
    phase_configs = runtime._phase_configs if runtime else {}
    p_cfg = phase_configs.get(phase_choice, {})
    p_prompt = ''
    if p_cfg:
        prompt_file = runtime.bot_dir / 'prompts' / p_cfg.get('prompt_file', '')
        if prompt_file.exists():
            p_prompt = prompt_file.read_text(encoding='utf-8')

    # 构建 prompt
    prompt = (NO_WRITE +
              (f"{p_prompt}\n\n" if p_prompt else "") +
              f"请将以下原始文章依照上面要求的结构进行处理。\n"
              f"第一行输出必须严格遵循指定的 FILE_PATH: 格式落盘，后续空行接内容。\n\n"
              f"原文：\n{raw_content[:20000]}")

    raw = provider.call_with_retry(prompt, timeout=600, cwd=ws)
    if raw.startswith('❌') or raw.startswith('⏸️'):
        ctx.reply_text = raw
        ctx.status = ContextStatus.ERROR
        return ctx

    today = datetime.now().strftime('%Y-%m-%d')
    file_path, content = _parse_output(raw, today)
    full_path = Path(ws) / '知识库' / file_path

    try:
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding='utf-8')
    except Exception as e:
        ctx.reply_text = f"❌ 写入失败：{e}"
        ctx.status = ContextStatus.ERROR
        return ctx

    try:
        rel = full_path.relative_to(ws)
    except ValueError:
        rel = full_path

    from tools.file_write import git_commit
    git_commit(str(full_path), ws, f"url_ingest: {full_path.name}")

    card_preview = content if len(content) <= REPLY_MAX_LEN else content[:REPLY_MAX_LEN] + "\n\n…（内容过长）"
    ctx.reply_text = f"✅ 已入库: {rel}\n📎 原文: {title}\n\n📋 情报卡内容：\n\n{card_preview}"
    ctx.output_path = str(full_path)
    ctx.status = ContextStatus.SUCCESS
    return ctx


def _classify_intent(content: str, provider, ws: str) -> str:
    prompt_file = Path(__file__).parent.parent / 'prompts' / 'system' / 'classify_intent.md'
    if prompt_file.exists():
        system_prompt = prompt_file.read_text(encoding='utf-8')
    else:
        system_prompt = "判断p7或p11，只输出一个。"
    prompt = NO_WRITE + system_prompt + f"\n\n待分类正文前段：\n{content[:2000]}"
    res = provider.call(prompt, timeout=60, cwd=ws).strip().lower()
    return 'p11' if 'p11' in res else 'p7'


def _parse_output(raw: str, today: str) -> tuple[str, str]:
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
    file_path = file_path.replace('知识库/行业/', '').replace('知识库/个股/', '')
    if not file_path.startswith('行业/') and not file_path.startswith('个股/'):
        file_path = '行业/' + file_path
    return file_path, content
