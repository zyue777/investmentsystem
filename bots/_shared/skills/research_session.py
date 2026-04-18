"""研究模式 Skill — 联网+知识库多轮研究对话，支持归档为情报卡。

触发方式：
  - 「研究 xxx」→ 开启研究模式
  - Session 激活时所有消息 → Router 第0.5层自动拦截到此
  - 「归档」→ AI 整理为情报卡 → 写入知识库 → 清空 Session
  - 「clear」/「jj」→ 清空 Session，不保存

对话模式（用户指挥）：
  - 「请联网 xxx」→ 联网搜索 + 历史上下文 → AI 回答
  - 「结合知识库 xxx」→ 知识库检索 + 历史上下文 → AI 回答
  - 其他文字 → 仅历史上下文 → AI 纯推理
"""
import re
from datetime import datetime
from pathlib import Path
from core.context import Context, ContextStatus, SkillManifest

MANIFEST = SkillManifest(
    name="research_session",
    description="联网+知识库多轮研究对话（研究/归档/clear）",
    triggers=["研究 ", "请联网研究", "联网研究"],
    version="1.0.0",
    tags=["AI", "研究", "联网", "记忆"],
    priority=20,
)

# 退出指令集合
_EXIT_CMDS = {'归档'}
_CLEAR_CMDS = {'clear', 'jj', '结束对话'}

# 联网/知识库检测前缀（研究模式内部使用）
_WEB_PREFIXES = ['请联网研究', '请联网', '联网研究', '联网']
_KB_PREFIXES = ['结合知识库', '知识库']

# 开启研究模式的前缀（会自动提取主题并开启）
_OPEN_PREFIXES = ['请联网研究', '联网研究', '研究 ']

# 反幻觉系统提示
_SYSTEM_PROMPT = (
    "你是一名专业的投资研究助手，正在协助用户进行深度研究。\n"
    "铁律：\n"
    "1. 只使用下方提供的「联网搜索结果」和「知识库资料」中的信息回答。\n"
    "2. 如果提供的资料不足，必须明确说明，绝对不要编造数据。\n"
    "3. 回答要有理有据，结构清晰，有数据就列表或制表。\n"
    "4. 全是干货，不要废话套话。\n"
    "5. 如果使用了联网搜索结果，在末尾标注「📡 部分信息来源于联网搜索」。\n\n"
)

# 归档整理提示
_ARCHIVE_PROMPT = (
    "你是一名投资研究助手。以下是一段完整的研究讨论记录。\n\n"
    "## 任务\n"
    "将所有讨论内容整理为一张**研究情报卡**。\n\n"
    "## 整理要求\n"
    "1. **按逻辑重组**：不要按对话顺序排列，要按主题/论点归类。"
    "不同轮次中展开的同一话题必须合并到同一章节。\n"
    "2. **全是干货**：保留所有论点、论据、关键数据。删除寒暄、重复、过渡语。\n"
    "3. **有表格就制表**：涉及数据对比、指标罗列的内容用表格呈现。\n"
    "4. **行文清晰有层次**：论点→论据→数据→判断，层层递进。\n"
    "5. **数据标注来源和时间**。\n\n"
    "## 输出格式（严格遵守）\n\n"
    "第一行输出 FILE_PATH: [路径]，格式为 行业/YYYY-MM-DD_[主题关键词].md 或 个股/YYYY-MM-DD_[股票名].md\n\n"
    "正文严格按以下结构（直接输出 Markdown，不要用代码块包裹）：\n\n"
    "```\n"
    "---\n"
    "date: {date}\n"
    "type: 研究记录\n"
    "status: 活跃\n"
    "importance: 一般\n"
    "tags:\n"
    "  - [细分行业/品种标签，如：原奶、铜、宏观等]\n"
    "  - 研究记录\n"
    "---\n"
    "# [以核心论点生成标题] ({date})\n\n"
    "## 🧊 核心论点与论据\n"
    "（按逻辑分节，每节一个论点及其支撑论据和数据）\n\n"
    "## 📊 关键数据盘点\n"
    "（表格化，标注来源和时间）\n\n"
    "## 🎯 跟踪锚点\n"
    "（需后续验证的指标/事件，表格：核算事项 | 最晚证实时间 | 若成真的影响）\n\n"
    "## 📎 参考链接\n"
    "（汇总所有引用的网页链接，表格：# | 标题 | 链接）\n"
    "```\n\n"
)


def _parse_open_command(text: str) -> tuple[str, bool]:
    """解析开启研究模式的指令。

    返回 (主题, 是否需要首轮联网)。
    支持：
      - '研究 铜的供需格局' → ('铜的供需格局', False)
      - '请联网研究铜的供需格局' → ('铜的供需格局', True)
      - '联网研究铜的供需格局' → ('铜的供需格局', True)
      - '请联网研究当前铜的供需情况' → ('当前铜的供需情况', True)
    """
    for prefix in ['请联网研究', '联网研究']:
        if text.startswith(prefix):
            topic = text[len(prefix):].strip()
            return topic, True
    if text.startswith('研究 '):
        topic = text[3:].strip()
        return topic, False
    return '', False


def handle(ctx: Context) -> Context:
    """研究模式主入口。"""
    from tools.session_memory import (
        create_session, get_active_session, get_history_as_prompt,
        append_turn, get_full_session, get_all_urls, clear_session,
    )

    text = ctx.raw_text.strip()
    session = get_active_session(ctx.user_id)

    # ── 1. 开启研究模式 ──
    if not session:
        topic, need_web = _parse_open_command(text)
        if topic:
            create_session(ctx.user_id, topic, ctx.bot_name)
            # 重新获取刚创建的 session
            session = get_active_session(ctx.user_id)
            if need_web:
                # 用户说"请联网研究xxx"→ 自动执行首轮联网搜索
                ctx = _do_research_turn(ctx, session, session['bot_name'],
                                        f"请联网研究{topic}")
                # 在回答前加入研究模式提示
                if ctx.reply_text and not ctx.reply_text.startswith('❌'):
                    ctx.reply_text = (
                        f"🔬 已进入研究模式：{topic}\n"
                        f"（归档 = 保存退出 | clear = 清空退出）\n"
                        f"━━━━━━━━━━━━━━━━━\n\n"
                        + ctx.reply_text
                    )
                return ctx
            else:
                ctx.reply_text = (
                    f"🔬 已进入研究模式：{topic}\n"
                    f"━━━━━━━━━━━━━━━━━\n"
                    f"后续消息自动保持上下文\n"
                    f"💡 用法：\n"
                    f"• 直接提问 → 纯推理\n"
                    f"• 「请联网 xxx」→ 联网搜索后回答\n"
                    f"• 「结合知识库 xxx」→ 检索知识库后回答\n"
                    f"• 归档 → 整理为情报卡存入知识库\n"
                    f"• clear → 清空退出"
                )
                ctx.status = ContextStatus.SUCCESS
                return ctx
        elif not topic:
            ctx.reply_text = "⚠️ 请在「研究」后附上主题，如：研究 原奶行业周期"
            ctx.status = ContextStatus.SUCCESS
            return ctx

    # 如果仍没有活跃 Session（不应该到这里），兜底
    if not session:
        ctx.reply_text = "💡 发送「研究 [主题]」开启研究模式"
        ctx.status = ContextStatus.SUCCESS
        return ctx

    bot_name = session['bot_name']

    # ── 2. 归档 ──
    if text in _EXIT_CMDS:
        return _do_archive(ctx, session, bot_name)

    # ── 3. 清空退出 ──
    if text.lower() in _CLEAR_CMDS:
        clear_session(ctx.user_id, bot_name)
        ctx.reply_text = "🗑️ 研究模式已退出，对话已清空"
        ctx.status = ContextStatus.SUCCESS
        return ctx

    # ── 4. 继续对话（核心） ──
    return _do_research_turn(ctx, session, bot_name, text)


def _do_research_turn(ctx: Context, session: dict,
                      bot_name: str, text: str) -> Context:
    """执行一轮研究对话：判断模式 → 搜索 → 构建 prompt → AI → 存储。"""
    from core.executor import get_ai_provider
    from tools.session_memory import get_history_as_prompt, append_turn

    topic = session['topic']
    ws = ctx.workspace

    # ── 判断本轮模式 ──
    use_web = False
    use_kb = False
    question = text

    for prefix in _WEB_PREFIXES:
        if text.startswith(prefix):
            use_web = True
            question = text[len(prefix):].strip() or topic
            break

    for prefix in _KB_PREFIXES:
        if text.startswith(prefix):
            use_kb = True
            question = text[len(prefix):].strip() or topic
            break

    # "综合分析" 自动开启双模式
    if '综合' in text and ('分析' in text or '研究' in text):
        use_web = True
        use_kb = True

    # ── 执行搜索（零 Token） ──
    web_context = ''
    web_urls = []
    kb_context = ''

    if use_web:
        web_context, web_urls = _search_web(question)

    if use_kb:
        kb_context = _search_kb_smart(question, topic, ws)

    # ── 构建 prompt ──
    history = get_history_as_prompt(ctx.user_id, bot_name)
    prompt = _build_turn_prompt(topic, question, history,
                                web_context, kb_context, ws)

    # ── 调用 AI ──
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

    # ── 存储本轮 ──
    append_turn(
        user_id=ctx.user_id,
        bot_name=bot_name,
        user_input=text,
        ai_response=raw,
        web_urls=web_urls if web_urls else None,
    )

    ctx.reply_text = raw
    ctx.ai_raw_output = raw
    ctx.status = ContextStatus.SUCCESS
    return ctx


def _do_archive(ctx: Context, session: dict, bot_name: str) -> Context:
    """归档：AI 整理全部对话为情报卡 → 写入知识库 → 清空 Session。"""
    from core.executor import get_ai_provider
    from tools.session_memory import (
        get_full_session, get_all_urls, clear_session,
    )

    ws = ctx.workspace
    full_session = get_full_session(ctx.user_id, bot_name)
    if not full_session or not full_session.get('turns'):
        clear_session(ctx.user_id, bot_name)
        ctx.reply_text = "⚠️ 无对话内容可归档，已退出研究模式"
        ctx.status = ContextStatus.SUCCESS
        return ctx

    # 构建归档内容
    today = datetime.now().strftime('%Y-%m-%d')
    topic = full_session['topic']

    # 拼接全部对话（全量）
    session_content = _format_session_for_archive(full_session)

    # 收集全部参考链接
    all_urls = get_all_urls(ctx.user_id, bot_name)
    urls_text = _format_urls_for_archive(all_urls)

    # 构建归档 prompt
    prompt = (
        "⚠️ 重要：本次执行请勿直接写入或创建任何文件。只在 stdout 输出内容。\n\n"
        + _ARCHIVE_PROMPT.replace('{date}', today)
        + f"\n## 研究主题\n{topic}\n\n"
        + f"## 原始讨论记录\n{session_content}\n\n"
    )
    if urls_text:
        prompt += f"## 所有引用的参考链接\n{urls_text}\n\n"

    prompt += "请现在输出整理后的情报卡。第一行严格输出 FILE_PATH: [路径]。"

    # 调用 AI 整理
    provider = get_ai_provider(ctx)
    if not provider:
        ctx.reply_text = "❌ AI模型不可用，归档失败"
        ctx.status = ContextStatus.ERROR
        return ctx

    raw = provider.call_with_retry(prompt, timeout=600, cwd=ws)
    if raw.startswith('❌') or raw.startswith('⏸️'):
        ctx.reply_text = f"归档 AI 整理失败：{raw}"
        ctx.status = ContextStatus.ERROR
        return ctx

    # 解析输出路径和内容
    file_path, card_content = _parse_archive_output(raw, today, topic)

    # 写入知识库
    full_path = Path(ws) / '知识库' / file_path
    try:
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(card_content, encoding='utf-8')
    except Exception as e:
        ctx.reply_text = f"❌ 写入失败：{e}"
        ctx.status = ContextStatus.ERROR
        return ctx

    # 清空 Session
    clear_session(ctx.user_id, bot_name)

    try:
        rel = full_path.relative_to(ws)
    except ValueError:
        rel = full_path

    ctx.reply_text = (
        f"✅ 已写入 {rel}\n"
        f"📌 主题：{topic}\n"
        f"对话已清空，已退出研究模式"
    )
    ctx.output_path = str(full_path)
    ctx.status = ContextStatus.SUCCESS
    return ctx


# ── 内部辅助函数 ────────────────────────────────────────────────────


def _build_turn_prompt(topic: str, question: str, history: str,
                       web_context: str, kb_context: str, ws: str) -> str:
    """构建单轮对话的完整 prompt。"""
    parts = [
        "⚠️ 重要：本次执行请勿直接写入或创建任何文件。只在 stdout 输出内容。\n\n",
        _SYSTEM_PROMPT,
        f"当前研究主题：{topic}\n\n",
    ]

    # 历史上下文
    if history:
        parts.append(history)
        parts.append('\n')

    # 联网搜索结果
    if web_context:
        parts.append(web_context)
        parts.append('\n')

    # 知识库资料
    if kb_context:
        parts.append(f"## 📂 知识库资料\n{kb_context}\n\n")

    # 当前问题
    parts.append(f"## 当前问题\n{question}\n")

    return ''.join(parts)


def _search_web(question: str) -> tuple[str, list[dict]]:
    """联网搜索（零 Token）。返回 (格式化文本, 原始结果列表)。"""
    from tools.web_search import search_web, format_results
    results = search_web(question, max_results=5)
    return format_results(results), results


def _search_kb_smart(question: str, topic: str, ws: str) -> str:
    """智能知识库检索 — 代码层控制，零 Token。

    策略：
    1. 用 session 主题词搜索 YAML tags（最精准）
    2. 从用户问题提取关键词补充搜索
    """
    from tools.kb_search import search_kb

    # 策略1：用主题词搜索
    results = search_kb(topic, ws, max_files=3, max_chars_per_file=2000)

    # 策略2：从问题提取额外关键词
    keywords = re.findall(r'[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}', question)
    # 过滤掉与主题重复的词
    extra_kw = [k for k in keywords if k not in topic][:2]
    if extra_kw:
        extra = search_kb(' '.join(extra_kw), ws,
                          max_files=2, max_chars_per_file=1500)
        if extra and extra not in results:
            results += '\n' + extra

    return results


def _format_session_for_archive(session: dict) -> str:
    """将完整 Session 格式化为归档 prompt 输入。"""
    lines = []
    for turn in session.get('turns', []):
        lines.append(f"### 第{turn['turn_id']}轮 ({turn.get('timestamp', '')[:16]})")
        lines.append(f"**用户**: {turn['user_input']}")
        lines.append(f"\n**AI回答**: {turn['ai_response']}")
        if turn.get('web_urls'):
            urls = ', '.join(u.get('url', '') for u in turn['web_urls'])
            lines.append(f"\n参考链接: {urls}")
        lines.append('')
    return '\n'.join(lines)


def _format_urls_for_archive(urls: list[dict]) -> str:
    """将参考链接格式化为 Markdown 表格。"""
    if not urls:
        return ''
    lines = ['| # | 标题 | 链接 |', '|---|------|------|']
    for i, u in enumerate(urls, 1):
        title = u.get('title', '未知')
        url = u.get('url', '')
        lines.append(f"| {i} | {title} | {url} |")
    return '\n'.join(lines)


def _parse_archive_output(raw: str, today: str, topic: str) -> tuple[str, str]:
    """解析 AI 归档输出为 (相对路径, 内容)。"""
    lines = raw.strip().split('\n')
    file_path = ''
    content_start = 0

    for i, line in enumerate(lines):
        if line.strip().upper().startswith('FILE_PATH:'):
            file_path = line.split(':', 1)[1].strip()
            content_start = i + 1
            break

    # 跳过空行
    while content_start < len(lines) and not lines[content_start].strip():
        content_start += 1

    content = '\n'.join(lines[content_start:]) if content_start < len(lines) else raw

    # 兜底路径
    if not file_path:
        # 从主题生成路径
        safe_topic = topic.replace('/', '_').replace(' ', '_')[:30]
        file_path = f"行业/{today}_{safe_topic}.md"

    # 路径净化（AI 可能输出冗余前缀）
    file_path = _sanitize_path(file_path)

    return file_path, content


def _sanitize_path(file_path: str) -> str:
    """净化 AI 输出的文件路径。"""
    # 去掉可能的引号
    file_path = file_path.strip().strip('"').strip("'")
    # 去掉 知识库/ 前缀（写入时会自动加）
    for prefix in ['知识库/', '知识库\\']:
        if file_path.startswith(prefix):
            file_path = file_path[len(prefix):]
    # 确保以 行业/ 或 个股/ 开头
    if not file_path.startswith('行业/') and not file_path.startswith('个股/'):
        file_path = '行业/' + file_path
    # 确保以 .md 结尾
    if not file_path.endswith('.md'):
        file_path += '.md'
    return file_path
