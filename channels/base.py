"""Channel 抽象基类。"""
from abc import ABC, abstractmethod
from core.context import Context


class ChannelBase(ABC):
    @abstractmethod
    def start(self, runtime):
        """启动监听（可阻塞）。"""
        pass

    @abstractmethod
    def send_reply(self, ctx: Context):
        """将结果发回用户。"""
        pass

    def build_context(self, runtime, **kwargs) -> Context:
        return Context(
            bot_name=runtime.config.name,
            channel=getattr(self, 'MANIFEST', type('', (), {'name': 'unknown'})).name,
            workspace=runtime.config.workspace,
            **kwargs,
        )
