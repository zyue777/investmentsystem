"""手动沉淀技能 — 用户发"沉淀"查看最近成功记录并标记为模板。"""
import json
from pathlib import Path
from core.context import Context, ContextStatus, SkillManifest

MANIFEST = SkillManifest(
    name="crystallize",
    description="查看执行统计或将成功经验标记为可复用模板",
    triggers=["沉淀", "统计", "复盘"],
    tags=["系统", "沉淀"],
)


def handle(ctx: Context) -> Context:
    runtime = ctx.metadata.get('_runtime')
    log_file = runtime.bot_dir / 'memory' / 'store' / 'executions.jsonl'

    if not log_file.exists():
        ctx.status = ContextStatus.SUCCESS
        ctx.reply_text = "暂无执行记录"
        return ctx

    records = _load_recent(log_file, days=7)
    subcmd = ctx.parsed_args.get('content', '').strip()

    if ctx.raw_text.startswith('统计'):
        # ── 统计模式 ──
        total = len(records)
        if total == 0:
            ctx.reply_text = "📊 近7天无执行记录"
            ctx.status = ContextStatus.SUCCESS
            return ctx
        success = sum(1 for r in records if r['status'] == 'success')
        by_skill = {}
        for r in records:
            s = r['matched_skill']
            by_skill[s] = by_skill.get(s, 0) + 1

        lines = [f"📊 近7天执行统计（{total}次，成功率 {success/total*100:.0f}%）\n"]
        for skill, count in sorted(by_skill.items(), key=lambda x: -x[1]):
            lines.append(f"  {skill}: {count}次")

        ctx.reply_text = '\n'.join(lines)

    else:
        # ── 沉淀模式：展示最近成功记录 ──
        success_records = [r for r in records if r['status'] == 'success'][-10:]
        if not success_records:
            ctx.reply_text = "近7天无成功记录"
        else:
            lines = ["🧊 最近成功执行（可标记为模板）：\n"]
            for i, r in enumerate(success_records):
                lines.append(f"  [{i+1}] {r['matched_skill']} | "
                             f"{r['input_summary'][:40]} | {r['timestamp'][:10]}")
            lines.append("\n💡 回复序号可将该记录标记为常用模式（如：沉淀 3）")

            if subcmd and subcmd.isdigit():
                idx = int(subcmd) - 1
                if 0 <= idx < len(success_records):
                    _mark_as_template(runtime, success_records[idx])
                    ctx.reply_text = f"✅ 已标记为常用模式：{success_records[idx]['matched_skill']}"
                else:
                    ctx.reply_text = "序号超出范围"
            else:
                ctx.reply_text = '\n'.join(lines)

    ctx.status = ContextStatus.SUCCESS
    return ctx


def _load_recent(log_file, days=7):
    from datetime import datetime, timedelta
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    records = []
    with open(log_file, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                try:
                    r = json.loads(line)
                    if r.get('timestamp', '') >= cutoff:
                        records.append(r)
                except json.JSONDecodeError:
                    pass
    return records


def _mark_as_template(runtime, record):
    tpl_file = runtime.bot_dir / 'memory' / 'store' / 'templates.jsonl'
    record['_is_template'] = True
    record['_marked_at'] = __import__('datetime').datetime.now().isoformat()
    with open(tpl_file, 'a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False) + '\n')
