# bot_gemini/bot.py
# 飞书机器人 —— 基于 DeepSeek API（OpenAI 兼容格式）+ 飞书长连接（WebSocket）
#
# 特性：
#   - 录入/更新 操作先展示计划，回复「确认」才实际写文件（类似 Claude Code）
#   - 自由提问主动判断，按需引用知识库
#   - 按需报告：发「晨报」「商品报」「自选股」「复盘」即时生成对应报告

import json
import os
import re
import threading
import urllib.request
import urllib.error
from pathlib import Path

import lark_oapi as lark
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1

import sys
_BOT_DIR    = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR   = os.path.dirname(_BOT_DIR)
_SHARED_DIR = os.path.join(_ROOT_DIR, 'shared')
sys.path.insert(0, _ROOT_DIR)
sys.path.insert(0, _SHARED_DIR)
from feishu_utils import get_tenant_access_token, send_text_message

# ── user_registry：记录用户 open_id，供 scheduler 主动推送使用 ────────────────
REGISTRY_PATH = os.path.join(_SHARED_DIR, 'user_registry.json')
_registry_lock = threading.Lock()

def _register_user(open_id: str, name: str = ''):
    """将用户 open_id 写入 registry，供定时任务推送使用"""
    try:
        with _registry_lock:
            reg = {}
            if os.path.exists(REGISTRY_PATH):
                with open(REGISTRY_PATH, 'r', encoding='utf-8') as f:
                    reg = json.load(f)
            ids = reg.setdefault('open_ids', {})
            if open_id not in ids.values():
                key = name or f'user_{len(ids)+1}'
                ids[key] = open_id
                with open(REGISTRY_PATH, 'w', encoding='utf-8') as f:
                    json.dump(reg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[bot] registry 写入失败: {e}")

# ── 读取配置 ──────────────────────────────────────────────────────────────────
CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.json')
with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
    CONFIG = json.load(f)

APP_ID           = CONFIG['app_id']
APP_SECRET       = CONFIG['app_secret']
DEEPSEEK_API_KEY = CONFIG.get('deepseek_api_key', '')
KB_PATH          = os.path.expanduser(CONFIG.get('kb_path', '~/kb'))

DEEPSEEK_URL   = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"

REPLY_MAX_LEN      = 3000
LATEST_RESULT_FILE = 'inbox/latest_result_deepseek.md'

# ── 状态存储（内存） ───────────────────────────────────────────────────────────
_processed_msg_ids: set = set()
_msg_id_lock = threading.Lock()

# 等待确认的写文件操作：{open_id: {"file_path": ..., "content": ...}}
_pending_writes: dict = {}
_pending_lock = threading.Lock()


# ── 知识库辅助 ────────────────────────────────────────────────────────────────

def list_kb_files() -> list:
    kb = Path(KB_PATH)
    if not kb.exists():
        return []
    return [p for p in kb.rglob('*') if p.is_file()]


def kb_files_str() -> str:
    files = list_kb_files()
    if not files:
        return f"（知识库目录 {KB_PATH} 为空或不存在）"
    return '\n'.join(str(p) for p in files)


def kb_file_tree() -> str:
    kb = Path(KB_PATH)
    if not kb.exists():
        return f"⚠️ 知识库目录 {KB_PATH} 不存在"
    files = list_kb_files()
    if not files:
        return f"⚠️ 知识库目录 {KB_PATH} 为空"
    lines = [f"📁 {KB_PATH}"]
    for f in sorted(files):
        rel = f.relative_to(kb)
        depth = len(rel.parts) - 1
        indent = "  " * depth
        lines.append(f"{indent}├─ {rel.name}")
    return '\n'.join(lines)


def write_kb_file(relative_path: str, content: str) -> str:
    """将内容写入知识库文件，返回结果说明"""
    try:
        kb = Path(KB_PATH)
        clean = relative_path.lstrip('/').lstrip('\\')
        target = (kb / clean).resolve()
        # 防路径穿越
        if not str(target).startswith(str(kb.resolve())):
            return f"❌ 非法路径：{relative_path}"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding='utf-8')
        return f"✅ 已写入：{target}"
    except Exception as e:
        return f"❌ 写入失败：{e}"


def save_latest_result(content: str):
    try:
        from datetime import datetime
        target = Path(KB_PATH) / LATEST_RESULT_FILE
        target.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        target.write_text(f"# DeepSeek 最新结果（{ts}）\n\n{content}\n", encoding='utf-8')
    except Exception as e:
        print(f"[bot_gemini/deepseek] 保存结果文件失败: {e}")


def truncate_reply(text: str) -> str:
    if len(text) <= REPLY_MAX_LEN:
        return text
    save_latest_result(text)
    return text[:REPLY_MAX_LEN] + f"\n\n…（内容已截断，完整结果已保存到 {LATEST_RESULT_FILE}）"


# ── 系统类指令 ────────────────────────────────────────────────────────────────

def cmd_status() -> str:
    return (
        "✅ bot_deepseek 运行中（长连接模式）\n"
        f"  知识库：{KB_PATH}\n"
        f"  文件数：{len(list_kb_files())}\n"
        f"  模型：{DEEPSEEK_MODEL}"
    )


def cmd_directory() -> str:
    return "📁 知识库目录结构：\n\n" + kb_file_tree()


def cmd_help() -> str:
    return (
        "📋 可用指令列表（DeepSeek 投研助理）\n\n"
        "【按需报告 — 随时发随时生成】\n"
        "  晨报        股票晨报（美股/港股/A股盘前）\n"
        "  商品报      大宗商品晨报（能源/金属/农产品/黑色系）\n"
        "  自选股      自选股日报（7只股票涨跌+公告+AI动态）\n"
        "  复盘        每日复盘（A股+港股+板块+北向）\n\n"
        "【知识库任务类】\n"
        "  分析：[问题]        读取知识库相关文件，做逻辑分析\n"
        "  录入：[内容]        整理格式后写入知识库（需确认）\n"
        "  更新：[目标] [内容]  找到对应文件并更新（需确认）\n"
        "  查找：[关键词]      在知识库全文搜索，返回摘要\n"
        "  总结：[主题/公司]   汇总该主题下所有文件要点\n"
        "  无前缀             自由提问，主动判断回答\n\n"
        "【写入确认流程】\n"
        "  录入/更新 → 展示计划 → 回复【确认】执行，回复【取消】放弃\n\n"
        "【系统类】\n"
        "  状态   查看服务状态\n"
        "  目录   查看知识库文件树\n"
        "  帮助   显示本列表\n"
    )


# ── 调用 DeepSeek API ─────────────────────────────────────────────────────────

def call_deepseek(messages: list) -> str:
    """通过 urllib 调用 DeepSeek（OpenAI 兼容），超时 120 秒"""
    if not DEEPSEEK_API_KEY or DEEPSEEK_API_KEY.startswith('填入'):
        return "❌ 请先在 config.json 中填入 DeepSeek API Key"

    payload = json.dumps({
        "model": DEEPSEEK_MODEL,
        "messages": messages,
        "max_tokens": 4096,
    }).encode('utf-8')

    req = urllib.request.Request(
        DEEPSEEK_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode('utf-8'))
        choices = result.get('choices', [])
        if choices:
            text = choices[0].get('message', {}).get('content', '').strip()
            return text if text else "（DeepSeek 无输出）"
        return "（DeepSeek 返回空候选列表）"
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='ignore')
        return f"❌ DeepSeek HTTP 错误 {e.code}: {body[:300]}"
    except urllib.error.URLError as e:
        return f"❌ DeepSeek 网络错误: {e.reason}"
    except Exception as e:
        return f"❌ DeepSeek 调用异常: {e}"


# ── 解析写入计划 ──────────────────────────────────────────────────────────────

def parse_write_plan(text: str):
    """
    从 AI 输出中解析文件路径和内容。
    返回 (explanation, file_path, content)，解析失败返回 None。
    """
    path_m    = re.search(r'===FILE_PATH===\s*(.*?)\s*===END_PATH===', text, re.DOTALL)
    content_m = re.search(r'===FILE_CONTENT===\s*(.*?)\s*===END_CONTENT===', text, re.DOTALL)
    if not path_m or not content_m:
        return None
    file_path   = path_m.group(1).strip()
    file_content = content_m.group(1).strip()
    explanation  = text[:text.find('===FILE_PATH===')].strip()
    return explanation, file_path, file_content


# ── 构建消息列表 ──────────────────────────────────────────────────────────────

WRITE_FORMAT = """
请严格按以下格式输出：

[分析与说明]
简要说明操作计划

===FILE_PATH===
相对于知识库的文件路径，例如：stocks/贵州茅台.md
===END_PATH===

===FILE_CONTENT===
文件完整 Markdown 内容
===END_CONTENT===
"""

def build_messages(prefix: str, content: str) -> list:
    kb_files = kb_files_str()
    system = {
        "role": "system",
        "content": (
            "你是一名专业的投资研究助手，服务于一位专业投资人。"
            "你有主动判断能力：问题涉及知识库时主动引用，不涉及时直接基于专业知识回答。"
            "对写入操作要谨慎准确，按指定格式给出结构化输出。"
        )
    }

    if prefix == '分析':
        user_content = (
            f"知识库文件列表：\n{kb_files}\n\n"
            f"请阅读知识库中与以下问题相关的文件，给出专业深度分析：\n{content}"
        )
    elif prefix == '录入':
        user_content = (
            f"知识库路径：{KB_PATH}\n现有文件：\n{kb_files}\n\n"
            f"请将以下内容整理成结构化 Markdown，确定写入的文件路径（新建或追加到已有文件）：\n{content}"
            f"\n\n{WRITE_FORMAT}"
        )
    elif prefix == '更新':
        user_content = (
            f"知识库文件列表：\n{kb_files}\n\n"
            f"请找到与以下内容相关的知识库文件，给出更新后的完整文件内容：\n{content}"
            f"\n\n{WRITE_FORMAT}"
        )
    elif prefix == '查找':
        user_content = (
            f"知识库文件列表：\n{kb_files}\n\n"
            f"请搜索以下关键词，返回包含该关键词的文件名及相关摘要段落：\n{content}"
        )
    elif prefix == '总结':
        user_content = (
            f"知识库文件列表：\n{kb_files}\n\n"
            f"请找出所有与以下主题或公司相关的文件，汇总核心要点：\n{content}"
        )
    else:
        user_content = (
            f"知识库文件列表（按需引用）：\n{kb_files}\n\n{content}"
        )

    return [system, {"role": "user", "content": user_content}]


# ── 异步处理消息 ──────────────────────────────────────────────────────────────

PREFIX_EMOJI = {
    '分析': '📊', '查找': '🔍', '总结': '📋', '': '💬',
}


def _run_report(report_type: str, open_id: str, token: str):
    """按需生成报告并发送（在独立线程中调用）"""
    try:
        # 延迟导入，避免在没有 dailyreport 环境时启动失败
        sys.path.insert(0, _ROOT_DIR)
        from daily_reporter.data_fetcher import (
            fetch_morning_stock, fetch_morning_commodity,
            fetch_watchlist, fetch_review
        )
        from daily_reporter.report_builder import (
            build_morning_stock, build_morning_commodity,
            build_watchlist, build_review
        )

        if report_type == '晨报':
            data   = fetch_morning_stock()
            report = build_morning_stock(data)
        elif report_type == '商品报':
            data   = fetch_morning_commodity()
            report = build_morning_commodity(data)
        elif report_type == '自选股':
            data   = fetch_watchlist()
            report = build_watchlist(data)
        elif report_type == '复盘':
            data   = fetch_review()
            report = build_review(data)
        else:
            return

        send_text_message(token, open_id, truncate_reply(report))
    except Exception as e:
        send_text_message(token, open_id, f"❌ 报告生成失败：{e}")


# 按需报告的触发关键词
_REPORT_CMDS = {
    '晨报':  '晨报',
    '股票晨报': '晨报',
    '商品报': '商品报',
    '大宗商品': '商品报',
    '自选股': '自选股',
    '自选股日报': '自选股',
    '复盘':  '复盘',
    '今日复盘': '复盘',
}


def handle_message_async(open_id: str, raw_text: str):
    token = get_tenant_access_token(APP_ID, APP_SECRET)
    if not token:
        return

    # 自动注册用户（首次发消息即注册，供定时任务主动推送）
    _register_user(open_id)

    text = raw_text.strip()

    # ① 系统类指令
    if text == '状态':
        send_text_message(token, open_id, cmd_status())
        return
    if text == '目录':
        send_text_message(token, open_id, cmd_directory())
        return
    if text == '帮助':
        send_text_message(token, open_id, cmd_help())
        return

    # ② 备忘录快捷存储（零 Token，直接写文件）
    if (text.startswith('memo ') or text.startswith('memo\n')
            or text.startswith('备忘 ') or text.startswith('备忘\n')):
        parts = text.split(None, 1)
        memo_content = parts[1].strip() if len(parts) > 1 else ''
        if memo_content:
            sys.path.insert(0, _SHARED_DIR)
            from memo_handler import save_memo
            rel_path, git_hash = save_memo(memo_content, KB_PATH)
            send_text_message(token, open_id,
                              f"📝 已记录\n📁 {rel_path}\n📌 git: {git_hash}")
        else:
            send_text_message(token, open_id, "⚠️ memo 后请附上内容")
        return

    # ③ 按需报告命令
    if text in _REPORT_CMDS:
        report_type = _REPORT_CMDS[text]
        send_text_message(token, open_id, f"⏳ 正在生成{report_type}，数据抓取中（约30-60秒）...")
        t = threading.Thread(target=_run_report, args=(report_type, open_id, token), daemon=True)
        t.start()
        return

    # ③ 确认 / 取消待写入操作
    if text in ('确认', 'yes', 'YES', '✅'):
        with _pending_lock:
            pending = _pending_writes.pop(open_id, None)
        if pending:
            result = write_kb_file(pending['file_path'], pending['content'])
            send_text_message(token, open_id, result)
        else:
            send_text_message(token, open_id, "⚠️ 没有待确认的写入操作")
        return

    if text in ('取消', 'no', 'NO', '❌'):
        with _pending_lock:
            _pending_writes.pop(open_id, None)
        send_text_message(token, open_id, "已取消写入操作。")
        return

    # ③ 处理中提示
    send_text_message(token, open_id, "⏳ 处理中，请稍候...")

    # ④ 解析指令前缀
    prefix = ''
    content = text
    for p in ['分析', '录入', '更新', '查找', '总结']:
        if text.startswith(p + '：') or text.startswith(p + ':'):
            prefix = p
            content = text[len(p) + 1:].strip()
            break

    # ⑤ 调用 DeepSeek
    messages  = build_messages(prefix, content)
    raw_reply = call_deepseek(messages)

    # ⑥ 写入操作：解析计划，等待确认
    if prefix in ('录入', '更新'):
        parsed = parse_write_plan(raw_reply)
        if parsed:
            explanation, file_path, file_content = parsed
            with _pending_lock:
                _pending_writes[open_id] = {
                    'file_path': file_path,
                    'content':   file_content,
                }
            preview = file_content[:400] + ('…' if len(file_content) > 400 else '')
            reply = (
                f"📝 写入计划\n{explanation}\n\n"
                f"目标文件：{file_path}\n\n"
                f"内容预览：\n{preview}\n\n"
                f"─────\n回复【确认】执行写入，回复【取消】放弃"
            )
            send_text_message(token, open_id, truncate_reply(reply))
            return
        # 解析失败则直接返回 AI 建议
        send_text_message(token, open_id, truncate_reply(f"📝 {raw_reply}"))
        return

    # ⑦ 普通回复
    if raw_reply.startswith('❌') or raw_reply.startswith('⚠️'):
        reply = truncate_reply(raw_reply)
    else:
        emoji = PREFIX_EMOJI.get(prefix, '✅')
        reply = truncate_reply(f"{emoji} {raw_reply}")

    send_text_message(token, open_id, reply)


# ── 飞书长连接事件处理 ────────────────────────────────────────────────────────

def on_message_receive(data: P2ImMessageReceiveV1) -> None:
    try:
        if data.event is None:
            return
        message = data.event.message
        sender  = data.event.sender
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

        msg_id = message.message_id or ''
        if msg_id:
            with _msg_id_lock:
                if msg_id in _processed_msg_ids:
                    return
                _processed_msg_ids.add(msg_id)
                if len(_processed_msg_ids) > 1000:
                    _processed_msg_ids.clear()
                    _processed_msg_ids.add(msg_id)

        t = threading.Thread(
            target=handle_message_async,
            args=(open_id, raw_text),
            daemon=True
        )
        t.start()

    except Exception as e:
        print(f"[bot_deepseek] 消息处理异常: {e}")


# ── 启动长连接 ────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print(f"[bot_deepseek] 启动中，知识库 {KB_PATH}，模型 {DEEPSEEK_MODEL}")

    event_handler = (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_im_message_receive_v1(on_message_receive)
        .build()
    )

    ws_client = lark.ws.Client(
        APP_ID,
        APP_SECRET,
        event_handler=event_handler,
        log_level=lark.LogLevel.INFO
    )
    ws_client.start()
