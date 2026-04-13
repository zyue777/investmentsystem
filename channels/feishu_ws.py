"""飞书 WebSocket 长连接渠道。"""
import json
import traceback
import threading
import lark_oapi as lark
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1
from channels.base import ChannelBase
from core.context import Context, ChannelManifest

MANIFEST = ChannelManifest(name="feishu_ws", description="飞书WebSocket长连接")


class FeishuWSChannel(ChannelBase):

    def start(self, runtime):
        cfg = runtime.config.channel_config
        self._runtime = runtime
        self._app_id = cfg.get('app_id', '')
        self._app_secret = cfg.get('app_secret', '')

        print(f"[feishu/{runtime.config.name}] app_id={self._app_id[:8]}... (len={len(self._app_id)})")

        def on_message(data: P2ImMessageReceiveV1):
            print(f"[feishu/{runtime.config.name}] >>> 收到消息事件")
            try:
                if data.event is None:
                    print(f"[feishu] data.event is None")
                    return
                msg = data.event.message
                sender = data.event.sender
                if not msg or not sender:
                    print(f"[feishu] msg={msg} sender={sender}")
                    return
                if msg.message_type != 'text':
                    print(f"[feishu] 跳过非文本消息: {msg.message_type}")
                    return
                content = json.loads(msg.content or '{}')
                raw_text = content.get('text', '').strip()
                if not raw_text:
                    print(f"[feishu] 空文本")
                    return
                open_id = sender.sender_id.open_id if sender.sender_id else ''
                if not open_id:
                    print(f"[feishu] 无 open_id")
                    return

                print(f"[feishu/{runtime.config.name}] 消息: '{raw_text[:50]}' from {open_id[:15]}...")

                ctx = self.build_context(runtime,
                    request_id=msg.message_id or '', user_id=open_id,
                    raw_text=raw_text,
                    metadata={'app_id': self._app_id, 'app_secret': self._app_secret},
                )
                threading.Thread(target=self._handle, args=(ctx,), daemon=True).start()
            except Exception as e:
                print(f"[feishu/{runtime.config.name}] 异常: {e}")
                traceback.print_exc()

        handler = (lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(on_message).build())
        print(f"[feishu/{runtime.config.name}] 连接飞书...")
        # 每个线程创建独立的 event loop，避免多Bot共用同一 loop 冲突
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        lark.ws.Client(self._app_id, self._app_secret,
                       event_handler=handler, log_level=lark.LogLevel.INFO).start()

    def _handle(self, ctx: Context):
        try:
            from core.executor import execute_in_runtime
            ctx = execute_in_runtime(self._runtime, ctx)
            self.send_reply(ctx)
        except Exception as e:
            print(f"[feishu] _handle 异常: {e}")
            traceback.print_exc()

    def send_reply(self, ctx: Context):
        if not ctx.reply_text:
            return
        try:
            from tools.feishu_token import get_token
            from tools.feishu_message import send_text
            token = get_token(ctx.metadata.get('app_id', ''), ctx.metadata.get('app_secret', ''))
            if not token:
                print(f"[feishu] ⚠️ 获取token失败")
                return
            ok = send_text(token, ctx.user_id, ctx.reply_text)
            print(f"[feishu] 回复{'成功' if ok else '失败'} → {ctx.user_id[:15]}...")
        except Exception as e:
            print(f"[feishu] send_reply 异常: {e}")
            traceback.print_exc()

def create_channel():
    return FeishuWSChannel()
