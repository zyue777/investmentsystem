"""统一执行引擎。这是消息处理的核心函数。
📝 文档引用：docs/00_架构总览.md「消息流转路径」
⚠️ 修改本文件影响所有 Bot 的执行链，修改前必须说明理由。
"""
from core.context import Context, ContextStatus
from core.bot_runtime import BotRuntime


def execute_in_runtime(runtime: BotRuntime, ctx: Context) -> Context:
    """完整的消息处理链路：Route → Middleware → Skill → Reply。
    
    这个函数是系统的"心脏"，整个调用链条如下：
    Channel.on_message → execute_in_runtime → Channel.send_reply
    """
    try:
        # ── Step 1: 路由（若 Channel 已预设 matched_skill，跳过 Router）──
        # 预路由规则：Channel 层可在构建 ctx 时设置 matched_skill + status=ROUTED
        # 以绕过 Router 的触发词匹配（例：文件消息直接指向 ingest_file）
        if ctx.status != ContextStatus.ROUTED:
            ctx = runtime.router.route(ctx)

        if ctx.status == ContextStatus.ERROR:
            ctx.reply_text = ctx.error_message or "无法识别指令"
            return ctx

        # ── Step 2: 查找 skill handler ──
        handler = runtime.skill_registry.get_handler(ctx.matched_skill)
        print(f"[executor] 路由结果: matched_skill={ctx.matched_skill}, handler={'✅' if handler else '❌ None'}, confidence={ctx.match_confidence}")
        if handler is None:
            ctx.status = ContextStatus.ERROR
            ctx.reply_text = f"技能 [{ctx.matched_skill}] 未注册"
            return ctx

        # ── Step 3: 注入运行时依赖到 metadata ──
        # skill 通过 ctx.metadata 访问 runtime 提供的共享资源
        # 原则：Skill 不应直接访问 runtime 的内部属性（_xxx）
        ctx.metadata['_runtime'] = runtime
        ctx.metadata['_pending_store'] = runtime.pending_store
        ctx.metadata['_dialog_history'] = runtime.dialog_history
        ctx.metadata['_dialog_mode'] = runtime.dialog_mode
        ctx.metadata['_phase_configs'] = runtime._phase_configs  # 供 Skill 读取 Phase 配置


        # ── Step 4: 解析 AI Provider ──
        skill_item = runtime.skill_registry.get(ctx.matched_skill)
        skill_manifest = skill_item['manifest'] if skill_item else None
        ctx.ai_provider = _resolve_provider_name(
            skill_manifest, ctx.phase_key, runtime)

        # ── Step 5: 通过 Middleware 管道执行 ──
        ctx = runtime.pipeline.execute(ctx, handler)
        print(f"[executor] 执行完成: skill={ctx.matched_skill}, status={ctx.status}, reply_len={len(ctx.reply_text) if ctx.reply_text else 0}")

        # ── Step 6: 兜底回复 ──
        if not ctx.reply_text and ctx.status == ContextStatus.ERROR:
            ctx.reply_text = ctx.error_message or "处理失败"

        return ctx

    except Exception as e:
        ctx.status = ContextStatus.ERROR
        ctx.error_message = str(e)
        ctx.reply_text = f"❌ 系统异常: {e}"
        return ctx


def _resolve_provider_name(skill_manifest, phase_key, runtime) -> str:
    """Provider 优先级：Skill指定 > Phase指定 > Bot默认 > claude_cli"""
    # 1. Skill 级
    if skill_manifest and getattr(skill_manifest, 'ai_provider', ''):
        return skill_manifest.ai_provider
    # 2. Phase 级
    if phase_key and phase_key in runtime._phase_configs:
        phase_provider = runtime._phase_configs[phase_key].get('ai_provider', '')
        if phase_provider:
            return phase_provider
    # 3. Bot 级
    if runtime.config.ai_provider:
        return runtime.config.ai_provider
    # 4. 全局兜底
    return 'claude_cli'


def get_ai_provider(ctx: Context):
    """Skill 内部调用此函数获取 AI Provider 实例。"""
    runtime = ctx.metadata.get('_runtime')
    if not runtime:
        return None
    provider_name = ctx.ai_provider or 'claude_cli'
    provider = runtime.provider_registry.get_instance(provider_name)
    if not provider:
        # 降级：如果指定 provider 不可用，尝试 Bot 默认
        fallback = runtime.config.ai_provider or 'claude_cli'
        if fallback != provider_name:
            print(f"[executor] {provider_name} 不可用，降级到 {fallback}")
            provider = runtime.provider_registry.get_instance(fallback)
    return provider
