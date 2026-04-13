"""示例技能"""
from core.context import Context, ContextStatus, SkillManifest

MANIFEST = SkillManifest(
    name="hello",
    description="测试Bot运行状态",
    triggers=["你好", "ping", "test"],
    version="1.0.0",
    tags=["系统"],
)

def handle(ctx: Context) -> Context:
    ctx.status = ContextStatus.SUCCESS
    ctx.reply_text = f"✅ {ctx.bot_name} Bot 运行正常！"
    return ctx
