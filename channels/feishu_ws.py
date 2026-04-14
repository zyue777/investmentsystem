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
                if msg.message_type == 'text':
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

                elif msg.message_type in runtime.config.file_skill_routes:
                    # ── 文件/文档消息 → 配置驱动路由（TD-04 修复）───────────────
                    # 路由目标由 bot.yaml 的 file_skill_routes 决定，Channel 不硬编码
                    skill_name = runtime.config.file_skill_routes[msg.message_type]
                    open_id = sender.sender_id.open_id if sender.sender_id else ''
                    if not open_id:
                        print(f"[feishu] 文件消息无 open_id")
                        return
                    try:
                        file_content = json.loads(msg.content or '{}')
                        file_key  = file_content.get('file_key', '')
                        file_name = file_content.get('file_name', '未知文件')
                    except Exception:
                        file_key, file_name = '', '未知文件'

                    if not file_key:
                        print(f"[feishu] 文件消息缺少 file_key")
                        return

                    print(f"[feishu/{runtime.config.name}] 文件: '{file_name}' → {skill_name}")
                    ctx = self.build_context(runtime,
                        request_id=msg.message_id or '', user_id=open_id,
                        raw_text=f'[文件] {file_name}',
                        metadata={
                            'app_id': self._app_id, 'app_secret': self._app_secret,
                            '_file_info': {
                                'file_key':   file_key,
                                'file_name':  file_name,
                                'message_id': msg.message_id or '',
                            },
                        },
                    )
                    ctx.matched_skill = skill_name   # 由配置决定，非硬编码
                    from core.context import ContextStatus
                    ctx.status = ContextStatus.ROUTED
                    threading.Thread(target=self._handle_direct, args=(ctx,), daemon=True).start()

                else:
                    print(f"[feishu] 跳过消息类型: {msg.message_type}")
                    return

            except Exception as e:
                print(f"[feishu/{runtime.config.name}] 异常: {e}")
                traceback.print_exc()

        handler = (lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(on_message).build())
        print(f"[feishu/{runtime.config.name}] 连接飞书...")

        # 启动时发送指令菜单给管理员（零 Token，静态消息）
        self._send_startup_menu(runtime)

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

    def _handle_direct(self, ctx: Context):
        """文件消息专用：ctx 已预设 matched_skill，跳过 Router 直接进执行引擎。"""
        try:
            from core.executor import execute_in_runtime
            from core.context import ContextStatus
            # 先发一条"正在处理"提示（文件处理耗时较长）
            ctx.reply_text = f"📎 收到文件，正在提取内容并分析，请稍候..."
            self.send_reply(ctx)
            ctx.reply_text = ''   # 清空，让 Skill 设置真正的回复
            ctx.status = ContextStatus.ROUTED   # 确保 executor 不会跳过 Skill 执行
            ctx = execute_in_runtime(self._runtime, ctx)
            self.send_reply(ctx)
        except Exception as e:
            print(f"[feishu] _handle_direct 异常: {e}")
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

    def _send_startup_menu(self, runtime):
        """启动时发送指令菜单（静态消息，零 Token）。"""
        notify_users = getattr(runtime.config, 'startup_notify_users', None)
        if not notify_users:
            return
        try:
            from tools.feishu_token import get_token
            from tools.feishu_message import send_text
            token = get_token(self._app_id, self._app_secret)
            if not token:
                print(f"[feishu] 启动菜单: token获取失败")
                return

            bot_label = runtime.config.label or runtime.config.name
            menu = (
                f"🤖 {bot_label} 已上线\n"
                f"━━━━━━━━━━━━━━━━━\n"
                f"📋 指令速查：\n"
                f"• 研究 [主题] → 进入研究模式\n"
                f"• 请联网研究 [主题] → 联网研究模式\n"
                f"  ┗ 归档 → 保存为情报卡\n"
                f"  ┗ clear → 清空退出\n"
                f"• 录 [内容] → 录入情报\n"
                f"• 问/析/比 → 知识库问答\n"
                f"• 请联网回答 [问题] → 联网问答\n"
                f"• 发送URL → 自动抓取入库\n"
                f"• 发送文件 → 自动蒸馏入库\n"
                f"• s → 系统状态"
            )

            for uid in notify_users:
                send_text(token, uid, menu)
            print(f"[feishu/{runtime.config.name}] 启动菜单已发送 → {len(notify_users)} 人")
        except Exception as e:
            print(f"[feishu] 启动菜单发送失败: {e}")

def create_channel():
    return FeishuWSChannel()
