"""通用Phase执行器 — 根据 registry.yaml 配置执行任意 Phase。"""
from datetime import datetime
from pathlib import Path
from core.context import Context, ContextStatus, SkillManifest

MANIFEST = SkillManifest(
    name="phase_execute",
    description="通用Phase执行器（读取registry.yaml配置）",
    triggers=[],  # 由 Router 的 Phase 触发词匹配触发
    version="1.0.0",
    tags=["Phase", "AI"],
    priority=40,
)

NO_WRITE = "⚠️ 注意：请直接返回最终内容结果，无需尝试执行任何写入操作。切勿在输出中包含任何关于系统环境、模式、限制的警告语或多余的说明文字。\n\n"
REPLY_MAX_LEN = 2800


def handle(ctx: Context) -> Context:
    from core.executor import get_ai_provider
    from tools.feishu_file import send_file_to_user
    from tools.feishu_token import get_token

    runtime = ctx.metadata.get('_runtime')
    pending_store = ctx.metadata.get('_pending_store')
    phase_key = ctx.parsed_args.get('phase_key', '') or ctx.phase_key
    extra = ctx.parsed_args.get('extra', '')

    if not runtime or not phase_key:
        ctx.reply_text = "⚠️ Phase 配置缺失"
        ctx.status = ContextStatus.ERROR
        return ctx

    phase_configs = runtime._phase_configs
    p_cfg = phase_configs.get(phase_key, {})
    if not p_cfg:
        ctx.reply_text = f"⚠️ Phase [{phase_key}] 未在 registry.yaml 中定义"
        ctx.status = ContextStatus.ERROR
        return ctx

    ws = ctx.workspace
    label = p_cfg.get('label', phase_key)
    timeout = p_cfg.get('timeout', 300)
    out_dir = p_cfg.get('output_dir', '')
    needs_confirm = p_cfg.get('needs_confirm', True)

    # 加载 Phase prompt
    prompt_file = runtime.bot_dir / 'prompts' / p_cfg.get('prompt_file', '')
    if not prompt_file.exists():
        ctx.reply_text = f"❌ Phase prompt 未找到: {prompt_file.name}"
        ctx.status = ContextStatus.ERROR
        return ctx
    prompt_text = prompt_file.read_text(encoding='utf-8')

    # 构建完整 prompt
    full_prompt = NO_WRITE + prompt_text
    if extra:
        full_prompt += f"\n\n请处理以下用户直接发送的原始内容：\n{extra}"

    # 添加输出路径指令
    today = datetime.now().strftime('%Y-%m-%d')
    if out_dir:
        full_prompt += (f"\n\n输出第一行请标注 FILE_PATH: {out_dir}/"
                        f"{today}_{label}.md")

    provider = get_ai_provider(ctx)
    if not provider:
        ctx.reply_text = "❌ AI模型不可用"
        ctx.status = ContextStatus.ERROR
        return ctx

    raw = provider.call_with_retry(full_prompt, timeout=timeout, cwd=ws)
    if raw.startswith('❌') or raw.startswith('⏸️'):
        ctx.reply_text = raw
        ctx.status = ContextStatus.ERROR
        return ctx

    # 解析输出
    file_path, content = _parse_output(raw, today)
    if not file_path or file_path.endswith('未分类.md'):
        if out_dir:
            file_path = f"{out_dir}/{today}_{label}.md"
        else:
            file_path = f"研究/周报月报/{today}_{label}.md"

    if needs_confirm:
        # 存入 pending 等确认
        if pending_store:
            pending_store.set(ctx.user_id, {
                'path': file_path, 'content': content,
                'original': '', 'kb': ws, 'type': 'phase',
            })

        if len(content) <= REPLY_MAX_LEN:
            preview = (f"📋 {label} 预览\n📁 {file_path}\n"
                       f"{'─' * 30}\n{content}\n{'─' * 30}\n"
                       f"回复 ok 确认写入")
            ctx.reply_text = preview
        else:
            # 长内容发文件
            tmp_path = Path(ws) / '_Inbox' / f'_preview_{phase_key}.md'
            tmp_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path.write_text(content, encoding='utf-8')
            token = get_token(
                ctx.metadata.get('app_id', ''),
                ctx.metadata.get('app_secret', ''))
            if token:
                send_file_to_user(token, ctx.user_id, str(tmp_path))
            ctx.reply_text = (f"📋 {label} 报告预览已发送\n"
                              f"📁 写入路径：{file_path}\n回复 ok 确认写入")
        ctx.status = ContextStatus.PENDING
    else:
        # 不需确认，直接写入
        full_path = Path(ws) / file_path
        try:
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content, encoding='utf-8')
            ctx.reply_text = f"✅ {label} 已完成\n📁 {file_path}"
            ctx.output_path = str(full_path)
        except Exception as e:
            ctx.reply_text = f"❌ 写入失败：{e}"
            ctx.status = ContextStatus.ERROR
            return ctx
        ctx.status = ContextStatus.SUCCESS

    return ctx


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
        file_path = f"{today}_未分类.md"
        content = raw
    return file_path, content
