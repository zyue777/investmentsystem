"""通用网页内容抓取与提炼工具。

支持任意公开网页（非微信）：学术论文、博客、新闻、报告等。
用法：给 Bot 发送网页 URL，Bot 会抓取内容并提炼摘要/翻译/重点存入 MEMO。
"""
import datetime
import requests
from core.context import ToolManifest

MANIFEST = ToolManifest(name="web_fetch", description="通用网页内容抓取与正文提取")

# ── 内置 Prompt 模板 ─────────────────────────────────────────────────────────
# Bot 收到网页内容后，使用此 Prompt 进行提炼与翻译。
# 可按需调整语气、输出格式。
DISTILL_PROMPT = """你是一位专业的研究助手，擅长将英文长文提炼成简洁的中文阅读笔记。

请对以下网页正文完成三件事：
1. **一句话摘要**（≤50字）：用最精炼的语言概括核心主旨。
2. **核心要点**（5-10条，每条≤80字）：用中文列出最有价值的观点或论据，保留关键案例/数据/金句。
3. **启发与行动建议**（2-3条）：结合内容，提炼对读者最有实践价值的洞见。

输出格式为 Markdown，不要复述原文，用你自己的语言提炼。

---
文章标题：{title}
文章来源：{url}

正文内容：
{content}
"""


def fetch_page(url: str) -> dict:
    """抓取任意公开网页，返回 {'title', 'date', 'content', 'url'} 或 {'error'}。"""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }

    try:
        resp = requests.get(url, headers=headers, timeout=20, allow_redirects=True)
        resp.raise_for_status()
    except Exception as e:
        return {"error": f"下载失败: {e}"}

    # 编码修正
    if resp.encoding and resp.encoding.lower() in ("iso-8859-1", "latin-1"):
        resp.encoding = resp.apparent_encoding

    html = resp.text

    try:
        from bs4 import BeautifulSoup
        import html2text
    except ImportError:
        return {"error": "需要安装 beautifulsoup4 和 html2text"}

    soup = BeautifulSoup(html, "html.parser")

    # ── 获取标题 ──────────────────────────────────────────────────────────────
    title = "未命名页面"
    # 优先 og:title，其次 <title>，最后 h1
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        title = og_title["content"].strip()
    elif soup.title and soup.title.string:
        title = soup.title.string.strip()
    elif soup.find("h1"):
        title = soup.find("h1").get_text(strip=True)

    # ── 获取日期 ──────────────────────────────────────────────────────────────
    date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    # 尝试 og:article:published_time
    pub_meta = soup.find("meta", property="article:published_time")
    if pub_meta and pub_meta.get("content"):
        date_str = pub_meta["content"][:10]

    # ── 提取正文 ──────────────────────────────────────────────────────────────
    # 移除干扰元素
    for tag in soup.find_all(["script", "style", "nav", "header",
                               "footer", "aside", "form", "noscript"]):
        tag.decompose()

    # 尝试语义容器：article > main > body
    body_el = (
        soup.find("article")
        or soup.find("main")
        or soup.find("div", {"role": "main"})
        or soup.find("div", id="content")
        or soup.find("div", class_=lambda c: c and "content" in c.lower())
        or soup.body
    )

    if not body_el:
        return {"error": "无法提取正文内容"}

    h2t = html2text.HTML2Text()
    h2t.ignore_links = True        # 阅读笔记不需要超链接
    h2t.ignore_images = True       # 不需要图片
    h2t.body_width = 0             # 不强制换行
    h2t.ignore_tables = False
    markdown_content = h2t.handle(str(body_el))

    # 去除过多空行
    import re
    markdown_content = re.sub(r"\n{3,}", "\n\n", markdown_content).strip()

    return {
        "title": title,
        "date": date_str,
        "content": markdown_content,
        "url": url,
        "distill_prompt": DISTILL_PROMPT.format(
            title=title,
            url=url,
            content=markdown_content[:8000],   # 避免超长 context
        ),
    }


def handle(ctx):
    return ctx
