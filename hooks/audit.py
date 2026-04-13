"""操作审计 Hook — 每次执行自动写入 JSONL 日志。"""
import json
from pathlib import Path
from core.context import Context, HookManifest, ExecutionRecord

MANIFEST = HookManifest(name="audit", phase="after", priority=20)


def handle(ctx: Context) -> None:
    """执行完成后自动写入日志（零人工）。"""
    runtime = ctx.metadata.get('_runtime')
    if not runtime:
        return

    log_file = runtime.bot_dir / 'memory' / 'store' / 'executions.jsonl'
    log_file.parent.mkdir(parents=True, exist_ok=True)

    record = ExecutionRecord(
        request_id=ctx.request_id,
        timestamp=ctx.created_at,
        bot_name=ctx.bot_name,
        user_id=ctx.user_id,
        channel=ctx.channel,
        matched_skill=ctx.matched_skill,
        ai_provider=ctx.ai_provider,
        status=ctx.status.value if hasattr(ctx.status, 'value') else str(ctx.status),
        execution_time_ms=ctx.execution_time_ms,
        input_summary=ctx.raw_text[:100],
        output_path=ctx.output_path,
        error_message=ctx.error_message,
    )

    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(json.dumps(record.__dict__, ensure_ascii=False) + '\n')
