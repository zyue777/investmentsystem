"""飞书 tenant_access_token 获取。"""
import requests
from core.context import ToolManifest

MANIFEST = ToolManifest(name="feishu_token", description="获取飞书tenant_access_token")


def get_token(app_id: str, app_secret: str) -> str:
    """获取飞书 tenant_access_token，失败时返回空字符串。"""
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    payload = {"app_id": app_id, "app_secret": app_secret}
    try:
        resp = requests.post(url, json=payload, timeout=10)
        data = resp.json()
        if data.get("code") == 0:
            return data.get("tenant_access_token", "")
        else:
            print(f"[feishu_token] 获取 token 失败: {data}")
            return ""
    except Exception as e:
        print(f"[feishu_token] 请求异常: {e}")
        return ""


def handle(ctx):
    """Tool 注册表要求的 handle 占位（实际通过 get_token 直接调用）。"""
    return ctx
