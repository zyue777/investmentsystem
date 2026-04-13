"""备忘录快捷存储 — 零Token，直接追加文件+git提交。"""
from datetime import datetime
from pathlib import Path
from core.context import Context, ContextStatus, SkillManifest


MANIFEST = SkillManifest(
    name="memo_save",
    description="零Token备忘录快捷存储",
    triggers=["memo", "备忘"],
    version="1.0.0",
    tags=["工具"],
    priority=20,
)


def handle(ctx: Context) -> Context:
    content = ctx.parsed_args.get('content', '').strip()
    if not content:
        ctx.reply_text = "⚠️ memo 后请附上内容"
        ctx.status = ContextStatus.SUCCESS
        return ctx

    ws = ctx.workspace
    today = datetime.now().strftime('%Y-%m-%d')
    time_str = datetime.now().strftime('%H:%M')
    rel_path = f"投资哲学/碎片备忘/_Inbox/{today}_投资思考.md"
    full_path = Path(ws) / rel_path

    full_path.parent.mkdir(parents=True, exist_ok=True)

    # 如果文件不存在，写入头部
    if not full_path.exists():
        full_path.write_text(f"# {today} 投资思考碎片\n\n", encoding='utf-8')

    # 追加记录
    entry = f"\n---\n\n**[{time_str}]**\n\n{content}\n"
    with open(full_path, 'a', encoding='utf-8') as f:
        f.write(entry)

    # git commit
    from tools.file_write import git_commit
    git_hash = git_commit(str(full_path), ws, f"memo: {today} {time_str}")

    ctx.reply_text = f"📝 已记录\n📁 {rel_path}\n📌 git: {git_hash}"
    ctx.status = ContextStatus.SUCCESS
    return ctx
