"""文件读取工具 — 统一的文件读取封装。"""
from pathlib import Path
from core.context import ToolManifest

MANIFEST = ToolManifest(name="file_read", description="文件读取（自动编码检测）")


def read_file(path: str, max_chars: int = 0) -> str:
    """读取文件内容，支持自动编码检测。"""
    p = Path(path)
    if not p.exists():
        return f"⚠️ 文件不存在: {path}"
    try:
        content = p.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        try:
            content = p.read_text(encoding='gbk')
        except Exception:
            return f"⚠️ 无法读取文件（编码问题）: {path}"
    if max_chars and len(content) > max_chars:
        content = content[:max_chars] + f"\n\n…（截断，共{len(content)}字符）"
    return content


def read_lines(path: str, start: int = 0, end: int = 0) -> str:
    """读取文件指定行范围。"""
    content = read_file(path)
    if content.startswith("⚠️"):
        return content
    lines = content.split('\n')
    if end:
        lines = lines[start:end]
    return '\n'.join(lines)


def handle(ctx):
    return ctx
