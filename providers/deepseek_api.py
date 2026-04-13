"""DeepSeek API Provider。"""
import os, requests
from providers.base import ProviderBase
from core.context import ProviderManifest

MANIFEST = ProviderManifest(name="deepseek_api", description="DeepSeek Chat API")

class DeepSeekProvider(ProviderBase):
    API_URL = "https://api.deepseek.com/chat/completions"
    def call(self, prompt, timeout=300, cwd="", **kwargs):
        api_key = kwargs.get('api_key') or os.environ.get('DEEPSEEK_API_KEY', '')
        model = kwargs.get('model', 'deepseek-chat')
        if not api_key:
            return "❌ 未设置 DEEPSEEK_API_KEY"
        try:
            resp = requests.post(self.API_URL,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": model, "messages": [{"role": "user", "content": prompt}]},
                timeout=timeout)
            return resp.json()['choices'][0]['message']['content']
        except Exception as e:
            return f"❌ DeepSeek 失败: {e}"
    def check_available(self):
        return bool(os.environ.get('DEEPSEEK_API_KEY'))

def create_provider():
    return DeepSeekProvider()
