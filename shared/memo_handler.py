# shared/memo_handler.py
# 投资备忘快捷存储 —— 被 bot_claude 和 bot_gemini 共同调用
# 收到 "memo xxx" → 原封不动追加到 08_Investment_Memos/_Inbox/YYYY-MM-DD_投资思考.md
# → git commit → 返回确认信息

import os
import re
import subprocess
from datetime import datetime
from pathlib import Path


def save_memo(text: str, kb_path: str) -> tuple:
    """
    将 text 原封不动追加到当天的 memo 文件中。
    返回 (相对路径, git_hash)
    """
    today = datetime.now().strftime('%Y-%m-%d')
    time_str = datetime.now().strftime('%H:%M')
    rel_path = f"08_Investment_Memos/_Inbox/{today}_投资思考.md"
    full_path = Path(kb_path) / rel_path

    full_path.parent.mkdir(parents=True, exist_ok=True)

    # 如果文件不存在，写入头部
    if not full_path.exists():
        header = f"# {today} 投资思考碎片\n\n"
        full_path.write_text(header, encoding='utf-8')

    # 追加一条记录（用时间戳和分隔线区分）
    entry = f"\n---\n\n**[{time_str}]**\n\n{text}\n"
    with open(full_path, 'a', encoding='utf-8') as f:
        f.write(entry)

    # git commit
    git_hash = _git_commit_memo(full_path, kb_path, f"memo: {today} {time_str}")
    return rel_path, git_hash


def _git_commit_memo(file_path: Path, kb_path: str, message: str) -> str:
    """对 memo 文件执行 git add + commit，返回 hash"""
    try:
        subprocess.run(
            ['git', 'add', str(file_path)],
            cwd=kb_path, capture_output=True, timeout=10
        )
        r = subprocess.run(
            ['git', 'commit', '-m', message],
            cwd=kb_path, capture_output=True, text=True, timeout=10
        )
        match = re.search(r'[a-f0-9]{7,}', r.stdout)
        return match.group(0) if match else '已提交'
    except Exception as e:
        print(f"[memo_handler] git 操作失败: {e}")
        return '(git失败)'
