# bot_claude/bot.py — 飞书投研机器人 V3
# 三层指令路由 + 录入确认流程 + Phase调度 + 认知框架查看/更新 + 文件推送
import json, os, subprocess, threading, time, re, math
from collections import deque
from datetime import datetime
from pathlib import Path

import lark_oapi as lark
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))
from feishu_utils import (get_tenant_access_token, send_text_message,
                           send_file_to_user)

# ═══════════════════════════════════════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════════════════════════════════════
CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.json')
with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
    CONFIG = json.load(f)

APP_ID = CONFIG['app_id']
APP_SECRET = CONFIG['app_secret']

# 多知识库支持（兼容旧 kb_path 格式）
if 'kb_roots' in CONFIG:
    KB_ROOTS = {k: os.path.expanduser(v) for k, v in CONFIG['kb_roots'].items()}
else:
    KB_ROOTS = {'周期': os.path.expanduser(CONFIG.get('kb_path', '~/kb'))}
DEFAULT_KB = CONFIG.get('default_kb', list(KB_ROOTS.keys())[0])

REPLY_MAX_LEN = 2800  # 飞书消息安全长度

# ═══════════════════════════════════════════════════════════════════════════════
# 录入规范模板（注入 Claude prompt）
# ═══════════════════════════════════════════════════════════════════════════════
RECORDING_RULES = """## 输出格式（严格遵守）
第一行输出文件路径，格式：FILE_PATH: [子目录名]/[文件名].md
然后空一行，输出完整情报卡内容（含YAML frontmatter）。不要输出其他解释。

## 分类路由
- 能匹配已有子目录 → 使用该目录
- 无法匹配或跨行业 → 使用 0_边缘横向品种
- 宏观策略类 → 使用 宏观策略

## 文件命名
{date}_情报卡_[品种名]_[主题简述].md

## YAML frontmatter
---
date: {date}
tags:
  - [品种名]（仅行业/品种词，≤5个，禁止描述性词汇）
status: 活跃
---

## 情报卡骨架
# 结构化蒸馏：[品种/主题] ({date})

## 🧊 绝对物理参数域 (Hard Facts)
[提取量化数据、价格、产能等客观事实，含因果链]

## 🟡 情报倾向鉴定 (Subjective Bias)
- 情况鉴定：**【多头/空头/中性/无立场】**
- 底色分析：[说明]

## 🎯 跟踪锚点 (Next Stage Anchors)
- [锚点] [事项] | [时间节点] | [判断条件]

## 格式硬约束
- 首行一级标题，标题前后各一空行，列表前后各一空行
- 表格管道符两侧各一空格，嵌套列表2空格缩进
- 文件末尾保留一个换行符"""

# ═══════════════════════════════════════════════════════════════════════════════
# Phase 映射（仅日常操作，排除年度选池类）
# ═══════════════════════════════════════════════════════════════════════════════
PHASE_MAP = {
    'p7':  'Phase7_私密纪要_结构化蒸馏_prompt.md',
    'p5':  'Phase5_周度高频_二阶雷达与事件追踪_prompt.md',
    'p2a': 'Phase2_月度全景_深度研究生成_prompt.md',
    'p2b': 'Phase2_月度全景_深度研究生成_prompt.md',
    'p3':  'Phase3_月度全景_反转排行打分_prompt.md',
    'p6':  'Phase6_流程质检_完整性核对_prompt.md',
    'p6x': 'Phase6X_逻辑矛盾质检_Contradiction_Scan_prompt.md',
}
PHASE_ALIASES = {
    '处理纪要': 'p7', '蒸馏': 'p7', '周报': 'p5', '雷达': 'p5',
    '月报a': 'p2a', '月报A': 'p2a', '月报b': 'p2b', '月报B': 'p2b',
    '分类': 'p3', '质检': 'p6', '矛盾检查': 'p6x',
}
PHASE_TIMEOUT = {
    'p7': 300, 'p5': 600, 'p2a': 600, 'p2b': 600,
    'p3': 300, 'p6': 180, 'p6x': 300,
}
PHASE_OUTPUT_DIRS = {
    'p5': '02_Reports/周度雷达_高频预警',
    'p2a': '02_Reports/A类_成长周期_月度深研',
    'p2b': '02_Reports/B类_刚需供需_月度信号',
    'p3': '03_Watchlist_Pool',
}
PHASE_LABELS = {
    'p7': 'Phase7 蒸馏', 'p5': 'Phase5 周报', 'p2a': 'Phase2A 月报',
    'p2b': 'Phase2B 月报', 'p3': 'Phase3 分类', 'p6': 'Phase6 质检',
    'p6x': 'Phase6X 矛盾检查',
}

# 不写文件的指令前缀（注入到所有 Claude 调用）
NO_WRITE_PREFIX = "⚠️ 重要：本次执行请勿直接写入或创建任何文件。只在 stdout 输出内容。\n\n"

# ═══════════════════════════════════════════════════════════════════════════════
# 内存状态
# ═══════════════════════════════════════════════════════════════════════════════
_processed_event_ids: set = set()
_event_id_lock = threading.Lock()

_pending_writes: dict = {}   # open_id -> {path, content, ts, original, kb}
_pending_lock = threading.Lock()
PENDING_TIMEOUT = 1800  # 30 分钟

_dialog_mode: dict = {}
_dialog_history: dict = {}

_active_processes: dict = {}  # open_id -> subprocess.Popen
_process_lock = threading.Lock()

_user_kb: dict = {}  # open_id -> kb_name

_phase_prompt_cache: dict = {}  # kb_path -> {phase_key -> prompt_text}


# ═══════════════════════════════════════════════════════════════════════════════
# 知识库路径
# ═══════════════════════════════════════════════════════════════════════════════
def active_kb_name(open_id: str = '') -> str:
    return _user_kb.get(open_id, DEFAULT_KB)

def active_kb_path(open_id: str = '') -> str:
    name = active_kb_name(open_id)
    return KB_ROOTS.get(name, list(KB_ROOTS.values())[0])

def get_kb_dir_names(open_id: str = '') -> list:
    """返回 04_Private_Knowledge/ 下所有子目录名"""
    pk = Path(active_kb_path(open_id)) / '04_Private_Knowledge'
    if not pk.exists():
        return []
    return sorted([d.name for d in pk.iterdir()
                   if d.is_dir() and not d.name.startswith('.')])

def kb_file_tree(open_id: str = '') -> str:
    kb = Path(active_kb_path(open_id))
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

def kb_file_count(open_id: str = '') -> int:
    kb = Path(active_kb_path(open_id))
    return sum(1 for _ in kb.rglob('*.md')) if kb.exists() else 0


# ═══════════════════════════════════════════════════════════════════════════════
# Phase prompt 缓存
# ═══════════════════════════════════════════════════════════════════════════════
def load_phase_prompts(kb_path: str):
    if kb_path in _phase_prompt_cache:
        return
    cache = {}
    prompts_dir = Path(kb_path) / '00_Prompts_Library'
    for key, filename in PHASE_MAP.items():
        fp = prompts_dir / filename
        if fp.exists():
            cache[key] = fp.read_text(encoding='utf-8')
    _phase_prompt_cache[kb_path] = cache
    print(f"[bot_claude] 已缓存 {len(cache)} 个 Phase prompt ({kb_path})")


# ═══════════════════════════════════════════════════════════════════════════════
# 零 Token 系统指令
# ═══════════════════════════════════════════════════════════════════════════════
def cmd_status(open_id: str = '') -> str:
    kb = active_kb_path(open_id)
    lines = [
        f"✅ bot_claude V3 运行中",
        f"📁 知识库：{active_kb_name(open_id)} ({kb_file_count(open_id)} 文件)",
        "", "📊 Claude 额度："
    ]
    try:
        r = subprocess.run(['claude', '/status'], capture_output=True,
                           text=True, timeout=15)
        lines.append((r.stdout + r.stderr).strip() or "（无输出）")
    except Exception as e:
        lines.append(f"⚠️ 查询失败：{e}")
    return '\n'.join(lines)

def cmd_quota() -> str:
    try:
        r = subprocess.run(['claude', '/status'], capture_output=True,
                           text=True, timeout=15)
        return f"📊 {(r.stdout + r.stderr).strip() or '（无输出）'}"
    except Exception as e:
        return f"⚠️ 额度查询失败：{e}"

def cmd_directory(open_id: str = '') -> str:
    return f"📁 {active_kb_name(open_id)} 知识库\n\n{kb_file_tree(open_id)}"

def cmd_latest(open_id: str = '') -> str:
    f = Path(active_kb_path(open_id)) / 'inbox' / 'latest_result.md'
    if f.exists():
        return f.read_text(encoding='utf-8')[:REPLY_MAX_LEN]
    return "ℹ️ 暂无保存的结果"

def cmd_which_kb(open_id: str = '') -> str:
    name = active_kb_name(open_id)
    path = active_kb_path(open_id)
    available = ', '.join(KB_ROOTS.keys())
    return f"📁 当前知识库：{name}\n📂 路径：{path}\n🗂️ 可用：{available}"

def cmd_help() -> str:
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
p7 [纪要内容]      蒸馏处理纪要
p5                周度雷达
p2a / p2b         A/B类月度深研

── 系统 ──
s 状态  d 目录  e 额度  z 最新
kk 开始对话  jj 结束对话
hh 更多指令"""

def cmd_help_more() -> str:
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

── 研究流程 ──
p3    结构分类      p6   质检
p6x   矛盾检查     初研 [行业]

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


# ═══════════════════════════════════════════════════════════════════════════════
# 认知框架查看（零 Token）
# ═══════════════════════════════════════════════════════════════════════════════
def _fw_path(open_id: str) -> Path:
    return Path(active_kb_path(open_id)) / '05_Cognitive_Framework'

def cmd_view_xinfa(open_id: str) -> str:
    f = _fw_path(open_id) / '01_通用投研大心法.md'
    return f.read_text(encoding='utf-8') if f.exists() else "⚠️ 文件不存在"

def cmd_view_focus(open_id: str) -> str:
    f = _fw_path(open_id) / '02_当下关注焦点.md'
    return f.read_text(encoding='utf-8') if f.exists() else "⚠️ 文件不存在"

def cmd_view_atlas(open_id: str, industry: str = '') -> str:
    f = _fw_path(open_id) / '03_行业核心指标图谱.md'
    if not f.exists():
        return "⚠️ 图谱文件不存在"
    content = f.read_text(encoding='utf-8')
    if not industry:
        headers = [l for l in content.split('\n')
                   if l.startswith('## ') or l.startswith('### ')]
        return "📊 图谱目录（发 '图谱 行业名' 查看详情）\n\n" + '\n'.join(headers)
    return _extract_section(content, industry)

def cmd_view_dossier(open_id: str, industry: str) -> str:
    cards_dir = _fw_path(open_id) / '论点卡'
    if not cards_dir.exists():
        return "⚠️ 论点卡目录不存在"
    matches = [f for f in cards_dir.glob('*.md')
               if industry in f.stem and '模板' not in f.stem]
    if not matches:
        available = [f.stem.replace('_研究底稿', '')
                     for f in cards_dir.glob('*研究底稿.md')]
        return f"⚠️ 未找到含'{industry}'的底稿\n可用：{', '.join(available)}"
    content = matches[0].read_text(encoding='utf-8')
    if len(content) > REPLY_MAX_LEN:
        return content[:REPLY_MAX_LEN] + "\n\n…（内容过长，建议电脑端查看）"
    return content

def _extract_section(content: str, keyword: str) -> str:
    """从大文件中提取包含关键词的段落（按 ## 分割）"""
    sections = re.split(r'(?=^## )', content, flags=re.MULTILINE)
    matched = [s for s in sections if keyword in s]
    if matched:
        result = '\n'.join(matched)
        return result[:REPLY_MAX_LEN] if len(result) > REPLY_MAX_LEN else result
    return f"⚠️ 图谱中未找到'{keyword}'相关段落"


# ═══════════════════════════════════════════════════════════════════════════════
# 调用 Claude CLI
# ═══════════════════════════════════════════════════════════════════════════════
def call_claude_print(prompt: str, timeout: int = 300,
                      open_id: str = '') -> str:
    """调用 claude --print，返回文本输出。支持 /stop 终止。"""
    kb = active_kb_path(open_id)
    Path(kb).mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.Popen(
            ['claude', '--print', '--dangerously-skip-permissions', prompt],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, cwd=kb
        )
        with _process_lock:
            _active_processes[open_id] = proc
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
            output = stdout.strip()
            if output:
                return output
            err = stderr.strip()
            if err and ('rate' in err.lower() or 'limit' in err.lower()):
                return "⏸️ Claude 额度暂时耗尽\n约1小时后恢复\n💡 可用：s d e z 心法 焦点 图谱 论（均免费）"
            return err if err else "（Claude 无输出）"
        except subprocess.TimeoutExpired:
            proc.kill()
            return f"❌ 处理超时（{timeout}秒）\n建议缩短问题范围或拆分任务"
    except FileNotFoundError:
        return "❌ 未找到 claude 命令，请确认 Claude CLI 已安装"
    except Exception as e:
        return f"❌ 调用异常：{e}"
    finally:
        with _process_lock:
            _active_processes.pop(open_id, None)


# ═══════════════════════════════════════════════════════════════════════════════
# 本地 grep 搜索
# ═══════════════════════════════════════════════════════════════════════════════
def local_grep(keyword: str, open_id: str = '') -> str:
    """本地 grep 搜索知识库，返回格式化结果"""
    kb = active_kb_path(open_id)
    try:
        r = subprocess.run(
            ['grep', '-rn', '--include=*.md', '-i', '--color=never',
             keyword, kb],
            capture_output=True, text=True, timeout=10
        )
        lines = r.stdout.strip().split('\n')
        if not lines or not lines[0]:
            return f"🔍 未找到包含'{keyword}'的内容"

        # 按文件分组，最多显示10条
        results = []
        seen_files = set()
        for line in lines[:30]:
            parts = line.split(':', 2)
            if len(parts) >= 3:
                fpath = Path(parts[0])
                try:
                    rel = fpath.relative_to(kb)
                except ValueError:
                    rel = fpath
                linenum = parts[1]
                text = parts[2].strip()[:100]
                fname = str(rel)
                if fname not in seen_files:
                    results.append(f"\n📄 {fname}")
                    seen_files.add(fname)
                if len(results) < 20:
                    results.append(f"  L{linenum}: {text}")

        return f"🔍 搜索'{keyword}'（{len(lines)}条匹配，{len(seen_files)}个文件）\n" + '\n'.join(results)
    except Exception as e:
        return f"⚠️ 搜索出错：{e}"


# ═══════════════════════════════════════════════════════════════════════════════
# 录入确认流程
# ═══════════════════════════════════════════════════════════════════════════════
def _clean_expired_pending():
    now = time.time()
    with _pending_lock:
        expired = [k for k, v in _pending_writes.items()
                   if now - v['ts'] > PENDING_TIMEOUT]
        for k in expired:
            _pending_writes.pop(k, None)

def _handle_url_feed(url: str, open_id: str, token: str):
    """URL 豁免规则：wechat_parser → Phase 7 → 直接落盘，无需确认"""
    kb = active_kb_path(open_id)
    parser = os.path.join(kb, 'tools', 'wechat_parser.py')
    send_text_message(token, open_id, "⏳ 抓取文章中...")
    pr = subprocess.run(['python3', parser, url],
                        capture_output=True, text=True, timeout=30)
    if pr.returncode != 0:
        send_text_message(token, open_id,
                          f"❌ 文章抓取失败：{(pr.stderr or pr.stdout)[:300]}")
        return
    path_m = re.search(r'已投递至 Inbox:\s*(.+\.md)', pr.stdout)
    if not path_m:
        send_text_message(token, open_id,
                          f"❌ 无法解析落盘路径：{pr.stdout[:200]}")
        return
    raw_path = path_m.group(1).strip()
    try:
        raw_content = Path(raw_path).read_text(encoding='utf-8')
    except Exception as e:
        send_text_message(token, open_id, f"❌ 读取原文失败：{e}")
        return
    # 构建 Phase 7 prompt
    load_phase_prompts(kb)
    p7_prompt = _phase_prompt_cache.get(kb, {}).get('p7', '')
    today = datetime.now().strftime('%Y-%m-%d')
    prompt = (
        NO_WRITE_PREFIX +
        (f"{p7_prompt}\n\n" if p7_prompt else "") +
        f"请将以下原始文章蒸馏为标准情报卡。\n"
        f"第一行输出：FILE_PATH: [子目录]/[文件名].md\n\n"
        f"原文：\n{raw_content[:10000]}"
    )
    send_text_message(token, open_id, "⏳ Phase 7 蒸馏中，预计 30-60 秒...")
    raw = call_claude_print(prompt, timeout=300, open_id=open_id)
    if raw.startswith('❌') or raw.startswith('⏸️'):
        send_text_message(token, open_id, raw)
        return
    file_path, content = _parse_record_output(raw, today)
    full_path = Path(kb) / '04_Private_Knowledge' / file_path
    try:
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding='utf-8')
    except Exception as e:
        send_text_message(token, open_id, f"❌ 写入失败：{e}")
        return
    try:
        rel = full_path.relative_to(kb)
    except ValueError:
        rel = full_path
    send_text_message(token, open_id,
                      f"✅ 已入库: {rel}\n"
                      f"📎 原文存档: {Path(raw_path).name}")
    # 发送情报卡内容供查阅
    card_preview = content if len(content) <= REPLY_MAX_LEN else content[:REPLY_MAX_LEN] + "\n\n…（内容过长，请查看文件）"
    send_text_message(token, open_id, f"📋 情报卡内容：\n\n{card_preview}")


def handle_record(open_id: str, content: str, token: str):
    """录入指令：Claude 生成情报卡 → 发预览 → 等 ok"""
    dirs = get_kb_dir_names(open_id)
    today = datetime.now().strftime('%Y-%m-%d')
    rules = RECORDING_RULES.replace('{date}', today)

    prompt = (NO_WRITE_PREFIX +
              f"你是投资研究知识库录入助手。\n"
              f"04_Private_Knowledge/ 下已有子目录：{dirs}\n\n"
              f"{rules}\n\n"
              f"请将以下原始信息结构化为情报卡：\n{content}")

    raw = call_claude_print(prompt, timeout=180, open_id=open_id)
    if raw.startswith('❌') or raw.startswith('⏸️'):
        send_text_message(token, open_id, raw)
        return

    file_path, card_content = _parse_record_output(raw, today)
    with _pending_lock:
        _pending_writes[open_id] = {
            'path': file_path, 'content': card_content,
            'ts': time.time(), 'original': content,
            'kb': active_kb_path(open_id), 'type': 'new',
        }

    preview = (f"📋 预览（回复 ok 确认写入）\n"
               f"📁 04_Private_Knowledge/{file_path}\n"
               f"{'─' * 30}\n"
               f"{card_content[:2400]}\n"
               f"{'─' * 30}\n"
               f"回复 ok 确认 | 改 [意见] 修改 | /cancel 取消")
    send_text_message(token, open_id, preview)

def _parse_record_output(raw: str, today: str) -> tuple:
    """解析 Claude 输出为 (相对路径, 卡片内容)"""
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
    # 兜底
    if not file_path:
        file_path = f"0_边缘横向品种/{today}_情报卡_未分类.md"
        content = raw
    # 确保路径不以 04_Private_Knowledge/ 开头（避免重复）
    file_path = file_path.replace('04_Private_Knowledge/', '')
    return file_path, content

def handle_confirm(open_id: str, token: str):
    """ok 确认 → 写入文件 → git commit"""
    with _pending_lock:
        pending = _pending_writes.pop(open_id, None)
    if not pending:
        send_text_message(token, open_id, "⚠️ 没有待确认的内容")
        return

    kb = pending['kb']
    ptype = pending.get('type', 'new')
    if ptype == 'new':
        full_path = Path(kb) / '04_Private_Knowledge' / pending['path']
    elif ptype == 'phase':
        full_path = Path(kb) / pending['path']
    else:  # 'update' — framework files already store absolute path
        full_path = Path(pending['path'])

    try:
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(pending['content'], encoding='utf-8')
    except Exception as e:
        send_text_message(token, open_id, f"❌ 写入失败：{e}")
        return

    try:
        rel = full_path.relative_to(kb)
    except ValueError:
        rel = full_path
    send_text_message(token, open_id, f"✅ 已入库\n📁 {rel}")

def handle_modify(open_id: str, modification: str, token: str):
    """改 [意见] → 基于原卡片 + 意见重新生成"""
    with _pending_lock:
        pending = _pending_writes.get(open_id)
    if not pending:
        send_text_message(token, open_id, "⚠️ 没有待修改的内容")
        return

    prompt = (NO_WRITE_PREFIX +
              f"以下是上一次生成的情报卡：\n{pending['content']}\n\n"
              f"用户修改意见：{modification}\n\n"
              f"请按照修改意见重新输出完整情报卡。\n"
              f"第一行保持 FILE_PATH: 格式。")

    send_text_message(token, open_id, "⏳ 正在修改...")
    raw = call_claude_print(prompt, timeout=120, open_id=open_id)
    if raw.startswith('❌') or raw.startswith('⏸️'):
        send_text_message(token, open_id, raw)
        return

    today = datetime.now().strftime('%Y-%m-%d')
    file_path, card_content = _parse_record_output(raw, today)
    with _pending_lock:
        _pending_writes[open_id].update({
            'path': file_path, 'content': card_content, 'ts': time.time(),
        })

    preview = (f"📋 修改后预览\n📁 04_Private_Knowledge/{file_path}\n"
               f"{'─' * 30}\n{card_content[:2400]}\n{'─' * 30}\n"
               f"回复 ok 确认 | 改 [意见] 继续修改")
    send_text_message(token, open_id, preview)

def handle_cancel(open_id: str, token: str):
    with _pending_lock:
        removed = _pending_writes.pop(open_id, None)
    if removed:
        send_text_message(token, open_id, "🗑️ 已取消待确认内容")
    else:
        send_text_message(token, open_id, "ℹ️ 没有待确认的内容")

def handle_redo(open_id: str, token: str):
    with _pending_lock:
        pending = _pending_writes.get(open_id)
    if not pending or 'original' not in pending:
        send_text_message(token, open_id, "⚠️ 没有可重做的录入")
        return
    original = pending['original']
    with _pending_lock:
        _pending_writes.pop(open_id, None)
    send_text_message(token, open_id, "⏳ 重新生成...")
    handle_record(open_id, original, token)


# ═══════════════════════════════════════════════════════════════════════════════
# 认知框架更新（消耗 Token，走确认流程）
# ═══════════════════════════════════════════════════════════════════════════════
def handle_framework_update(cmd: str, arg: str, content: str,
                            open_id: str, token: str):
    fw = _fw_path(open_id)
    if cmd == '焦点+':
        target = fw / '02_当下关注焦点.md'
        if not target.exists():
            send_text_message(token, open_id, "⚠️ 焦点文件不存在"); return
        current = target.read_text(encoding='utf-8')
        prompt = (NO_WRITE_PREFIX +
                  f"当前焦点文件：\n{current}\n\n"
                  f"请按用户意见更新，保持格式不变：\n{content}\n"
                  f"输出更新后的完整文件内容。")
    elif cmd == '图谱+':
        target = fw / '03_行业核心指标图谱.md'
        if not target.exists():
            send_text_message(token, open_id, "⚠️ 图谱文件不存在"); return
        current = target.read_text(encoding='utf-8')
        section = _extract_section(current, arg)
        prompt = (NO_WRITE_PREFIX +
                  f"图谱'{arg}'段落：\n{section}\n\n"
                  f"请按以下新数据更新该段落：\n{content}\n"
                  f"只输出更新后的该段落。")
    elif cmd == '论+':
        cards_dir = fw / '论点卡'
        matches = [f for f in cards_dir.glob('*.md') if arg in f.stem]
        if not matches:
            send_text_message(token, open_id, f"⚠️ 未找到'{arg}'底稿"); return
        target = matches[0]
        current = target.read_text(encoding='utf-8')
        prompt = (NO_WRITE_PREFIX +
                  f"当前底稿：\n{current}\n\n"
                  f"请根据新信息更新对应章节：\n{content}\n"
                  f"输出更新后的完整底稿。")
    else:
        return

    send_text_message(token, open_id, "⏳ 生成更新...")
    raw = call_claude_print(prompt, timeout=300, open_id=open_id)
    if raw.startswith('❌') or raw.startswith('⏸️'):
        send_text_message(token, open_id, raw); return

    with _pending_lock:
        _pending_writes[open_id] = {
            'path': str(target), 'content': raw,
            'ts': time.time(), 'original': content,
            'kb': active_kb_path(open_id), 'type': 'update',
        }
    preview = (f"📋 更新预览\n📁 {target.name}\n"
               f"{'─' * 30}\n{raw[:2400]}\n{'─' * 30}\n"
               f"回复 ok 确认 | /cancel 取消")
    send_text_message(token, open_id, preview)


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 调度
# ═══════════════════════════════════════════════════════════════════════════════
def resolve_phase(text: str):
    """解析文本为 phase_key，找不到返回 None"""
    t = text.strip().lower()
    if t in PHASE_MAP:
        return t
    # 带内容的 p7，如 "p7 xxxxx"
    if t.startswith('p7 ') or t.startswith('p7\n'):
        return 'p7'
    return PHASE_ALIASES.get(text.strip(), None)

def handle_phase(phase_key: str, extra: str, open_id: str, token: str):
    """执行 Phase → 预览 → 等待确认"""
    kb = active_kb_path(open_id)
    load_phase_prompts(kb)
    cache = _phase_prompt_cache.get(kb, {})
    prompt_text = cache.get(phase_key, '')
    if not prompt_text:
        send_text_message(token, open_id,
                          f"❌ Phase prompt 未找到: {PHASE_MAP.get(phase_key)}")
        return

    # 构建完整 prompt
    full_prompt = NO_WRITE_PREFIX + prompt_text
    if phase_key == 'p2a':
        full_prompt += "\n\n⚠️ 本次仅处理 A类（成长周期型）行业。"
    elif phase_key == 'p2b':
        full_prompt += "\n\n⚠️ 本次仅处理 B类（刚需供需型）行业。"
    if phase_key == 'p7' and extra:
        full_prompt += f"\n\n请处理以下用户直接发送的原始纪要：\n{extra}"

    # 添加输出路径指令
    today = datetime.now().strftime('%Y-%m-%d')
    out_dir = PHASE_OUTPUT_DIRS.get(phase_key, '')
    if out_dir:
        full_prompt += (f"\n\n输出第一行请标注 FILE_PATH: {out_dir}/"
                        f"{today}_{PHASE_LABELS.get(phase_key, 'report')}.md")

    timeout = PHASE_TIMEOUT.get(phase_key, 300)
    label = PHASE_LABELS.get(phase_key, phase_key)
    send_text_message(token, open_id, f"⏳ 执行 {label}，预计 {timeout//60} 分钟...")

    raw = call_claude_print(full_prompt, timeout=timeout, open_id=open_id)
    if raw.startswith('❌') or raw.startswith('⏸️'):
        send_text_message(token, open_id, raw); return

    # 解析输出路径
    file_path, content = _parse_record_output(raw, today)
    if not file_path or file_path.endswith('未分类.md'):
        if out_dir:
            file_path = f"{out_dir}/{today}_{label}.md"
        else:
            file_path = f"02_Reports/{today}_{label}.md"

    with _pending_lock:
        _pending_writes[open_id] = {
            'path': file_path, 'content': content,
            'ts': time.time(), 'original': '',
            'kb': kb, 'type': 'phase',
        }

    # 发预览：短内容发文本，长内容发文件
    if len(content) <= REPLY_MAX_LEN:
        preview = (f"📋 {label} 预览\n📁 {file_path}\n"
                   f"{'─' * 30}\n{content}\n{'─' * 30}\n"
                   f"回复 ok 确认写入")
        send_text_message(token, open_id, preview)
    else:
        # 保存为临时文件并发送
        tmp_path = Path(kb) / '04_Private_Knowledge' / '_Raw_Inbox' / f'_preview_{phase_key}.md'
        tmp_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path.write_text(content, encoding='utf-8')
        send_file_to_user(token, open_id, str(tmp_path))
        send_text_message(token, open_id,
                          f"📋 {label} 报告预览已发送\n📁 写入路径：{file_path}\n"
                          f"回复 ok 确认写入")


# ═══════════════════════════════════════════════════════════════════════════════
# 智能任务指令
# ═══════════════════════════════════════════════════════════════════════════════
def parse_task_cmd(text: str) -> tuple:
    """解析任务指令，返回 (cmd, content)"""
    # 单字指令
    for prefix in ['录', '找', '问', '总']:
        if text.startswith(prefix + ' ') or text.startswith(prefix + '\n'):
            return prefix, text[2:].strip()
    # 析 [行业] [问题]
    if text.startswith('析 ') or text.startswith('析\n'):
        return '析', text[2:].strip()
    # 比 [A] [B]
    if text.startswith('比 ') or text.startswith('比\n'):
        return '比', text[2:].strip()
    # 焦点+、图谱+、论+ （含空格分割）
    if text.startswith('焦点+ ') or text.startswith('焦点+\n'):
        return '焦点+', text[4:].strip()
    if text.startswith('图谱+ '):
        return '图谱+', text[4:].strip()
    if text.startswith('论+ '):
        return '论+', text[3:].strip()
    # 初研
    if text.startswith('初研 '):
        return '初研', text[3:].strip()
    # 旧指令兼容
    for p in ['分析', '录入', '更新', '查找', '总结']:
        if text.startswith(p + '：') or text.startswith(p + ':'):
            new_cmd = {'分析': '问', '录入': '录', '更新': '录',
                       '查找': '找', '总结': '总'}
            return new_cmd.get(p, '问'), text[len(p) + 1:].strip()
    return '', text

def build_task_prompt(cmd: str, content: str, open_id: str = '') -> str:
    """按指令类型精准构建 prompt"""
    kb = active_kb_path(open_id)

    if cmd == '问':
        structure = kb_file_tree(open_id)
        return (NO_WRITE_PREFIX +
                f"知识库结构：\n{structure}\n\n"
                f"请基于知识库回答：\n{content}")
    elif cmd == '析':
        # 尝试解析行业名
        parts = content.split(None, 1)
        if len(parts) == 2:
            industry, question = parts
        else:
            industry, question = content, '当前周期位置与反转条件分析'
        # 加载该行业底稿
        dossier_path = _fw_path(open_id) / '论点卡'
        dossier = ''
        if dossier_path.exists():
            matches = [f for f in dossier_path.glob('*.md') if industry in f.stem]
            if matches:
                dossier = matches[0].read_text(encoding='utf-8')
        # 查找该行业的情报卡文件列表
        pk = Path(kb) / '04_Private_Knowledge'
        industry_files = []
        for d in pk.iterdir():
            if d.is_dir() and industry in d.name:
                industry_files = [f.name for f in d.glob('*.md')]
                break
        return (NO_WRITE_PREFIX +
                f"目标行业：{industry}\n"
                f"底稿：\n{dossier[:3000]}\n\n"
                f"该行业情报文件：{industry_files}\n\n"
                f"分析问题：{question}")
    elif cmd == '比':
        parts = content.split()
        if len(parts) < 2:
            return f"请提供两个行业名称进行比较。输入：{content}"
        a, b = parts[0], parts[1]
        da = cmd_view_dossier(open_id, a)
        db = cmd_view_dossier(open_id, b)
        return (NO_WRITE_PREFIX +
                f"行业A({a})底稿：\n{da[:2500]}\n\n"
                f"行业B({b})底稿：\n{db[:2500]}\n\n"
                f"请对两者做横向对比分析。")
    elif cmd == '总':
        return (NO_WRITE_PREFIX +
                f"知识库结构：\n{kb_file_tree(open_id)}\n\n"
                f"请汇总主题'{content}'下所有相关文件要点。")
    else:
        # 连续对话或无前缀
        return (NO_WRITE_PREFIX +
                f"知识库结构：\n{kb_file_tree(open_id)}\n\n"
                f"请回答：\n{content}")


# ═══════════════════════════════════════════════════════════════════════════════
# 结果交付
# ═══════════════════════════════════════════════════════════════════════════════
def deliver_result(token: str, open_id: str, text: str):
    """短文本直接发，长文本分段 + 发文件"""
    if text.startswith('❌') or text.startswith('⏸️') or text.startswith('⚠️'):
        send_text_message(token, open_id, text[:REPLY_MAX_LEN])
        return
    if len(text) <= REPLY_MAX_LEN:
        send_text_message(token, open_id, text)
        return
    # 分段发送
    chunks = _split_text(text, REPLY_MAX_LEN)
    for i, chunk in enumerate(chunks):
        header = f"📄 [{i+1}/{len(chunks)}]\n"
        send_text_message(token, open_id, header + chunk)
        if i < len(chunks) - 1:
            time.sleep(0.5)
    # 保存完整结果
    _save_latest(text, open_id)

def _split_text(text: str, max_len: int) -> list:
    paragraphs = text.split('\n\n')
    chunks, current = [], ''
    for p in paragraphs:
        if len(current) + len(p) + 2 > max_len and current:
            chunks.append(current)
            current = p
        else:
            current = current + '\n\n' + p if current else p
    if current:
        chunks.append(current)
    return chunks or [text[:max_len]]

def _save_latest(content: str, open_id: str = ''):
    try:
        kb = active_kb_path(open_id)
        target = Path(kb) / '04_Private_Knowledge' / '_Raw_Inbox' / 'latest_result.md'
        target.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        target.write_text(f"# 最新结果（{ts}）\n\n{content}\n", encoding='utf-8')
    except Exception as e:
        print(f"[bot_claude] 保存结果失败: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# Git 操作
# ═══════════════════════════════════════════════════════════════════════════════
def _git_commit(file_path: Path, kb_path: str, message: str) -> str:
    try:
        subprocess.run(['git', 'add', str(file_path)],
                       cwd=kb_path, capture_output=True, timeout=10)
        r = subprocess.run(['git', 'commit', '-m', message],
                           cwd=kb_path, capture_output=True, text=True,
                           timeout=10)
        # 提取 commit hash
        match = re.search(r'[a-f0-9]{7,}', r.stdout)
        return match.group(0) if match else '已提交'
    except Exception as e:
        print(f"[bot_claude] git 操作失败: {e}")
        return '(git失败)'


# ═══════════════════════════════════════════════════════════════════════════════
# 知识库切换
# ═══════════════════════════════════════════════════════════════════════════════
def switch_kb(open_id: str, name: str, token: str):
    name = name.strip()
    if name in KB_ROOTS:
        _user_kb[open_id] = name
        load_phase_prompts(KB_ROOTS[name])
        send_text_message(token, open_id,
                          f"✅ 已切换到 {name} 知识库\n📂 {KB_ROOTS[name]}")
    else:
        available = ', '.join(KB_ROOTS.keys())
        send_text_message(token, open_id,
                          f"⚠️ 未找到'{name}'知识库\n可用：{available}")


# ═══════════════════════════════════════════════════════════════════════════════
# 斜杠控制指令
# ═══════════════════════════════════════════════════════════════════════════════
def handle_stop(open_id: str, token: str):
    with _process_lock:
        proc = _active_processes.pop(open_id, None)
    if proc:
        try:
            proc.kill()
        except Exception:
            pass
        send_text_message(token, open_id, "⛔ 已终止当前任务")
    else:
        send_text_message(token, open_id, "ℹ️ 当前没有运行中的任务")

def handle_clear(open_id: str, token: str):
    _dialog_mode.pop(open_id, None)
    _dialog_history.pop(open_id, None)
    send_text_message(token, open_id, "🗑️ 对话历史已清空")


# ═══════════════════════════════════════════════════════════════════════════════
# 主消息路由
# ═══════════════════════════════════════════════════════════════════════════════
def handle_message_async(open_id: str, raw_text: str):
    token = get_tenant_access_token(APP_ID, APP_SECRET)
    if not token:
        return
    _clean_expired_pending()
    text = raw_text.strip()

    # ══ 第一层：零 token 系统指令 ══
    QUICK = {
        's': lambda: cmd_status(open_id), '状态': lambda: cmd_status(open_id),
        'd': lambda: cmd_directory(open_id), '目录': lambda: cmd_directory(open_id),
        'h': cmd_help, '帮助': cmd_help,
        'hh': cmd_help_more, '更多': cmd_help_more,
        'e': cmd_quota, '额度': cmd_quota,
        'z': lambda: cmd_latest(open_id), '最新': lambda: cmd_latest(open_id),
        '库': lambda: cmd_which_kb(open_id),
        '心法': lambda: cmd_view_xinfa(open_id),
        '焦点': lambda: cmd_view_focus(open_id),
    }
    if text in QUICK:
        result = QUICK[text]()
        deliver_result(token, open_id, result)
        return

    # 图谱
    if text == '图谱':
        deliver_result(token, open_id, cmd_view_atlas(open_id))
        return
    if text.startswith('图谱 '):
        deliver_result(token, open_id, cmd_view_atlas(open_id, text[3:].strip()))
        return

    # 论 [行业]
    if text.startswith('论 '):
        deliver_result(token, open_id, cmd_view_dossier(open_id, text[2:].strip()))
        return

    # ══ 斜杠控制 ══
    if text == '/stop':
        handle_stop(open_id, token); return
    if text == '/clear':
        handle_clear(open_id, token); return
    if text == '/cancel':
        handle_cancel(open_id, token); return
    if text == '/redo':
        handle_redo(open_id, token); return

    # ══ 确认/修改 ══
    if text.lower() in ('ok', '确认'):
        handle_confirm(open_id, token); return
    if text.startswith('改 '):
        handle_modify(open_id, text[2:].strip(), token); return

    # ══ 对话模式 ══
    if text in ('kk', '开始对话'):
        _dialog_mode[open_id] = True
        _dialog_history[open_id] = deque(maxlen=10)
        send_text_message(token, open_id,
                          '✅ 连续对话模式\n后续消息无需前缀\n发 jj 或 /clear 退出')
        return
    if text in ('jj', '结束对话'):
        handle_clear(open_id, token); return

    # ══ 知识库切换 ══
    if text.startswith('切 '):
        switch_kb(open_id, text[2:].strip(), token); return

    # ══ 备忘录快捷存储（零 Token，直接写文件）══
    if (text.startswith('memo ') or text.startswith('memo\n')
            or text.startswith('备忘 ') or text.startswith('备忘\n')):
        parts = text.split(None, 1)
        memo_content = parts[1].strip() if len(parts) > 1 else ''
        if memo_content:
            from memo_handler import save_memo
            rel_path, git_hash = save_memo(memo_content, active_kb_path(open_id))
            send_text_message(token, open_id,
                              f"📝 已记录\n📁 {rel_path}\n📌 git: {git_hash}")
        else:
            send_text_message(token, open_id, "⚠️ memo 后请附上内容")
        return

    # ══ URL 投喂（豁免规则：全自动，直接落盘，无需确认）══
    _URL_RE = re.compile(r'https?://\S+')
    _url_m = _URL_RE.search(text)
    _feed_kws = ('投喂', '蒸馏', '存档')
    _is_feed = (
        (_url_m and text.strip() == _url_m.group(0))
        or any(text.startswith(kw + ' ') or text.startswith(kw + '\n') for kw in _feed_kws)
    )
    if _is_feed:
        if _url_m:
            _feed_url = _url_m.group(0)
        else:
            _parts = text.split(None, 1)
            _feed_url = _parts[1].strip() if len(_parts) > 1 else ''
        if _feed_url:
            _handle_url_feed(_feed_url, open_id, token)
        else:
            send_text_message(token, open_id, "⚠️ 请附上文章 URL")
        return

    # ══ 第二层：Phase 触发 ══
    phase_key = resolve_phase(text)
    if phase_key:
        extra = ''
        if phase_key == 'p7' and len(text) > 2:
            extra = text[2:].strip() if text.startswith('p7') else text
        handle_phase(phase_key, extra, open_id, token)
        return

    # 初研
    if text.startswith('初研 '):
        industry = text[3:].strip()
        send_text_message(token, open_id, f"⏳ 生成 {industry} 初研底稿...")
        prompt = (NO_WRITE_PREFIX +
                  f"请为'{industry}'生成行业研究初步底稿。\n"
                  f"参照 05_Cognitive_Framework/论点卡/04_行业投资论点卡_模板.md 的格式。\n"
                  f"先网络搜索该行业当前供需格局，再结合知识库已有情报。\n"
                  f"第一行输出 FILE_PATH: 论点卡/{industry}_研究底稿.md")
        raw = call_claude_print(prompt, timeout=600, open_id=open_id)
        if raw.startswith('❌') or raw.startswith('⏸️'):
            send_text_message(token, open_id, raw); return
        today = datetime.now().strftime('%Y-%m-%d')
        fp, content = _parse_record_output(raw, today)
        if not fp or '未分类' in fp:
            fp = f"论点卡/{industry}_研究底稿.md"
        with _pending_lock:
            _pending_writes[open_id] = {
                'path': str(Path(active_kb_path(open_id)) / '05_Cognitive_Framework' / fp),
                'content': content, 'ts': time.time(),
                'original': industry, 'kb': active_kb_path(open_id),
                'type': 'update',
            }
        if len(content) <= REPLY_MAX_LEN:
            send_text_message(token, open_id,
                              f"📋 初研底稿预览\n📁 {fp}\n{'─'*30}\n"
                              f"{content}\n{'─'*30}\n回复 ok 确认写入")
        else:
            tmp = Path(active_kb_path(open_id)) / '04_Private_Knowledge' / '_Raw_Inbox' / '_preview_初研.md'
            tmp.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(content, encoding='utf-8')
            send_file_to_user(token, open_id, str(tmp))
            send_text_message(token, open_id,
                              f"📋 初研底稿已发送\n📁 {fp}\n回复 ok 确认写入")
        return

    # ══ 第三层：智能任务指令 ══
    cmd, content = parse_task_cmd(text)

    # 找 → 本地 grep（零 token）
    if cmd == '找':
        result = local_grep(content, open_id)
        send_text_message(token, open_id, result)
        return

    # 录 → 确认流程
    if cmd == '录':
        send_text_message(token, open_id, "⏳ 正在生成情报卡...")
        handle_record(open_id, content, token)
        return

    # 框架更新
    if cmd in ('焦点+', '图谱+', '论+'):
        # 图谱+ 需要解析行业名和内容
        if cmd == '图谱+':
            parts = content.split(None, 1)
            arg = parts[0] if parts else ''
            cont = parts[1] if len(parts) > 1 else ''
            handle_framework_update(cmd, arg, cont, open_id, token)
        elif cmd == '论+':
            parts = content.split(None, 1)
            arg = parts[0] if parts else ''
            cont = parts[1] if len(parts) > 1 else ''
            handle_framework_update(cmd, arg, cont, open_id, token)
        else:
            handle_framework_update(cmd, '', content, open_id, token)
        return

    # 问/析/比/总/无前缀 → Claude 问答
    if not content:
        send_text_message(token, open_id, "💡 发送 h 查看常用指令")
        return

    send_text_message(token, open_id, "⏳ 处理中...")

    # 连续对话历史
    history_block = ''
    if _dialog_mode.get(open_id):
        hist = _dialog_history.get(open_id, deque())
        if hist:
            lines = [f"{'用户' if h['role']=='user' else '助手'}：{h['text']}"
                     for h in hist]
            history_block = "对话历史：\n" + '\n'.join(lines) + "\n\n"

    prompt = build_task_prompt(cmd, content, open_id)
    if history_block:
        prompt = prompt + '\n\n' + history_block

    raw = call_claude_print(prompt, timeout=300, open_id=open_id)

    # 存对话历史
    if _dialog_mode.get(open_id):
        hist = _dialog_history.setdefault(open_id, deque(maxlen=10))
        hist.append({'role': 'user', 'text': content[:100]})
        hist.append({'role': 'assistant', 'text': raw[:100]})

    deliver_result(token, open_id, raw)


# ═══════════════════════════════════════════════════════════════════════════════
# 飞书 WebSocket 事件处理
# ═══════════════════════════════════════════════════════════════════════════════
def on_message_receive(data: P2ImMessageReceiveV1) -> None:
    try:
        if data.event is None:
            return
        message = data.event.message
        sender = data.event.sender
        if message is None or sender is None:
            return
        if message.message_type != 'text':
            return
        try:
            content_obj = json.loads(message.content or '{}')
            raw_text = content_obj.get('text', '').strip()
        except Exception:
            raw_text = ''
        if not raw_text:
            return
        open_id = sender.sender_id.open_id if sender.sender_id else ''
        if not open_id:
            return
        # 去重
        msg_id = message.message_id or ''
        if msg_id:
            with _event_id_lock:
                if msg_id in _processed_event_ids:
                    return
                _processed_event_ids.add(msg_id)
                if len(_processed_event_ids) > 1000:
                    _processed_event_ids.clear()
                    _processed_event_ids.add(msg_id)
        t = threading.Thread(target=handle_message_async,
                             args=(open_id, raw_text), daemon=True)
        t.start()
    except Exception as e:
        print(f"[bot_claude] 消息处理异常: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# 启动
# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    # 预加载所有知识库的 Phase prompts
    for name, path in KB_ROOTS.items():
        load_phase_prompts(path)
        print(f"[bot_claude] 知识库 '{name}' → {path}")

    print(f"[bot_claude] V3 启动中（默认知识库: {DEFAULT_KB}）")

    event_handler = (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_im_message_receive_v1(on_message_receive)
        .build()
    )
    ws_client = lark.ws.Client(
        APP_ID, APP_SECRET,
        event_handler=event_handler,
        log_level=lark.LogLevel.INFO
    )
    ws_client.start()
