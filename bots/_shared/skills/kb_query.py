"""知识库问答 — 支持联网搜索 + 知识库搜索 + 四种模式（问/析/比/总）。

触发方式：
  - 「问 xxx」/「析 xxx」/「比 A B」/「总 xxx」→ 传统知识库问答
  - 「请联网回答 xxx」→ 仅联网搜索后回答
  - 「请结合联网与知识库信息回答 xxx」→ 联网 + 知识库搜索后回答
  - 其他文字（兜底）→ 纯 AI 回答

Token 控制策略：
  - 知识库搜索：零 Token（本地 grep + 读文件）
  - 联网搜索：零 Token（DuckDuckGo API）
  - AI 调用：一次性消耗，context 上限 ~7000 字
"""
import re
from pathlib import Path
from core.context import Context, ContextStatus, SkillManifest

MANIFEST = SkillManifest(
    name="kb_query",
    description="AI知识库问答（问/析/比/总/联网搜索）",
    triggers=["问 ", "析 ", "比 ", "总 ",
              "请联网回答", "请结合联网与知识库信息回答"],
    version="2.0.0",
    tags=["AI", "问答", "联网"],
    priority=50,
)

REPLY_MAX_LEN = 2800
NO_WRITE = "⚠️ 重要：本次执行请勿直接写入或创建任何文件。只在 stdout 输出内容。\n\n"

# 联网触发前缀（代码层精确匹配，不消耗 Token）
_WEB_ONLY_PREFIX = "请联网回答"
_WEB_KB_PREFIX = "请结合联网与知识库信息回答"

# 反幻觉 system prompt
_ANTI_HALLUCINATION = (
    "铁律：只使用下方提供的「知识库匹配」和「联网搜索结果」中的信息回答。\n"
    "如果提供的资料不足以回答问题，必须明确说「目前信息不足，无法回答」，"
    "绝对不要编造、推测或补充任何未在资料中出现的数据、事实或结论。\n"
    "如果回答中使用了联网搜索结果，请在末尾标注「📡 以上部分信息来源于联网搜索」。\n\n"
)


def handle(ctx: Context) -> Context:
    from core.executor import get_ai_provider

    text = ctx.raw_text.strip()
    ws = ctx.workspace
    question = ctx.parsed_args.get('content', '') or ctx.parsed_args.get('question', '') or text

    # ── 判断搜索模式 ────────────────────────────────────────────────────────
    use_web = False
    use_kb = False

    if text.startswith(_WEB_KB_PREFIX):
        # 「请结合联网与知识库信息回答 xxx」
        use_web = True
        use_kb = True
        question = text[len(_WEB_KB_PREFIX):].strip()
    elif text.startswith(_WEB_ONLY_PREFIX):
        # 「请联网回答 xxx」
        use_web = True
        use_kb = False
        question = text[len(_WEB_ONLY_PREFIX):].strip()
    else:
        # 传统模式：问/析/比/总 或兜底
        use_kb = True
        use_web = False

    if not question:
        ctx.reply_text = "⚠️ 请在指令后附上问题"
        ctx.status = ContextStatus.ERROR
        return ctx

    # ── 解析传统指令类型 ──────────────────────────────────────────────────────
    cmd = ''
    for prefix in ['问', '析', '比', '总']:
        if text.startswith(prefix + ' ') or text.startswith(prefix + '\n'):
            cmd = prefix
            question = text[2:].strip()
            break

    # ── 执行搜索（零 Token 消耗）────────────────────────────────────────────
    kb_context = ''
    web_context = ''

    if use_kb:
        kb_context = _search_kb(cmd, question, ws)

    if use_web:
        web_context = _search_web(question)

    # ── 构建 prompt ──────────────────────────────────────────────────────────
    prompt = _build_prompt(cmd, question, ws, kb_context, web_context)

    provider = get_ai_provider(ctx)
    if not provider:
        ctx.reply_text = "❌ AI模型不可用"
        ctx.status = ContextStatus.ERROR
        return ctx

    raw = provider.call_with_retry(prompt, timeout=300, cwd=ws)

    _save_latest(raw, ws)

    ctx.reply_text = raw
    ctx.ai_raw_output = raw
    ctx.status = ContextStatus.SUCCESS
    return ctx


def _search_kb(cmd: str, question: str, ws: str) -> str:
    """知识库搜索（零 Token）。根据指令类型选择搜索策略。"""
    if cmd == '析':
        # 析：加载论点卡
        parts = question.split(None, 1)
        industry = parts[0] if parts else question
        return _load_dossier(ws, industry)
    elif cmd == '比':
        # 比：加载两个行业的论点卡
        parts = question.split()
        if len(parts) >= 2:
            da = _load_dossier(ws, parts[0])
            db = _load_dossier(ws, parts[1])
            result = ""
            if da:
                result += f"📄 行业A（{parts[0]}）论点卡：\n{da[:2500]}\n\n"
            if db:
                result += f"📄 行业B（{parts[1]}）论点卡：\n{db[:2500]}"
            return result
        return ""
    else:
        # 问/总/兜底：用关键词搜索知识库
        from tools.kb_search import search_kb
        # 从问题中提取搜索关键词（取前2个有意义的词）
        keywords = re.findall(r'[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}', question)
        if keywords:
            search_query = ' '.join(keywords[:3])
            return search_kb(search_query, ws)
        return ""


def _search_web(question: str) -> str:
    """联网搜索（零 Token）。"""
    from tools.web_search import search_web, format_results
    results = search_web(question, max_results=5)
    return format_results(results)


def _build_prompt(cmd: str, question: str, ws: str,
                  kb_context: str, web_context: str) -> str:
    """构建最终 prompt：反幻觉指令 + 上下文 + 问题。"""
    parts = [NO_WRITE, _ANTI_HALLUCINATION]

    # 知识库上下文
    if kb_context:
        parts.append(kb_context)
        parts.append("")

    # 联网上下文
    if web_context:
        parts.append(web_context)
        parts.append("")

    # 如果没有任何上下文，给目录摘要兜底
    if not kb_context and not web_context:
        tree = _get_tree_summary(ws)
        parts.append(f"知识库结构：\n{tree}\n")

    # 问题指令
    if cmd == '析':
        parts_q = question.split(None, 1)
        industry = parts_q[0] if parts_q else question
        q = parts_q[1] if len(parts_q) > 1 else '当前周期位置与反转条件分析'
        parts.append(f"目标行业：{industry}\n分析问题：{q}")
    elif cmd == '比':
        parts_q = question.split()
        if len(parts_q) >= 2:
            parts.append(f"请对{parts_q[0]}和{parts_q[1]}做横向对比分析。")
        else:
            parts.append(f"请对比分析：{question}")
    elif cmd == '总':
        parts.append(f"请汇总主题「{question}」下所有相关要点。")
    else:
        parts.append(f"请回答：\n{question}")

    return '\n'.join(parts)


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
