"""会话记忆工具 — 研究模式等多轮对话场景的持久化存储。

用法：
    from tools.session_memory import create_session, append_turn, get_active_session
    session = create_session(user_id, "原奶行业周期", "investment")

存储：JSON 文件 → bots/<bot>/memory/sessions/<user_id>.json
特性：
  - 文件持久化（进程重启不丢失）
  - 24h 自动过期（防止孤儿 Session）
  - 单用户单 Session（新建自动关旧）
"""
import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from core.context import ToolManifest

MANIFEST = ToolManifest(name="session_memory", description="多轮对话会话记忆存储")

# 会话文件根目录（由各 Bot 的 memory/sessions/ 下按 user_id 存储）
_SESSIONS_BASE = Path(__file__).resolve().parent.parent / 'bots'
_SESSION_EXPIRE_HOURS = 24
# 上下文压缩阈值：超过此轮数后，早期 turn 自动压缩为摘要
COMPRESS_AFTER_TURNS = 5


def _session_dir(bot_name: str) -> Path:
    """获取 Bot 的 session 存储目录。"""
    d = _SESSIONS_BASE / bot_name / 'memory' / 'sessions'
    d.mkdir(parents=True, exist_ok=True)
    return d


def _session_file(bot_name: str, user_id: str) -> Path:
    """获取用户的 session 文件路径。"""
    safe_uid = user_id.replace('/', '_').replace('\\', '_')
    return _session_dir(bot_name) / f'{safe_uid}.json'


def _load(bot_name: str, user_id: str) -> dict | None:
    """从文件加载 Session。返回 None 表示无 Session 或已过期。"""
    f = _session_file(bot_name, user_id)
    if not f.exists():
        return None
    try:
        data = json.loads(f.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, OSError):
        return None
    # 检查过期
    last_active = data.get('last_active', data.get('created_at', ''))
    if last_active:
        try:
            last_dt = datetime.fromisoformat(last_active)
            if datetime.now() - last_dt > timedelta(hours=_SESSION_EXPIRE_HOURS):
                f.unlink(missing_ok=True)
                return None
        except ValueError:
            pass
    return data


def _save(bot_name: str, user_id: str, data: dict) -> None:
    """将 Session 写入文件。"""
    f = _session_file(bot_name, user_id)
    f.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


# ── 全局 Session 索引（内存缓存，加速 Router 查询）──
# 格式：{user_id: {"bot_name": str, "target_skill": str}}
_active_index: dict[str, dict] = {}


def create_session(user_id: str, topic: str, bot_name: str,
                   target_skill: str = 'research_session') -> dict:
    """创建新会话。如果已有活跃 Session，自动清理旧的。"""
    # 清理旧 Session（如果有）
    old = _load(bot_name, user_id)
    if old:
        clear_session(user_id, bot_name)

    data = {
        'session_id': str(uuid.uuid4())[:8],
        'user_id': user_id,
        'bot_name': bot_name,
        'topic': topic,
        'target_skill': target_skill,
        'created_at': datetime.now().isoformat(),
        'last_active': datetime.now().isoformat(),
        'turns': [],
    }
    _save(bot_name, user_id, data)
    _active_index[user_id] = {
        'bot_name': bot_name,
        'target_skill': target_skill,
    }
    return data


def append_turn(user_id: str, bot_name: str,
                user_input: str, ai_response: str,
                web_urls: list[dict] | None = None,
                kb_refs: list[str] | None = None) -> None:
    """追加一轮对话到 Session。"""
    data = _load(bot_name, user_id)
    if not data:
        return

    turn = {
        'turn_id': len(data['turns']) + 1,
        'user_input': user_input,
        'ai_response': ai_response,
        'timestamp': datetime.now().isoformat(),
    }
    if web_urls:
        turn['web_urls'] = web_urls
    if kb_refs:
        turn['kb_refs'] = kb_refs

    data['turns'].append(turn)
    data['last_active'] = datetime.now().isoformat()
    _save(bot_name, user_id, data)


def get_history(user_id: str, bot_name: str) -> list[dict]:
    """获取 Session 中的所有对话轮次（构建 prompt 用）。"""
    data = _load(bot_name, user_id)
    if not data:
        return []
    return data.get('turns', [])


def get_history_as_prompt(user_id: str, bot_name: str,
                          max_chars: int = 15000) -> str:
    """将对话历史格式化为 prompt 片段。

    策略：
    - 前 COMPRESS_AFTER_TURNS 轮全量
    - 超出部分只保留用户问题 + AI 回答前200字（自动压缩）
    - 总长度限制 max_chars
    """
    turns = get_history(user_id, bot_name)
    if not turns:
        return ''

    lines = ['## 之前的讨论记录\n']
    total_len = 0

    for i, turn in enumerate(turns):
        if i < COMPRESS_AFTER_TURNS:
            # 全量
            block = (f"### 第{turn['turn_id']}轮\n"
                     f"**用户**: {turn['user_input']}\n\n"
                     f"**AI**: {turn['ai_response']}\n")
        else:
            # 压缩：只保留前200字
            resp_preview = turn['ai_response'][:200] + '...' \
                if len(turn['ai_response']) > 200 else turn['ai_response']
            block = (f"### 第{turn['turn_id']}轮（摘要）\n"
                     f"**用户**: {turn['user_input']}\n\n"
                     f"**AI**: {resp_preview}\n")

        if total_len + len(block) > max_chars:
            lines.append('\n（更早的讨论已省略以控制长度）')
            break
        lines.append(block)
        total_len += len(block)

    return '\n'.join(lines)


def get_full_session(user_id: str, bot_name: str) -> dict | None:
    """获取完整 Session 对象（归档用）。"""
    return _load(bot_name, user_id)


def get_active_session(user_id: str) -> dict | None:
    """检查用户是否有活跃 Session。Router 用此函数做拦截判断。

    优先查内存索引（快），miss 时扫描磁盘（慢但可靠）。
    返回 {'bot_name': str, 'target_skill': str, 'topic': str} 或 None。
    """
    # 1. 内存索引命中
    if user_id in _active_index:
        idx = _active_index[user_id]
        data = _load(idx['bot_name'], user_id)
        if data:
            return {
                'bot_name': data['bot_name'],
                'target_skill': data['target_skill'],
                'topic': data['topic'],
            }
        else:
            # 文件已过期或被删，清理索引
            del _active_index[user_id]
            return None

    # 2. 内存 miss → 扫描所有 Bot 目录（进程重启后的恢复机制）
    for bot_dir in _SESSIONS_BASE.iterdir():
        if not bot_dir.is_dir() or bot_dir.name.startswith('_'):
            continue
        sess_dir = bot_dir / 'memory' / 'sessions'
        if not sess_dir.exists():
            continue
        safe_uid = user_id.replace('/', '_').replace('\\', '_')
        f = sess_dir / f'{safe_uid}.json'
        if f.exists():
            try:
                data = json.loads(f.read_text(encoding='utf-8'))
                # 检查过期
                last_active = data.get('last_active', '')
                if last_active:
                    last_dt = datetime.fromisoformat(last_active)
                    if datetime.now() - last_dt > timedelta(hours=_SESSION_EXPIRE_HOURS):
                        f.unlink(missing_ok=True)
                        continue
                # 恢复索引
                _active_index[user_id] = {
                    'bot_name': data['bot_name'],
                    'target_skill': data['target_skill'],
                }
                return {
                    'bot_name': data['bot_name'],
                    'target_skill': data['target_skill'],
                    'topic': data['topic'],
                }
            except (json.JSONDecodeError, OSError, ValueError):
                continue
    return None


def get_all_urls(user_id: str, bot_name: str) -> list[dict]:
    """收集 Session 中所有轮次的参考链接（归档用）。"""
    data = _load(bot_name, user_id)
    if not data:
        return []
    urls = []
    seen = set()
    for turn in data.get('turns', []):
        for u in turn.get('web_urls', []):
            url_str = u.get('url', '')
            if url_str and url_str not in seen:
                seen.add(url_str)
                urls.append(u)
    return urls


def clear_session(user_id: str, bot_name: str = '') -> None:
    """清空 Session。bot_name 为空时从索引中查找。"""
    if not bot_name and user_id in _active_index:
        bot_name = _active_index[user_id]['bot_name']
    if bot_name:
        f = _session_file(bot_name, user_id)
        f.unlink(missing_ok=True)
    _active_index.pop(user_id, None)


def handle(ctx):
    """Tool 注册需要的 handle 函数（session_memory 不直接作为 Skill 使用）。"""
    return ctx
