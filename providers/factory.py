"""Provider 工厂 —— 单一真理源。

所有非 Claude 模块通过 get_provider() 获取 AI Provider 实例。
换模型：只改 .env 中的 AI_MODEL=xxx，业务代码零改动。

设计说明：
  - Claude CLI Bot 不经过这里（走 providers/claude_cli.py，独立架构）
  - 其余所有 Bot（Gemini / Kimi / DeepSeek 等）统一走 LiteLLMProvider
"""

import os
from providers.base import ProviderBase


def get_provider(model: str = None) -> ProviderBase:
    """返回 LiteLLMProvider 实例。

    Args:
        model: 可选，覆盖 .env 中的 AI_MODEL。
               格式：'gemini/gemini-2.0-flash'、'moonshot/moonshot-v1-8k' 等。
               为空则自动读取 AI_MODEL 环境变量。
    """
    from providers.litellm_provider import LiteLLMProvider
    provider = LiteLLMProvider()
    # 若调用方指定了 model，在 call() 时以 kwargs 传入覆盖
    if model:
        # 包装一个临时实例，将 model 绑定进去
        _model = model
        _inner = provider

        class _BoundProvider(ProviderBase):
            def call(self, prompt, timeout=300, cwd="", **kwargs):
                kwargs.setdefault("model", _model)
                return _inner.call(prompt, timeout, cwd, **kwargs)
            def check_available(self):
                return _inner.check_available()

        return _BoundProvider()
    return provider
