"""知识库搜索工具 — 基于 grep 的本地搜索。"""
import subprocess
from pathlib import Path
from core.context import ToolManifest

MANIFEST = ToolManifest(name="search_grep", description="知识库grep搜索")


def search(keyword: str, search_path: str, max_results: int = 30) -> list[dict]:
    """搜索知识库，返回结构化结果列表。"""
    try:
        r = subprocess.run(
            ['grep', '-rn', '--include=*.md', '-i', '--color=never',
             keyword, search_path],
            capture_output=True, text=True, timeout=10
        )
        lines = r.stdout.strip().split('\n')
        if not lines or not lines[0]:
            return []

        results = []
        for line in lines[:max_results]:
            parts = line.split(':', 2)
            if len(parts) >= 3:
                fpath = Path(parts[0])
                try:
                    rel = str(fpath.relative_to(search_path))
                except ValueError:
                    rel = str(fpath)
                results.append({
                    'file': rel,
                    'line': int(parts[1]),
                    'text': parts[2].strip()[:150],
                })
        return results
    except Exception as e:
        print(f"[search_grep] 搜索出错: {e}")
        return []


def search_formatted(keyword: str, search_path: str) -> str:
    """搜索知识库，返回格式化文本（兼容旧接口）。"""
    results = search(keyword, search_path)
    if not results:
        return f"🔍 未找到包含'{keyword}'的内容"

    seen_files = set()
    lines = []
    for r in results:
        if r['file'] not in seen_files:
            lines.append(f"\n📄 {r['file']}")
            seen_files.add(r['file'])
        if len(lines) < 20:
            lines.append(f"  L{r['line']}: {r['text'][:100]}")

    return (f"🔍 搜索'{keyword}'（{len(results)}条匹配，"
            f"{len(seen_files)}个文件）\n" + '\n'.join(lines))


def handle(ctx):
    return ctx
