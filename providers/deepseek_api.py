"""DeepSeek API Provider（使用 OpenAI SDK）。"""
import os
from openai import OpenAI
from providers.base import ProviderBase
from core.context import ProviderManifest

MANIFEST = ProviderManifest(name="deepseek_api", description="DeepSeek Chat API（OpenAI SDK）")

# 投研助手通用 system prompt（与 Claude 的 CLAUDE.md 角色对齐）
_DEFAULT_SYSTEM = (
    "你是一个专业的AI投研助手，帮助用户进行股票研究、行业分析和知识管理。"
    "风格要求：严谨、有逻辑、数据优先。"
    "格式要求：使用Markdown，适合飞书阅读，重点用【】标注。"
    "铁律：只使用用户消息中明确提供的数据，禁止编造、推断或补充任何未提供的数字。"
)


class DeepSeekProvider(ProviderBase):

    def call(self, prompt: str, timeout: int = 300, cwd: str = "", **kwargs) -> str:
        api_key = kwargs.get('api_key') or os.environ.get('DEEPSEEK_API_KEY', '')
        model = kwargs.get('model', 'deepseek-v4-flash')
        system = kwargs.get('system', _DEFAULT_SYSTEM)

        if not api_key:
            return "❌ 未设置 DEEPSEEK_API_KEY"

        client = OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com",
            timeout=timeout,
        )

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                stream=False,
                reasoning_effort="high",
                extra_body={"thinking": {"type": "enabled"}},
            )
            content = response.choices[0].message.content
            return content.strip() if content else "（DeepSeek 无输出）"
        except Exception as e:
            err = str(e)
            if "429" in err:
                return "⏸️ AI 额度暂时耗尽（rate limit）"
            return f"❌ DeepSeek 失败: {e}"

    def check_available(self) -> bool:
        return bool(os.environ.get('DEEPSEEK_API_KEY'))


def create_provider():
    return DeepSeekProvider()
