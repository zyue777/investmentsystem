"""DeepSeek API Provider。"""
import os
import requests
from providers.base import ProviderBase
from core.context import ProviderManifest

MANIFEST = ProviderManifest(name="deepseek_api", description="DeepSeek Chat API")

# 投研助手通用 system prompt（与 Claude 的 CLAUDE.md 角色对齐）
_DEFAULT_SYSTEM = (
    "你是一个专业的AI投研助手，帮助用户进行股票研究、行业分析和知识管理。"
    "风格要求：严谨、有逻辑、数据优先。"
    "格式要求：使用Markdown，适合飞书阅读，重点用【】标注。"
    "铁律：只使用用户消息中明确提供的数据，禁止编造、推断或补充任何未提供的数字。"
)


class DeepSeekProvider(ProviderBase):
    API_URL = "https://api.deepseek.com/chat/completions"

    def call(self, prompt: str, timeout: int = 300, cwd: str = "", **kwargs) -> str:
        api_key = kwargs.get('api_key') or os.environ.get('DEEPSEEK_API_KEY', '')
        model = kwargs.get('model', 'deepseek-v4-flash')
        system = kwargs.get('system', _DEFAULT_SYSTEM)

        if not api_key:
            return "❌ 未设置 DEEPSEEK_API_KEY"

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        try:
            resp = requests.post(
                self.API_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={"model": model, "messages": messages},
                timeout=timeout,
            )
            if resp.status_code == 429:
                return "⏸️ AI 额度暂时耗尽（rate limit）"
            if resp.status_code != 200:
                return f"❌ DeepSeek HTTP错误 {resp.status_code}: {resp.text[:200]}"
            data = resp.json()
            choices = data.get('choices', [])
            if not choices:
                return "（DeepSeek 无输出）"
            return choices[0]['message']['content'].strip()
        except requests.Timeout:
            return f"❌ 超时（{timeout}s）"
        except Exception as e:
            return f"❌ DeepSeek 失败: {e}"

    def check_available(self) -> bool:
        return bool(os.environ.get('DEEPSEEK_API_KEY'))


def create_provider():
    return DeepSeekProvider()

