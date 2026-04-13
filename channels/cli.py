"""CLI 调试渠道 — 终端直接测试消息处理链路，无需飞书。"""
import uuid
from channels.base import ChannelBase
from core.context import Context, ChannelManifest, ContextStatus

MANIFEST = ChannelManifest(name="cli", description="本地CLI调试渠道")


class CLIChannel(ChannelBase):

    def start(self, runtime):
        self._runtime = runtime
        print(f"\n{'='*40}")
        print(f"  CLI 模式 — {runtime.config.label}")
        print(f"  输入指令测试，Ctrl+C 退出")
        print(f"{'='*40}\n")

        while True:
            try:
                text = input(f"[{runtime.config.name}] > ").strip()
                if not text:
                    continue
                if text in ('exit', 'quit'):
                    break
                ctx = self.build_context(runtime,
                    request_id=str(uuid.uuid4())[:8],
                    user_id='cli_user',
                    raw_text=text,
                    metadata={},
                )
                from core.executor import execute_in_runtime
                ctx = execute_in_runtime(runtime, ctx)
                self.send_reply(ctx)
            except (KeyboardInterrupt, EOFError):
                print("\n[cli] 退出")
                break

    def send_reply(self, ctx: Context):
        if ctx.reply_text:
            print(f"\n{ctx.reply_text}\n")
        if ctx.status == ContextStatus.ERROR:
            print(f"[错误] {ctx.error_message}")


def create_channel():
    return CLIChannel()
