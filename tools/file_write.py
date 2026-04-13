"""文件写入 + Git 提交工具。"""
import re
import subprocess
from pathlib import Path
from core.context import ToolManifest

MANIFEST = ToolManifest(name="file_write", description="文件写入+Git提交")


def write_file(path: str, content: str, mkdir: bool = True) -> bool:
    """写入文件，自动创建父目录。"""
    p = Path(path)
    try:
        if mkdir:
            p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding='utf-8')
        return True
    except Exception as e:
        print(f"[file_write] 写入失败: {e}")
        return False


def append_file(path: str, content: str, mkdir: bool = True) -> bool:
    """追加内容到文件。"""
    p = Path(path)
    try:
        if mkdir:
            p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, 'a', encoding='utf-8') as f:
            f.write(content)
        return True
    except Exception as e:
        print(f"[file_write] 追加失败: {e}")
        return False


def git_commit(file_path: str, repo_path: str, message: str) -> str:
    """对文件执行 git add + commit，返回 hash。"""
    try:
        subprocess.run(['git', 'add', file_path],
                       cwd=repo_path, capture_output=True, timeout=10)
        r = subprocess.run(['git', 'commit', '-m', message],
                           cwd=repo_path, capture_output=True, text=True,
                           timeout=10)
        match = re.search(r'[a-f0-9]{7,}', r.stdout)
        return match.group(0) if match else '已提交'
    except Exception as e:
        print(f"[file_write] git 操作失败: {e}")
        return '(git失败)'


def handle(ctx):
    return ctx
