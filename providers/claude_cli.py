"""Claude CLI Provider。"""
import subprocess
from providers.base import ProviderBase
from core.context import ProviderManifest

MANIFEST = ProviderManifest(name="claude_cli", description="本地Claude CLI调用")

class ClaudeCLIProvider(ProviderBase):
    def call(self, prompt: str, timeout: int = 300, cwd: str = "", **kwargs) -> str:
        try:
            proc = subprocess.Popen(
                ['claude', '--print', '--dangerously-skip-permissions', prompt],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                cwd=cwd or None,
            )
            stdout, stderr = proc.communicate(timeout=timeout)
            if stdout.strip():
                return stdout.strip()
            err = stderr.strip()
            if err and ('rate' in err.lower() or 'limit' in err.lower()):
                return "⏸️ AI 额度暂时耗尽"
            return err if err else "（无输出）"
        except subprocess.TimeoutExpired:
            proc.kill()
            return f"❌ 超时（{timeout}s）"
        except FileNotFoundError:
            return "❌ 未找到 claude 命令"
        except Exception as e:
            return f"❌ 异常: {e}"

    def check_available(self) -> bool:
        try:
            r = subprocess.run(['claude', '--version'], capture_output=True, text=True, timeout=5)
            return r.returncode == 0
        except Exception:
            return False

def create_provider():
    return ClaudeCLIProvider()
