# 飞书公共工具函数
# 封装获取 tenant_access_token、发送文本消息、上传文件、发送文件消息

import json
import os
import requests


def get_tenant_access_token(app_id: str, app_secret: str) -> str:
    """
    获取飞书 tenant_access_token
    :return: tenant_access_token 字符串，失败时返回空字符串
    """
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    payload = {"app_id": app_id, "app_secret": app_secret}
    try:
        resp = requests.post(url, json=payload, timeout=10)
        data = resp.json()
        if data.get("code") == 0:
            return data.get("tenant_access_token", "")
        else:
            print(f"[feishu_utils] 获取 token 失败: {data}")
            return ""
    except Exception as e:
        print(f"[feishu_utils] 请求异常: {e}")
        return ""


def send_text_message(token: str, open_id: str, text: str) -> bool:
    """
    向指定用户发送文本消息
    :return: 发送成功返回 True
    """
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
            print(f"[feishu_utils] 发送消息失败: {data}")
            return False
    except Exception as e:
        print(f"[feishu_utils] 发送消息异常: {e}")
        return False


def upload_file(token: str, file_path: str, file_name: str) -> str:
    """
    上传文件到飞书服务器，返回 file_key
    :param file_path: 本地文件绝对路径
    :param file_name: 文件名（含后缀，如 report.md）
    :return: file_key 字符串，失败时返回空字符串
    """
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
            file_key = result.get("data", {}).get("file_key", "")
            return file_key
        else:
            print(f"[feishu_utils] 上传文件失败: {result}")
            return ""
    except Exception as e:
        print(f"[feishu_utils] 上传文件异常: {e}")
        return ""


def send_file_message(token: str, open_id: str, file_key: str) -> bool:
    """
    向指定用户发送文件消息
    :param file_key: 通过 upload_file 获取的 file_key
    :return: 发送成功返回 True
    """
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
            print(f"[feishu_utils] 发送文件消息失败: {data}")
            return False
    except Exception as e:
        print(f"[feishu_utils] 发送文件消息异常: {e}")
        return False


def send_file_to_user(token: str, open_id: str, file_path: str) -> bool:
    """
    便捷函数：上传本地文件并发送给用户
    :param file_path: 本地文件绝对路径
    :return: 发送成功返回 True
    """
    file_name = os.path.basename(file_path)
    file_key = upload_file(token, file_path, file_name)
    if not file_key:
        print(f"[feishu_utils] 上传失败，无法发送文件: {file_path}")
        return False
    return send_file_message(token, open_id, file_key)
