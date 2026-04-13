"""AI Provider 抽象基类，内置重试和降级能力。"""
import time
from abc import ABC, abstractmethod


class ProviderBase(ABC):
    @abstractmethod
    def call(self, prompt: str, timeout: int = 300, cwd: str = "", **kwargs) -> str:
        pass

    @abstractmethod
    def check_available(self) -> bool:
        pass

    def call_with_retry(self, prompt: str, timeout: int = 300,
                        cwd: str = "", max_retries: int = 2,
                        backoff: float = 2.0, **kwargs) -> str:
        """带指数退避重试的调用。Provider 不可用时抛出异常供 executor 降级。"""
        last_error = ""
        for attempt in range(max_retries + 1):
            result = self.call(prompt, timeout, cwd, **kwargs)
            # 正常结果
            if not result.startswith("❌") and not result.startswith("⏸️"):
                return result
            last_error = result
            # 限流 → 重试
            if "⏸️" in result and attempt < max_retries:
                wait = backoff ** attempt
                print(f"[provider] 限流，{wait}s后重试 ({attempt+1}/{max_retries})")
                time.sleep(wait)
                continue
            # 硬错误 → 不重试
            if "❌" in result:
                break
        return last_error
