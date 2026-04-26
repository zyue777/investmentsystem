"""Gemini API Provider。Gemini 出错时自动降级到 DeepSeek API。"""
import os
import requests
from providers.base import ProviderBase
from core.context import ProviderManifest

MANIFEST = ProviderManifest(name="gemini_api", description="Google Gemini API（出错时自动降级到 DeepSeek）")

_DEFAULT_SYSTEM = (
    "你是一个专业的AI投研助手，帮助用户进行股票研究、行业分析和知识管理。"
    "风格要求：严谨、有逻辑、数据优先。"
    "格式要求：使用Markdown，适合飞书阅读，重点用【】标注。"
    "铁律：只使用用户消息中明确提供的数据，禁止编造、推断或补充任何未提供的数字。"
)


def _call_deepseek_fallback(prompt: str, system: str, timeout: int) -> str:
    """降级专用：直接调用 DeepSeek API，不依赖 Provider 注册表。"""
    from providers.deepseek_api import DeepSeekProvider
    ds = DeepSeekProvider()
    return ds.call(prompt, timeout=timeout, system=system)


def _fallback_response(err_reason: str, ds_result: str) -> str:
    """格式化降级回复：错误通知 + DeepSeek 正常输出。"""
    notice = f"⚠️ Gemini 出错（{err_reason}），已自动切换到 DeepSeek\n"
    if ds_result.startswith("❌"):
        return f"{notice}\n❌ DeepSeek 也失败了：{ds_result}"
    return f"{notice}\n---\n\n{ds_result}"


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

            # ── 非 200 时全部降级到 DeepSeek ─────────────────────────────────
            if resp.status_code != 200:
                reason = f"HTTP {resp.status_code}"
                print(f"[gemini_api] ⚠️ Gemini {reason}，自动降级到 DeepSeek...")
                ds_result = _call_deepseek_fallback(prompt, system, timeout)
                if ds_result.startswith("❌"):
                    print(f"[gemini_api] ❌ DeepSeek 降级也失败: {ds_result[:100]}")
                return _fallback_response(reason, ds_result)
            # ─────────────────────────────────────────────────────────────────

            data = resp.json()
            candidates = data.get('candidates', [])
            if not candidates:
                return "（Gemini 无输出）"

            # 提取文本回复
            text = candidates[0].get('content', {}).get('parts', [{}])[0].get('text', '')
            return text.strip() or "（Gemini 内容为空）"
        except requests.Timeout:
            reason = f"请求超时（{timeout}s）"
            print(f"[gemini_api] ⚠️ Gemini {reason}，自动降级到 DeepSeek...")
            ds_result = _call_deepseek_fallback(prompt, system, timeout)
            if ds_result.startswith("❌"):
                print(f"[gemini_api] ❌ DeepSeek 降级也失败: {ds_result[:100]}")
            return _fallback_response(reason, ds_result)
        except Exception as e:
            reason = f"异常: {e}"
            print(f"[gemini_api] ⚠️ Gemini {reason}，自动降级到 DeepSeek...")
            ds_result = _call_deepseek_fallback(prompt, system, timeout)
            if ds_result.startswith("❌"):
                print(f"[gemini_api] ❌ DeepSeek 降级也失败: {ds_result[:100]}")
            return _fallback_response(reason, ds_result)

    def check_available(self) -> bool:
        return bool(os.environ.get('GEMINI_API_KEY'))


def create_provider():
    return GeminiProvider()
