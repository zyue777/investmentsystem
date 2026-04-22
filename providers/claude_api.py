"""Claude API Provider（直接调用 Anthropic HTTP API，不依赖 Claude CLI）。"""
import os
import requests
from providers.base import ProviderBase
from core.context import ProviderManifest

MANIFEST = ProviderManifest(name="claude_api", description="Anthropic Claude API（直连）")

_DEFAULT_SYSTEM = (
    "你是一个专业的AI投研助手，帮助用户进行股票研究、行业分析和知识管理。"
    "风格要求：严谨、有逻辑、数据优先。"
    "格式要求：使用Markdown，适合飞书阅读，重点用【】标注。"
    "铁律：只使用用户消息中明确提供的数据，禁止编造、推断或补充任何未提供的数字。"
)

_DEFAULT_MODEL = "claude-sonnet-4-5"


class ClaudeAPIProvider(ProviderBase):
    API_URL = "https://api.anthropic.com/v1/messages"

    def call(self, prompt: str, timeout: int = 300, cwd: str = "", **kwargs) -> str:
        api_key = kwargs.get('api_key') or os.environ.get('ANTHROPIC_API_KEY', '')
        model = kwargs.get('model', _DEFAULT_MODEL)
        system = kwargs.get('system', _DEFAULT_SYSTEM)

        if not api_key:
            return "❌ 未设置 ANTHROPIC_API_KEY"

        proxies = None
        proxy = os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy') or \
                os.environ.get('ALL_PROXY') or os.environ.get('all_proxy')
        if proxy:
            proxies = {"https": proxy, "http": proxy}

        try:
            resp = requests.post(
                self.API_URL,
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": 8096,
                    "system": system,
                    "messages": [{"role": "user", "content": prompt}],
                },
                proxies=proxies,
                timeout=timeout,
            )
            if resp.status_code == 429:
                return "⏸️ AI 额度暂时耗尽（rate limit）"
            if resp.status_code != 200:
                return f"❌ Claude API HTTP错误 {resp.status_code}: {resp.text[:200]}"
            data = resp.json()
            content = data.get('content', [])
            if not content:
                return "（Claude 无输出）"
            return content[0].get('text', '').strip() or "（Claude 内容为空）"
        except requests.Timeout:
            return f"❌ 超时（{timeout}s）"
        except Exception as e:
            return f"❌ Claude API 失败: {e}"

    def check_available(self) -> bool:
        return bool(os.environ.get('ANTHROPIC_API_KEY'))


def create_provider():
    return ClaudeAPIProvider()
