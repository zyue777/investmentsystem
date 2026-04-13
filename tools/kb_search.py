"""知识库深度搜索工具 — grep 匹配 + 文件内容摘要。

与 search_grep.py 的区别：
  - search_grep：返回匹配行（粗搜，适合定位文件）
  - kb_search：返回匹配文件的内容摘要（深搜，适合生成 AI 上下文）

Token 控制：每个文件最多读取 max_chars_per_file 字符，最多 max_files 个文件。
"""
from pathlib import Path
from core.context import ToolManifest

MANIFEST = ToolManifest(name="kb_search", description="知识库深度搜索")


def search_kb(query: str, ws: str, max_files: int = 3,
              max_chars_per_file: int = 1500) -> str:
    """搜索知识库，返回拼接好的上下文文本（Token 已控制）。
    
    返回空字符串表示无匹配。
    """
    from tools.search_grep import search

    kb_path = str(Path(ws) / '知识库')
    hits = search(query, kb_path, max_results=15)

    if not hits:
        return ""

    # 按文件去重，读取每个文件的内容摘要
    seen = set()
    context_parts = []
    for hit in hits:
        if hit['file'] in seen or len(seen) >= max_files:
            continue
        seen.add(hit['file'])
        full_path = Path(ws) / '知识库' / hit['file']
        if full_path.exists():
            content = full_path.read_text(encoding='utf-8')[:max_chars_per_file]
            context_parts.append(f"📄 {hit['file']}\n{content}")

    if not context_parts:
        return ""

    header = f"📚 **知识库匹配**（共 {len(context_parts)} 份文档）：\n"
    return header + '\n\n---\n\n'.join(context_parts)


def handle(ctx):
    return ctx
