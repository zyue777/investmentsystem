"""知识库问答 — 问/析/比/总 四种模式。"""
import re
from pathlib import Path
from core.context import Context, ContextStatus, SkillManifest

MANIFEST = SkillManifest(
    name="kb_query",
    description="AI知识库问答（问/析/比/总）",
    triggers=["问 ", "析 ", "比 ", "总 "],
    version="1.0.0",
    tags=["AI", "问答"],
    priority=50,
)

REPLY_MAX_LEN = 2800
NO_WRITE = "⚠️ 重要：本次执行请勿直接写入或创建任何文件。只在 stdout 输出内容。\n\n"


def handle(ctx: Context) -> Context:
    from core.executor import get_ai_provider

    text = ctx.raw_text.strip()
    ws = ctx.workspace
    question = ctx.parsed_args.get('content', '') or ctx.parsed_args.get('question', '') or text

    # 解析指令类型
    cmd = ''
    for prefix in ['问', '析', '比', '总']:
        if text.startswith(prefix + ' ') or text.startswith(prefix + '\n'):
            cmd = prefix
            question = text[2:].strip()
            break

    prompt = _build_prompt(cmd, question, ws)

    provider = get_ai_provider(ctx)
    if not provider:
        ctx.reply_text = "❌ AI模型不可用"
        ctx.status = ContextStatus.ERROR
        return ctx

    raw = provider.call_with_retry(prompt, timeout=300, cwd=ws)

    # 保存最新结果
    _save_latest(raw, ws)

    ctx.reply_text = raw
    ctx.ai_raw_output = raw
    ctx.status = ContextStatus.SUCCESS
    return ctx


def _build_prompt(cmd: str, content: str, ws: str) -> str:
    if cmd == '问':
        tree = _get_tree_summary(ws)
        return (NO_WRITE + f"知识库结构：\n{tree}\n\n"
                f"请基于知识库回答：\n{content}")

    elif cmd == '析':
        parts = content.split(None, 1)
        if len(parts) == 2:
            industry, question = parts
        else:
            industry, question = content, '当前周期位置与反转条件分析'
        dossier = _load_dossier(ws, industry)
        return (NO_WRITE + f"目标行业：{industry}\n"
                f"底稿：\n{dossier[:3000]}\n\n"
                f"分析问题：{question}")

    elif cmd == '比':
        parts = content.split()
        if len(parts) < 2:
            return f"请提供两个行业名称进行比较。输入：{content}"
        a, b = parts[0], parts[1]
        da = _load_dossier(ws, a)
        db = _load_dossier(ws, b)
        return (NO_WRITE + f"行业A({a})底稿：\n{da[:2500]}\n\n"
                f"行业B({b})底稿：\n{db[:2500]}\n\n"
                f"请对两者做横向对比分析。")

    elif cmd == '总':
        tree = _get_tree_summary(ws)
        return (NO_WRITE + f"知识库结构：\n{tree}\n\n"
                f"请汇总主题'{content}'下所有相关文件要点。")

    else:
        tree = _get_tree_summary(ws)
        return (NO_WRITE + f"知识库结构：\n{tree}\n\n"
                f"请回答：\n{content}")


def _get_tree_summary(ws: str) -> str:
    """只给目录名+文件数，不展开全部文件（Token优化）。"""
    kb = Path(ws)
    if not kb.exists():
        return f"⚠️ 目录不存在: {ws}"
    lines = [f"📁 {kb.name}/"]
    for d in sorted(kb.iterdir()):
        if d.name.startswith('.') or d.name.startswith('_'):
            continue
        if d.is_dir():
            count = sum(1 for _ in d.rglob('*.md'))
            lines.append(f"  📂 {d.name}/ ({count} 文件)")
    return '\n'.join(lines)


def _load_dossier(ws: str, industry: str) -> str:
    cards_dir = Path(ws) / '研究' / '论点卡'
    if not cards_dir.exists():
        return ""
    matches = [f for f in cards_dir.glob('*.md') if industry in f.stem and '模板' not in f.stem]
    if matches:
        return matches[0].read_text(encoding='utf-8')
    return ""


def _save_latest(content: str, ws: str):
    try:
        target = Path(ws) / '_Inbox' / 'latest_result.md'
        target.parent.mkdir(parents=True, exist_ok=True)
        from datetime import datetime
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        target.write_text(f"# 最新结果（{ts}）\n\n{content}\n", encoding='utf-8')
    except Exception as e:
        print(f"[kb_query] 保存结果失败: {e}")
