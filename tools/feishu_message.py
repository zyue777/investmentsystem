"""飞书消息发送。"""
import json
import requests
from core.context import ToolManifest

MANIFEST = ToolManifest(name="feishu_message", description="飞书文本消息发送")

REPLY_MAX_LEN = 2800  # 飞书消息安全长度


def send_text(token: str, open_id: str, text: str) -> bool:
    """向指定用户发送文本消息，超长自动分段。"""
    if not text:
        return True
    if len(text) <= REPLY_MAX_LEN:
        return _send_single(token, open_id, text)
    # 分段发送
    chunks = _split_text(text, REPLY_MAX_LEN)
    ok = True
    for i, chunk in enumerate(chunks):
        header = f"📄 [{i+1}/{len(chunks)}]\n"
        if not _send_single(token, open_id, header + chunk):
            ok = False
    return ok


def _send_single(token: str, open_id: str, text: str) -> bool:
    """发送单条文本消息。"""
    url = "https://open.feishu.cn/open-apis/im/v1/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    payload = {
        "receive_id": open_id,
        "msg_type": "text",
        "content": json.dumps({"text": text}, ensure_ascii=False)
    }
    params = {"receive_id_type": "open_id"}
    try:
        resp = requests.post(url, headers=headers, json=payload,
                             params=params, timeout=10)
        data = resp.json()
        if data.get("code") == 0:
            return True
        else:
            print(f"[feishu_message] 发送消息失败: {data}")
            return False
    except Exception as e:
        print(f"[feishu_message] 发送消息异常: {e}")
        return False


def _split_text(text: str, max_len: int) -> list:
    """按段落分割长文本。"""
    paragraphs = text.split('\n\n')
    chunks, current = [], ''
    for p in paragraphs:
        if len(current) + len(p) + 2 > max_len and current:
            chunks.append(current)
            current = p
        else:
            current = current + '\n\n' + p if current else p
    if current:
        chunks.append(current)
    return chunks or [text[:max_len]]


def handle(ctx):
    """Tool 注册表要求的 handle 占位。"""
    return ctx
