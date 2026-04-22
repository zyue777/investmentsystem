"""Claude CLI Provider — 通过本地 Relay 服务调用（绕过云端 claude.ai 封锁）。

云端无法直接运行 claude CLI（Cloudflare 封锁 claude.ai OAuth 验证），
因此改为 HTTP 请求转发到本地电脑运行的 claude_relay_server.py。

环境变量：
  CLAUDE_RELAY_URL    本地 relay 服务的公网地址（cloudflared 生成）
  CLAUDE_RELAY_SECRET 鉴权密钥（默认 invest-relay-2026）
"""
import os
import requests
from providers.base import ProviderBase
from core.context import ProviderManifest

MANIFEST = ProviderManifest(name="claude_cli", description="本地Claude CLI转发调用")

_DEFAULT_SECRET = "invest-relay-2026"


class ClaudeCLIProvider(ProviderBase):
    def call(self, prompt: str, timeout: int = 300, cwd: str = "", **kwargs) -> str:
        relay_url = os.environ.get("CLAUDE_RELAY_URL", "").rstrip("/")
        secret = os.environ.get("CLAUDE_RELAY_SECRET", _DEFAULT_SECRET)

        if not relay_url:
            return "❌ 未设置 CLAUDE_RELAY_URL（请启动本地 relay 服务并配置）"

        try:
            resp = requests.post(
                f"{relay_url}/call",
                json={"prompt": prompt, "timeout": timeout, "secret": secret},
                timeout=timeout + 10,
            )
            if resp.status_code == 401:
                return "❌ Relay 鉴权失败，检查 CLAUDE_RELAY_SECRET"
            if resp.status_code == 504:
                return f"❌ 超时（{timeout}s）"
            if resp.status_code != 200:
                return f"❌ Relay 错误 {resp.status_code}: {resp.text[:200]}"
            data = resp.json()
            if "error" in data:
                return f"❌ {data['error']}"
            result = data.get("result", "（无输出）")
            if "rate" in result.lower() or "limit" in result.lower():
                return "⏸️ AI 额度暂时耗尽"
            return result
        except requests.Timeout:
            return f"❌ Relay 连接超时（本地服务是否在线？）"
        except requests.ConnectionError:
            return "❌ 无法连接 Relay 服务（本地电脑是否开机？cloudflared 是否运行？）"
        except Exception as e:
            return f"❌ 异常: {e}"

    def check_available(self) -> bool:
        relay_url = os.environ.get("CLAUDE_RELAY_URL", "").rstrip("/")
        if not relay_url:
            return False
        try:
            resp = requests.get(f"{relay_url}/health", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False


def create_provider():
    return ClaudeCLIProvider()
