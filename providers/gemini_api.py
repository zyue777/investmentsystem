"""Gemini API Provider。"""
import os
import requests
from providers.base import ProviderBase
from core.context import ProviderManifest

MANIFEST = ProviderManifest(name="gemini_api", description="Google Gemini API")

_DEFAULT_SYSTEM = (
    "你是一个专业的AI投研助手，帮助用户进行股票研究、行业分析和知识管理。"
    "风格要求：严谨、有逻辑、数据优先。"
    "格式要求：使用Markdown，适合飞书阅读，重点用【】标注。"
    "铁律：只使用用户消息中明确提供的数据，禁止编造、推断或补充任何未提供的数字。"
)

class GeminiProvider(ProviderBase):
    def call(self, prompt: str, timeout: int = 300, cwd: str = "", **kwargs) -> str:
        api_key = kwargs.get('api_key') or os.environ.get('GEMINI_API_KEY', '')
        # 默认使用 Gemini 2.5 Flash，旧版 1.5 已经被官方下线会报 404
        model = kwargs.get('model', 'gemini-2.5-flash')
        system = kwargs.get('system', _DEFAULT_SYSTEM)

        if not api_key:
            return "❌ 未设置 GEMINI_API_KEY"

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

        # 构造请求体 (按照 Gemini 官方 V1Beta 协议)
        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"parts": [{"text": prompt}]}]
        }

        try:
            resp = requests.post(
                url,
                headers={
                    "Content-Type": "application/json",
                    "X-goog-api-key": api_key,
                },
                json=payload,
                timeout=timeout,
            )
            if resp.status_code == 429:
                return "⏸️ AI 额度繁忙（rate limit）"
            if resp.status_code != 200:
                return f"❌ Gemini HTTP错误 {resp.status_code}: {resp.text[:200]}"
            data = resp.json()
            candidates = data.get('candidates', [])
            if not candidates:
                return "（Gemini 无输出）"
            
            # 提取文本回复
            text = candidates[0].get('content', {}).get('parts', [{}])[0].get('text', '')
            return text.strip() or "（Gemini 内容为空）"
        except requests.Timeout:
            return f"❌ 超时（{timeout}s）"
        except Exception as e:
            return f"❌ Gemini 失败: {e}"

    def check_available(self) -> bool:
        return bool(os.environ.get('GEMINI_API_KEY'))

def create_provider():
    return GeminiProvider()
