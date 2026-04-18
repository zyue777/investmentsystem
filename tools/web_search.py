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
        import requests
        from bs4 import BeautifulSoup
        
        # 使用 DuckDuckGo HTML 端点绕过 API 封锁
        url = "https://html.duckduckgo.com/html/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        data = {"q": query}
        
        res = requests.post(url, headers=headers, data=data, timeout=15)
        res.raise_for_status()
        
        soup = BeautifulSoup(res.text, "html.parser")
        results = []
        
        for item in soup.select(".result"):
            if len(results) >= max_results:
                break
            title_el = item.select_one(".result__title > a")
            snippet_el = item.select_one(".result__snippet")
            url_el = item.select_one(".result__url")
            
            if title_el and snippet_el:
                href = url_el.get('href', '').strip() if url_el else ''
                # 提取真实的 url，部分鸭鸭链接自带前缀 /url?q=
                if 'url?q=' in href:
                    href = href.split('url?q=')[1].split('&')[0]
                    import urllib.parse
                    href = urllib.parse.unquote(href)
                    
                results.append({
                    'title': title_el.get_text(strip=True),
                    'url': href,
                    'snippet': snippet_el.get_text(strip=True)[:200],
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
