"""LiteLLM 通用 Provider —— 换插座层。

设计原则：
  - 这是所有"可替换模型 Bot"的唯一推理层入口
  - 换模型只需修改 .env 中的 AI_MODEL 变量，无需改任何业务代码
  - Claude CLI Bot 不经过此处（它有独立的 claude_cli provider）

支持的模型示例（改 .env 即可切换）：
  AI_MODEL=gemini/gemini-2.0-flash          ← 当前默认
  AI_MODEL=moonshot/moonshot-v1-8k          ← Kimi
  AI_MODEL=deepseek/deepseek-chat           ← DeepSeek
  AI_MODEL=gpt-4o                           ← OpenAI
  AI_MODEL=claude-3-5-sonnet-20241022       ← Claude API（非 CLI）

对应的 API Key 环境变量（LiteLLM 自动识别）：
  GEMINI_API_KEY        ← Gemini
  MOONSHOT_API_KEY      ← Kimi (月之暗面)
  DEEPSEEK_API_KEY      ← DeepSeek
  OPENAI_API_KEY        ← OpenAI
  ANTHROPIC_API_KEY     ← Claude API
"""

import os
from providers.base import ProviderBase
from core.context import ProviderManifest

MANIFEST = ProviderManifest(name="litellm", description="LiteLLM 通用模型层（换模型只改 .env）")

# 默认 system prompt（可被调用方覆盖）
_DEFAULT_SYSTEM = (
    "你是一个专业的AI投研助手，帮助用户进行股票研究、行业分析和知识管理。"
    "风格要求：严谨、有逻辑、数据优先。"
    "格式要求：使用Markdown，适合飞书阅读，重点用【】标注。"
    "铁律：只使用用户消息中明确提供的数据，禁止编造、推断或补充任何未提供的数字。"
)


# Gemini 免费层降级链（限流时自动尝试下一个，无需手动切换）
_GEMINI_FALLBACK_CHAIN = [
    "gemini/gemini-2.5-flash",
    "gemini/gemini-2.0-flash",
    "gemini/gemini-flash-latest",
]

def _build_fallbacks(primary_model: str) -> list:
    """构建降级模型列表（排除主模型自身）。"""
    if primary_model in _GEMINI_FALLBACK_CHAIN:
        # 从主模型之后的位置开始作为备用
        idx = _GEMINI_FALLBACK_CHAIN.index(primary_model)
        return _GEMINI_FALLBACK_CHAIN[idx + 1:]
    return []  # 非 Gemini 模型不自动降级


class LiteLLMProvider(ProviderBase):
    """通用 LiteLLM Provider。model 从 AI_MODEL 环境变量读取。"""

    def call(self, prompt: str, timeout: int = 300, cwd: str = "", **kwargs) -> str:
        # 延迟导入，避免冷启动时的导入开销
        try:
            import litellm
        except ImportError:
            return "❌ litellm 未安装，请执行: pip install litellm"

        model  = kwargs.get("model")  or os.environ.get("AI_MODEL", "gemini/gemini-2.0-flash")
        system = kwargs.get("system") or _DEFAULT_SYSTEM

        messages = [
            {"role": "system", "content": system},
            {"role": "user",   "content": prompt},
        ]

        # 支持自定义 base_url（Kimi 中转站等 OpenAI 兼容接口）
        api_base = kwargs.get("api_base") or os.environ.get("AI_API_BASE") or None
        api_key  = kwargs.get("api_key")  or os.environ.get("AI_API_KEY")  or None

        # litellm 用 httpx 发请求，httpx 会读 all_proxy/ALL_PROXY 环境变量。
        # PM2 ecosystem 里设了 socks5 代理，但 httpx[socks] 未安装会直接崩溃。
        # Kimi/DeepSeek 等国内接口不需要代理，临时清掉再恢复。
        _proxy_keys = ("all_proxy", "ALL_PROXY", "HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy")
        _saved_proxies = {k: os.environ.pop(k) for k in _proxy_keys if k in os.environ}

        try:
            resp = litellm.completion(
                model=model,
                messages=messages,
                timeout=timeout,
                fallbacks=_build_fallbacks(model),
                **({"api_base": api_base} if api_base else {}),
                **({"api_key":  api_key}  if api_key  else {}),
            )
            return resp.choices[0].message.content or "（模型无输出）"

        except litellm.AuthenticationError as e:
            msg = f"❌ API Key 认证失败（{model}）: {e}"
            print(f"[litellm_provider] {msg}")
            return msg
        except litellm.RateLimitError as e:
            msg = f"⏸️ 所有模型均触发限流，请稍后重试: {e}"
            print(f"[litellm_provider] {msg}")
            return msg
        except litellm.BadRequestError as e:
            msg = f"❌ 请求格式错误（{model}）: {e}"
            print(f"[litellm_provider] {msg}")
            return msg
        except Exception as e:
            msg = f"❌ LiteLLM 调用异常（{model}）: {e}"
            print(f"[litellm_provider] {msg}")
            return msg
        finally:
            os.environ.update(_saved_proxies)

    def check_available(self) -> bool:
        try:
            import litellm  # noqa
            return bool(os.environ.get("AI_MODEL") or os.environ.get("GEMINI_API_KEY"))
        except ImportError:
            return False


def create_provider():
    return LiteLLMProvider()
