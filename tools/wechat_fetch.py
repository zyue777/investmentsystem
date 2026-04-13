"""微信公众号文章抓取工具。"""
import re
import datetime
import requests
from core.context import ToolManifest

MANIFEST = ToolManifest(name="wechat_fetch", description="微信公众号文章抓取")


def fetch_article(url: str) -> dict:
    """抓取微信公众号文章，返回 {'title', 'date', 'content', 'url'} 或 {'error'}。"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
    except Exception as e:
        return {'error': f"下载失败: {e}"}

    html = response.text

    try:
        from bs4 import BeautifulSoup
        import html2text
    except ImportError:
        return {'error': "需要安装 beautifulsoup4 和 html2text"}

    soup = BeautifulSoup(html, "html.parser")

    # 获取标题
    title_el = soup.find("h1", class_="rich_media_title")
    if title_el:
        title = title_el.get_text(strip=True)
    else:
        title_el = soup.find("meta", property="og:title")
        title = title_el["content"] if title_el else "未命名微信文章"

    # 获取日期
    date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    ct_match = re.search(r'var ct = "(\d+)";', html)
    if ct_match:
        ts = int(ct_match.group(1))
        if ts > 1000000000:
            date_str = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")

    # 提取正文
    content_el = soup.find("div", id="js_content")
    if not content_el:
        return {'error': "未找到文章正文（可能非图文链接）"}

    # 处理图片懒加载
    for img in content_el.find_all("img"):
        data_src = img.get("data-src")
        if data_src:
            img["src"] = data_src

    # 取消隐藏
    if "style" in content_el.attrs:
        content_el["style"] = content_el["style"].replace("visibility: hidden", "")

    # 转 Markdown
    h2t = html2text.HTML2Text()
    h2t.ignore_links = False
    h2t.ignore_images = False
    h2t.body_width = 0
    markdown_content = h2t.handle(str(content_el))

    return {
        'title': title,
        'date': date_str,
        'content': markdown_content,
        'url': url,
    }


def handle(ctx):
    return ctx
