"""微信公众号文章抓取工具。

功能：
- 广告图片过滤（data-w < 400 / 二维码检测）
- 合格图片自动调用 Vision AI (kimi-k2.6) 识别表格/文字
- OCR 结果内嵌到 Markdown 正文，供下游 AI 蒸馏时直接读取
"""
import os
import re
import base64
import datetime
import requests
from core.context import ToolManifest

MANIFEST = ToolManifest(name="wechat_fetch", description="微信公众号文章抓取（含广告过滤+图表OCR）")

VISION_MODEL = "kimi-k2.6"


def _try_ocr_image(cdn_url: str, api_key: str, base_url: str) -> str:
    """下载图片并调用 Vision AI 识别表格/文字。失败静默返回空。"""
    if not api_key or not base_url:
        return ""
    try:
        from openai import OpenAI
    except ImportError:
        return ""

    try:
        # 下载图片（必须带 Referer）
        img_resp = requests.get(cdn_url, headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://mp.weixin.qq.com/",
        }, timeout=15)
        img_resp.raise_for_status()
        if len(img_resp.content) < 500:  # 太小，无意义
            return ""
        img_b64 = base64.b64encode(img_resp.content).decode("utf-8")

        client = OpenAI(api_key=api_key, base_url=base_url)
        resp = client.chat.completions.create(
            model=VISION_MODEL,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
                    {"type": "text", "text": (
                        "请识别这张图片中的内容。\n"
                        "- 若包含数据表格或数字图表：完整转写为 Markdown 表格，保留所有数字和文字，不要省略任何行列。\n"
                        "- 若包含有意义的纯文字段落：直接输出文字内容。\n"
                        "- 若是装饰图、配图、示意图、无具体数据的图片：只输出三个字 无文字内容\n"
                        "直接输出结果，不要加解释、不要加前缀。"
                    )}
                ]
            }],
            max_tokens=1500,
            timeout=30
        )
        result = resp.choices[0].message.content.strip()
        if "无文字内容" in result and len(result) < 20:
            return ""
        return result
    except Exception:
        return ""


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

    # ── 广告过滤 + 图片占位符 ──────────────────────────────
    image_placeholders = {}  # {占位符: cdn_url}
    img_counter = 0

    for img in content_el.find_all("img"):
        data_src = img.get("data-src")
        if not data_src:
            img.decompose()
            continue

        data_w = img.get("data-w")
        data_ratio = img.get("data-ratio")

        is_ad = False
        if data_w and data_w.isdigit():
            w = int(data_w)
            if w < 400:
                is_ad = True
            elif w < 500 and data_ratio:
                try:
                    ratio = float(data_ratio)
                    if 0.9 <= ratio <= 1.1:
                        is_ad = True
                except ValueError:
                    pass

        if is_ad:
            img.decompose()
            continue

        img_counter += 1
        placeholder = f"[[IMG_PLACEHOLDER_{img_counter}]]"
        image_placeholders[placeholder] = data_src
        img.replace_with(placeholder)

    # 取消隐藏
    if "style" in content_el.attrs:
        content_el["style"] = content_el["style"].replace("visibility: hidden", "")

    # 转 Markdown
    h2t = html2text.HTML2Text()
    h2t.ignore_links = False
    h2t.ignore_images = True  # 图片由占位符接管
    h2t.body_width = 0
    markdown_content = h2t.handle(str(content_el))

    # ── Vision OCR：识别图表 ──────────────────────────────
    api_key = os.environ.get("AI_API_KEY", "")
    base_url = os.environ.get("AI_API_BASE", "")

    for placeholder, cdn_url in image_placeholders.items():
        ocr_text = _try_ocr_image(cdn_url, api_key, base_url)
        if ocr_text:
            block = "\n\n> 🤖 AI图表识别：\n"
            for line in ocr_text.splitlines():
                block += f"> {line}\n"
            block += "\n"
        else:
            block = ""  # 装饰图/配图：直接移除占位符，不留痕迹
        markdown_content = markdown_content.replace(placeholder, block)

    return {
        'title': title,
        'date': date_str,
        'content': markdown_content,
        'url': url,
    }


def handle(ctx):
    return ctx
