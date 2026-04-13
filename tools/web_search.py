"""联网搜索工具 — DuckDuckGo 免费搜索（无需 API Key）。

用法：
    from tools.web_search import search_web
    results = search_web("A股 宏观 最新政策")

返回：[{'title': '...', 'url': '...', 'snippet': '...'}, ...]
Token 控制：snippet 截取 200 字，默认最多 5 条。
"""
from core.context import ToolManifest

MANIFEST = ToolManifest(name="web_search", description="DuckDuckGo联网搜索")


def search_web(query: str, max_results: int = 5) -> list[dict]:
    """执行联网搜索，返回结构化结果。失败时返回空列表（不抛异常）。"""
    try:
        from ddgs import DDGS
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append({
                    'title': r.get('title', ''),
                    'url': r.get('href', ''),
                    'snippet': r.get('body', '')[:200],
                })
        return results
    except Exception as e:
        print(f"[web_search] 搜索失败: {e}")
        return []


def format_results(results: list[dict]) -> str:
    """将搜索结果格式化为 Markdown 文本（供拼入 prompt 用）。"""
    if not results:
        return ""
    lines = ["🌐 **联网搜索结果**（以下信息来源于互联网，仅供参考）：\n"]
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. **{r['title']}**")
        lines.append(f"   {r['snippet']}")
        lines.append(f"   来源: {r['url']}\n")
    return '\n'.join(lines)


def handle(ctx):
    return ctx
