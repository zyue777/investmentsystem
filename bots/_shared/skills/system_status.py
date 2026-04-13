"""零Token系统指令集 — s/d/h/hh/e/z/库/心法/焦点/图谱/论/找/切/stop/clear/cancel/redo"""
import re
import subprocess
from pathlib import Path
from core.context import Context, ContextStatus, SkillManifest

MANIFEST = SkillManifest(
    name="system_status",
    description="零Token系统指令（状态/目录/帮助/额度/搜索/框架查看）",
    triggers=["s", "状态", "d", "目录", "h", "帮助", "hh", "更多",
              "e", "额度", "z", "最新", "库",
              "心法", "焦点", "图谱", "论 ", "找 ",
              "/stop", "/clear", "/cancel", "/redo",
              "切 ", "ping", "test", "你好"],
    version="1.0.0",
    tags=["系统"],
    priority=10,
)

REPLY_MAX_LEN = 2800


def handle(ctx: Context) -> Context:
    text = ctx.raw_text.strip()
    ws = ctx.workspace

    # ── ping/hello ──
    if text in ('ping', 'test', '你好'):
        ctx.reply_text = f"✅ {ctx.bot_name} Bot 运行正常！"
        ctx.status = ContextStatus.SUCCESS
        return ctx

    # ── 状态 ──
    if text in ('s', '状态'):
        ctx.reply_text = _cmd_status(ws)
        ctx.status = ContextStatus.SUCCESS
        return ctx

    # ── 目录 ──
    if text in ('d', '目录'):
        ctx.reply_text = _cmd_directory(ws)
        ctx.status = ContextStatus.SUCCESS
        return ctx

    # ── 帮助 ──
    if text in ('h', '帮助'):
        ctx.reply_text = _cmd_help()
        ctx.status = ContextStatus.SUCCESS
        return ctx
    if text in ('hh', '更多'):
        ctx.reply_text = _cmd_help_more()
        ctx.status = ContextStatus.SUCCESS
        return ctx

    # ── 额度 ──
    if text in ('e', '额度'):
        ctx.reply_text = _cmd_quota()
        ctx.status = ContextStatus.SUCCESS
        return ctx

    # ── 最新 ──
    if text in ('z', '最新'):
        ctx.reply_text = _cmd_latest(ws)
        ctx.status = ContextStatus.SUCCESS
        return ctx

    # ── 当前库 ──
    if text == '库':
        ctx.reply_text = f"📁 当前知识库\n📂 路径：{ws}"
        ctx.status = ContextStatus.SUCCESS
        return ctx

    # ── 认知框架查看（零Token） ──
    if text == '心法':
        ctx.reply_text = _read_file(ws, '投资哲学/通用投研大心法.md')
        ctx.status = ContextStatus.SUCCESS
        return ctx
    if text == '焦点':
        ctx.reply_text = _read_file(ws, '投资哲学/当下关注焦点.md')
        ctx.status = ContextStatus.SUCCESS
        return ctx

    # ── 图谱 ──
    if text == '图谱':
        ctx.reply_text = _cmd_atlas(ws)
        ctx.status = ContextStatus.SUCCESS
        return ctx
    if text.startswith('图谱 '):
        ctx.reply_text = _cmd_atlas(ws, text[3:].strip())
        ctx.status = ContextStatus.SUCCESS
        return ctx

    # ── 论 ──
    if text.startswith('论 '):
        ctx.reply_text = _cmd_dossier(ws, text[2:].strip())
        ctx.status = ContextStatus.SUCCESS
        return ctx

    # ── 找 ──
    if text.startswith('找 '):
        from tools.search_grep import search_formatted
        ctx.reply_text = search_formatted(text[2:].strip(), ws)
        ctx.status = ContextStatus.SUCCESS
        return ctx

    # ── 切换KB ──
    if text.startswith('切 '):
        ctx.reply_text = "ℹ️ 当前版本仅支持单知识库模式"
        ctx.status = ContextStatus.SUCCESS
        return ctx

    # ── 控制指令 ──
    if text == '/stop':
        ctx.reply_text = "ℹ️ 当前没有运行中的任务"
        ctx.status = ContextStatus.SUCCESS
        return ctx
    if text == '/clear':
        dialog_mode = ctx.metadata.get('_dialog_mode', {})
        dialog_history = ctx.metadata.get('_dialog_history', {})
        dialog_mode.pop(ctx.user_id, None)
        dialog_history.pop(ctx.user_id, None)
        ctx.reply_text = "🗑️ 对话历史已清空"
        ctx.status = ContextStatus.SUCCESS
        return ctx
    if text == '/cancel':
        pending = ctx.metadata.get('_pending_store')
        if pending:
            removed = pending.pop(ctx.user_id)
            ctx.reply_text = "🗑️ 已取消待确认内容" if removed else "ℹ️ 没有待确认的内容"
        else:
            ctx.reply_text = "ℹ️ 没有待确认的内容"
        ctx.status = ContextStatus.SUCCESS
        return ctx
    if text == '/redo':
        ctx.reply_text = "⚠️ 请先使用 录 指令生成内容"
        ctx.status = ContextStatus.SUCCESS
        return ctx

    # fallback
    ctx.reply_text = "💡 发送 h 查看常用指令"
    ctx.status = ContextStatus.SUCCESS
    return ctx


# ── 内部函数 ──

def _cmd_status(ws: str) -> str:
    fc = sum(1 for _ in Path(ws).rglob('*.md')) if Path(ws).exists() else 0
    lines = [f"✅ 投研Bot V4 运行中", f"📁 知识库：{Path(ws).name} ({fc} 文件)", "", "📊 Claude 额度："]
    try:
        r = subprocess.run(['claude', '/status'], capture_output=True, text=True, timeout=15)
        lines.append((r.stdout + r.stderr).strip() or "（无输出）")
    except Exception as e:
        lines.append(f"⚠️ 查询失败：{e}")
    return '\n'.join(lines)

def _cmd_directory(ws: str) -> str:
    kb = Path(ws)
    if not kb.exists():
        return f"⚠️ 知识库目录不存在: {kb}"
    lines = [f"📁 {kb.name}/"]
    for d in sorted(kb.iterdir()):
        if d.name.startswith('.'):
            continue
        if d.is_dir():
            count = sum(1 for _ in d.rglob('*.md'))
            lines.append(f"  📂 {d.name}/ ({count} 文件)")
        else:
            lines.append(f"  📄 {d.name}")
    return '\n'.join(lines)

def _cmd_quota() -> str:
    try:
        r = subprocess.run(['claude', '/status'], capture_output=True, text=True, timeout=15)
        return f"📊 {(r.stdout + r.stderr).strip() or '（无输出）'}"
    except Exception as e:
        return f"⚠️ 额度查询失败：{e}"

def _cmd_latest(ws: str) -> str:
    for p in [Path(ws) / 'inbox' / 'latest_result.md', Path(ws) / '_Inbox' / 'latest_result.md']:
        if p.exists():
            return p.read_text(encoding='utf-8')[:REPLY_MAX_LEN]
    return "ℹ️ 暂无保存的结果"

def _read_file(ws: str, rel: str) -> str:
    f = Path(ws) / rel
    if f.exists():
        content = f.read_text(encoding='utf-8')
        return content[:REPLY_MAX_LEN] if len(content) > REPLY_MAX_LEN else content
    return "⚠️ 文件不存在"

def _cmd_atlas(ws: str, industry: str = '') -> str:
    f = Path(ws) / '行业状态面板.md'
    if not f.exists():
        return "⚠️ 行业状态面板不存在"
    content = f.read_text(encoding='utf-8')
    if not industry:
        headers = [l for l in content.split('\n') if l.startswith('## ') or l.startswith('### ')]
        return "📊 行业状态（发 '图谱 行业名' 查看详情）\n\n" + '\n'.join(headers)
    return _extract_section(content, industry)

def _cmd_dossier(ws: str, industry: str) -> str:
    cards_dir = Path(ws) / '研究' / '论点卡'
    if not cards_dir.exists():
        return "⚠️ 论点卡目录不存在"
    matches = [f for f in cards_dir.glob('*.md') if industry in f.stem and '模板' not in f.stem]
    if not matches:
        available = [f.stem.replace('_研究底稿', '') for f in cards_dir.glob('*研究底稿.md')]
        return f"⚠️ 未找到含'{industry}'的底稿\n可用：{', '.join(available)}"
    content = matches[0].read_text(encoding='utf-8')
    return content[:REPLY_MAX_LEN] if len(content) > REPLY_MAX_LEN else content

def _extract_section(content: str, keyword: str) -> str:
    sections = re.split(r'(?=^## )', content, flags=re.MULTILINE)
    matched = [s for s in sections if keyword in s]
    if matched:
        result = '\n'.join(matched)
        return result[:REPLY_MAX_LEN] if len(result) > REPLY_MAX_LEN else result
    return f"⚠️ 图谱中未找到'{keyword}'相关段落"


def _cmd_help() -> str:
    return """📋 常用指令

── 录入 ──
录 [内容]          录入纪要（预览确认后入库）
ok                确认写入
改 [意见]          修改待入库内容

── 查询 ──
找 [关键词]        知识库搜索（免费）
问 [问题]          AI问答
析 [行业] [问题]   定向分析

── 报告 ──
蒸馏 [纪要内容]    蒸馏处理纪要
周报              周度雷达
月报A / 月报B      A/B类月度深研

── 系统 ──
s 状态  d 目录  e 额度  z 最新
kk 开始对话  jj 结束对话
hh 更多指令"""


def _cmd_help_more() -> str:
    return """📋 更多指令

── 认知框架（查看免费）──
论 [行业]           查看论点卡（底稿）
论+ [行业] [内容]    更新论点卡
心法                查看投研大心法
焦点                查看当下关注焦点
焦点+ [内容]        更新关注焦点
图谱                查看指标图谱目录
图谱 [行业]         查看行业图谱段
图谱+ [行业] [内容]  更新图谱

── 对比汇总 ──
比 [行业A] [行业B]  横向对比
总 [主题]          汇总

── 控制 ──
/stop   终止当前任务
/clear  清空对话历史
/cancel 取消待确认写入
/redo   重新生成上次录入

── 多知识库 ──
库               当前知识库
切 [名称]        切换知识库"""
