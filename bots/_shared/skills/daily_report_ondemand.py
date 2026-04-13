"""按需触发每日报告 — 用户主动发送指令时立即生成并回复。

定时任务走 scheduler_runner.py（自动推送给所有人）。
本 Skill 是补充：用户随时可以主动发指令，立即拿到最新报告。
"""
import sys
from pathlib import Path
from core.context import Context, ContextStatus, SkillManifest

MANIFEST = SkillManifest(
    name="daily_report_ondemand",
    description="按需生成每日报告（晨报/午间复盘/收盘复盘/周末汇总）",
    triggers=[
        "午间复盘",
        "午盘复盘",
        "午间报告",
        "收盘复盘",
        "收盘报告",
        "晨报",
        "股票晨报",
        "大宗商品晨报",
        "周末汇总",
        "自选股",
    ],
    version="1.0.0",
    tags=["报告", "数据"],
    priority=20,   # 高优先级，排在 kb_query(P50) 前面
)

# 触发词 → 生成函数名映射
_TRIGGER_MAP = {
    "午间复盘":    "generate_midday_review",
    "午盘复盘":    "generate_midday_review",
    "午间报告":    "generate_midday_review",
    "收盘复盘":    "generate_review",
    "收盘报告":    "generate_review",
    "晨报":        "generate_morning_stock",
    "股票晨报":    "generate_morning_stock",
    "大宗商品晨报": "generate_morning_commodity",
    "周末汇总":    "generate_weekend_summary",
    "自选股":      "generate_watchlist",
}


def handle(ctx: Context) -> Context:
    # 确保 daily_reporter 在 path 中
    root = Path(__file__).parent.parent.parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    text = ctx.raw_text.strip()

    # 找到匹配的生成函数
    gen_func_name = None
    for trigger, func_name in _TRIGGER_MAP.items():
        if text.startswith(trigger):
            gen_func_name = func_name
            break

    if not gen_func_name:
        ctx.reply_text = "❓ 未识别的报告类型"
        ctx.status = ContextStatus.ERROR
        return ctx

    # 提示用户数据获取中（报告生成通常需要 30-60 秒）
    ctx.reply_text = f"⏳ 正在抓取数据并生成 {text}，请稍候（约30-60秒）..."
    ctx.status = ContextStatus.PENDING

    # 在后台线程中生成（避免飞书 WS 超时）
    import threading
    threading.Thread(
        target=_generate_and_reply,
        args=(ctx, gen_func_name, text),
        daemon=True
    ).start()

    return ctx


def _generate_and_reply(ctx: Context, gen_func_name: str, label: str):
    """后台线程：生成报告 → 发飞书消息。"""
    try:
        from daily_reporter.report_builder import (
            generate_midday_review, generate_review,
            generate_morning_stock, generate_morning_commodity,
            generate_watchlist, generate_weekend_summary,
        )
        gen_funcs = {
            "generate_midday_review":     generate_midday_review,
            "generate_review":            generate_review,
            "generate_morning_stock":     generate_morning_stock,
            "generate_morning_commodity": generate_morning_commodity,
            "generate_watchlist":         generate_watchlist,
            "generate_weekend_summary":   generate_weekend_summary,
        }
        report = gen_funcs[gen_func_name]()

    except Exception as e:
        report = f"❌ {label} 生成失败：{e}"

    # 用 feishu_message 工具直接发给触发此次请求的用户
    try:
        from tools.feishu_token import get_token
        from tools.feishu_message import send_text

        # channel_config 里有 app_id / app_secret
        runtime = ctx.metadata.get('_runtime')
        if runtime:
            cfg = runtime.config.channel_config
            token = get_token(cfg.get('app_id', ''), cfg.get('app_secret', ''))
            if token:
                # 飞书单条消息上限约 4000 字
                chunk = report[:3800] + ('\n\n…（已截断）' if len(report) > 3800 else '')
                send_text(token, ctx.user_id, chunk)
            else:
                print(f"[daily_report_ondemand] token 获取失败")
    except Exception as e:
        print(f"[daily_report_ondemand] 发送失败: {e}")
