"""飞书文件上传与发送。"""
import json
import os
import requests
from core.context import ToolManifest

MANIFEST = ToolManifest(name="feishu_file", description="飞书文件上传与发送")


def upload_file(token: str, file_path: str, file_name: str) -> str:
    """上传文件到飞书服务器，返回 file_key。"""
    url = "https://open.feishu.cn/open-apis/im/v1/files"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        with open(file_path, 'rb') as f:
            files = {"file": (file_name, f)}
            data = {"file_type": "stream", "file_name": file_name}
            resp = requests.post(url, headers=headers, data=data,
                                 files=files, timeout=30)
        result = resp.json()
        if result.get("code") == 0:
            return result.get("data", {}).get("file_key", "")
        else:
            print(f"[feishu_file] 上传文件失败: {result}")
            return ""
    except Exception as e:
        print(f"[feishu_file] 上传文件异常: {e}")
        return ""


def send_file(token: str, open_id: str, file_key: str) -> bool:
    """向指定用户发送文件消息。"""
    url = "https://open.feishu.cn/open-apis/im/v1/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    payload = {
        "receive_id": open_id,
        "msg_type": "file",
        "content": json.dumps({"file_key": file_key}, ensure_ascii=False)
    }
    params = {"receive_id_type": "open_id"}
    try:
        resp = requests.post(url, headers=headers, json=payload,
                             params=params, timeout=10)
        data = resp.json()
        if data.get("code") == 0:
            return True
        else:
            print(f"[feishu_file] 发送文件消息失败: {data}")
            return False
    except Exception as e:
        print(f"[feishu_file] 发送文件消息异常: {e}")
        return False


def send_file_to_user(token: str, open_id: str, file_path: str) -> bool:
    """便捷函数：上传本地文件并发送给用户。"""
    file_name = os.path.basename(file_path)
    file_key = upload_file(token, file_path, file_name)
    if not file_key:
        print(f"[feishu_file] 上传失败，无法发送文件: {file_path}")
        return False
    return send_file(token, open_id, file_key)


def handle(ctx):
    """Tool 注册表要求的 handle 占位。"""
    return ctx
