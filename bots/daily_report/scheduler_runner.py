"""
bots/daily_report/scheduler_runner.py
新架构下的每日报告定时调度器。

设计原则：
- 数据抓取/AI生成 完全复用 daily_reporter（不重写业务逻辑）
- 飞书推送 改用新架构的 tools/feishu_token + shared/feishu_utils
- 通过 audit hook 记录每次执行到 executions.jsonl
- 该文件由 start.sh 单独以 nohup 启动，不依赖 Agent Hub 主进程
"""

import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# ── 路径设置 ─────────────────────────────────────────────────────────────────
_BOT_DIR  = Path(__file__).parent
_ROOT_DIR = _BOT_DIR.parent.parent
sys.path.insert(0, str(_ROOT_DIR))

# 加载 .env 环境变量（PM2 直接启动时不经过 start.sh，必须在此加载）
from dotenv import load_dotenv
load_dotenv(_ROOT_DIR / '.env')

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

# 复用旧版数据抓取和报告生成（保持不重复造轮子）
from daily_reporter.data_fetcher import (
    fetch_morning_stock, fetch_morning_commodity,
    fetch_watchlist, fetch_review,
    fetch_midday_review, fetch_weekend_summary,
)
from daily_reporter.report_builder import (
    build_morning_stock, build_morning_commodity,
    build_watchlist, build_review,
    build_midday_review, build_weekend_summary,
)
from shared.feishu_utils import get_tenant_access_token, send_text_message

# ── 日志 ─────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s [daily_report] %(message)s',
    datefmt='%H:%M:%S',
)
log = logging.getLogger('daily_report')

# ── 配置（从环境变量读取，由 start.sh 注入）──────────────────────────────────
APP_ID     = os.environ.get('FEISHU_DS_APP_ID', '')
APP_SECRET = os.environ.get('FEISHU_DS_APP_SECRET', '')
REGISTRY   = _ROOT_DIR / 'shared' / 'user_registry.json'
AUDIT_FILE = _BOT_DIR / 'executions.jsonl'

# 晨间数据缓存（08:25 抓取，08:30 / 09:00 复用）
_morning_cache: dict = {}


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def _get_recipients() -> list:
    """从 user_registry.json 读取注册用户 open_id 列表。"""
    try:
        if not REGISTRY.exists():
            log.warning("user_registry.json 不存在")
            return []
        reg = json.loads(REGISTRY.read_text(encoding='utf-8'))
        return list(reg.get('open_ids', {}).values()) or list(reg.values())
    except Exception as e:
        log.error(f"读取 registry 失败: {e}")
        return []


def _send_to_all(text: str, job_name: str):
    """推送消息给所有注册用户，并写 audit 日志。"""
    recipients = _get_recipients()
    if not recipients:
        log.warning("没有注册用户，消息未发送")
        return

    token = get_tenant_access_token(APP_ID, APP_SECRET)
    if not token:
        log.error("获取飞书 token 失败")
        _audit(job_name, success=False, error="token获取失败")
        return

    success_count = 0
    for open_id in recipients:
        # 飞书消息最大长度约 4000 字符
        chunk = text[:3800] + ('\n\n…（内容已截断）' if len(text) > 3800 else '')
        ok = send_text_message(token, open_id, chunk)
        if ok:
            success_count += 1
        log.info(f"  → {open_id[:8]}... {'✅' if ok else '❌'}")

    _audit(job_name, success=success_count > 0,
           recipients=len(recipients), sent=success_count)


def _audit(job_name: str, success: bool, **extra):
    """写执行记录到 executions.jsonl。"""
    record = {
        "ts": datetime.now().isoformat(),
        "bot": "daily_report",
        "job": job_name,
        "success": success,
        **extra,
    }
    try:
        with open(AUDIT_FILE, 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')
    except Exception as e:
        log.warning(f"audit写入失败: {e}")


# ── 定时任务 ──────────────────────────────────────────────────────────────────

def job_fetch_morning():
    """08:25（周一~周六）— 抓取晨间数据，缓存备用。"""
    global _morning_cache
    log.info("开始抓取晨间数据...")
    try:
        _morning_cache['stock']     = fetch_morning_stock()
        _morning_cache['commodity'] = fetch_morning_commodity()
        _morning_cache['watchlist'] = fetch_watchlist()
        log.info("晨间数据抓取完成")
        _audit('fetch_morning', success=True)
    except Exception as e:
        log.error(f"晨间数据抓取失败: {e}")
        _audit('fetch_morning', success=False, error=str(e))


def job_watchlist():
    """08:30（周一~周六）— 自选股日报。"""
    log.info("生成自选股日报...")
    try:
        data   = _morning_cache.get('watchlist') or fetch_watchlist()
        report = build_watchlist(data)
        _send_to_all(report, 'watchlist')
        log.info("自选股日报已发送")
    except Exception as e:
        log.error(f"自选股日报失败: {e}")
        _send_to_all(f"❌ 自选股日报生成失败：{e}", 'watchlist')


def job_morning_reports():
    """08:10（周一~周六）— 晨报·股票版 + 晨报·大宗商品版。"""
    log.info("生成晨报...")
    try:
        stock_data     = _morning_cache.get('stock')     or fetch_morning_stock()
        commodity_data = _morning_cache.get('commodity') or fetch_morning_commodity()
        _send_to_all(build_morning_stock(stock_data),         'morning_stock')
        time.sleep(2)
        _send_to_all(build_morning_commodity(commodity_data), 'morning_commodity')
        log.info("晨报已发送")
    except Exception as e:
        log.error(f"晨报失败: {e}")
        _send_to_all(f"❌ 晨报生成失败：{e}", 'morning_report')


def job_midday_review():
    """12:45（周一~周五）— 午间复盘。"""
    log.info("生成午间复盘...")
    try:
        data   = fetch_midday_review()
        report = build_midday_review(data)
        _send_to_all(report, 'midday_review')
        log.info("午间复盘已发送")
    except Exception as e:
        log.error(f"午间复盘失败: {e}")
        _send_to_all(f"❌ 午间复盘生成失败：{e}", 'midday_review')


def job_review():
    """16:30（周一~周五）— 每日收盘复盘。"""
    log.info("生成每日复盘...")
    try:
        data   = fetch_review()
        report = build_review(data)
        _send_to_all(report, 'daily_review')
        log.info("每日复盘已发送")
    except Exception as e:
        log.error(f"复盘失败: {e}")
        _send_to_all(f"❌ 每日复盘生成失败：{e}", 'daily_review')


def job_weekend_summary():
    """19:00（仅周日）— 周末汇总。"""
    log.info("生成周末汇总...")
    try:
        data   = fetch_weekend_summary()
        report = build_weekend_summary(data)
        _send_to_all(report, 'weekend_summary')
        log.info("周末汇总已发送")
    except Exception as e:
        log.error(f"周末汇总失败: {e}")
        _send_to_all(f"❌ 周末汇总生成失败：{e}", 'weekend_summary')


# ── 特种兵改造：每日督促任务 ──────────────────────────────────────────────────

import random

_MORNING_TASKS = [
    "📚 今日阅读任务：继续消费必读书（《定位》/《零售的哲学》/《穷查理宝典》）\n"
    "🎯 完成后在备忘里记一条核心收获（memo 触发词）",
    "🏗️ 今日构建任务：推进「消费投研心法.md」，把周期方法论嫁接到消费品\n"
    "💡 核心公式：消费品赔率 ≈ 品牌定价权 × 渠道去库存进度 ÷ 当前估值",
    "📊 今日研究任务：推进安踏/运动服饰研究底稿\n"
    "🔍 重点关注：库存周转天数的周期规律",
    "🌍 今日研究任务：伊利深加工空间 + 海外乳企对标研究\n"
    "🔍 参考：达能/雀巢/明治的深加工业务占比与利润率",
    "🔬 今日研究任务：潮玩/消费成长赛道扫描\n"
    "💡 复盘泡泡马特的成长路径，提炼消费成长股的筛选框架",
    "✍️ 今日写作任务：推进公众号文章\n"
    "📝 选题方向：投资方法论 / 周期×消费交叉研究 / AI投研理念",
]

_EXPRESSION_TOPICS = [
    "请用60秒讲清楚你对原奶行业当前周期位置的判断",
    "请用60秒向一个不懂周期的人解释什么是困境反转投资",
    "请用60秒讲清楚你的三范式投资框架",
    "请用60秒介绍你自己的投资经历和业绩",
    "请用60秒讲你最成功的一笔投资",
    "请用60秒向面试官解释为什么你要加入一个平台",
    "请用60秒讲清楚运动服饰行业的库存周期逻辑",
    "请用60秒讲清楚AI如何提升你的投研效率",
    "面试官问：你的投资频率太低。请用60秒回应",
    "面试官问：你只做过周期，消费经验不够。请用60秒回应",
    "请用60秒讲清楚你如何用周期视角看消费品",
    "请用60秒讲你最失败的一笔投资以及反思",
]

_MOTIVATIONAL = [
    "🔥 你已经证明了自己能做到10倍。下一个10倍需要更强的表达力和更广的能力圈。",
    "💪 100万到1000万靠的是研究深度，1000万到1亿靠的是研究深度+人脉+表达。",
    "🎯 INTP的分析力是你的天赋，每天花15分钟激活ENTJ模式，让行动力追上思考力。",
    "⚡ 今天的15分钟练习，是未来面试时从容表达的基石。",
    "🏔️ 特种兵改造不靠天赋，靠每天的重复训练。坚持下去。",
    "💎 你的研究能力已经是顶级水平。现在要做的是让表达配得上你的思考。",
]


def _get_training_day() -> int:
    """计算从2026-05-05开始的训练天数。"""
    from datetime import date
    start = date(2026, 5, 5)
    today = date.today()
    return max(1, (today - start).days + 1)


def job_morning_coach():
    """09:30（每天）— 早间专注任务提醒。"""
    log.info("发送早间督促...")
    try:
        task = random.choice(_MORNING_TASKS)
        motivation = random.choice(_MOTIVATIONAL)
        msg = (
            f"☀️ 早安，特种兵改造 Day {_get_training_day()}\n\n"
            f"━━━ 今日专注任务 ━━━\n\n"
            f"{task}\n\n"
            f"━━━━━━━━━━━━━━━━\n\n"
            f"{motivation}\n\n"
            f"💬 回复「训练」开始今日60秒表达力训练"
        )
        _send_to_all(msg, 'morning_coach')
        log.info("早间督促已发送")
    except Exception as e:
        log.error(f"早间督促失败: {e}")


def job_evening_coach():
    """20:00（每天）— 晚间阅读+训练提醒。"""
    log.info("发送晚间督促...")
    try:
        topic = random.choice(_EXPRESSION_TOPICS)
        msg = (
            f"🌙 晚间提醒 — 特种兵改造 Day {_get_training_day()}\n\n"
            f"━━━ 表达力训练 ━━━\n\n"
            f"🎯 今日话题：{topic}\n\n"
            f"📏 要求：200字以内，结构＝结论→论据→风险→判断\n"
            f"🚫 禁词：然后、就是说、其实、反正就是\n\n"
            f"回复「训练」让AI给你出题打分\n\n"
            f"━━━ 阅读时间 ━━━\n\n"
            f"📖 睡前读30分钟消费/投资/非虚构类书籍\n"
            f"📝 读完记一条核心收获（回复 memo + 内容）"
        )
        _send_to_all(msg, 'evening_coach')
        log.info("晚间督促已发送")
    except Exception as e:
        log.error(f"晚间督促失败: {e}")


# ── 入口 ──────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    if not APP_ID or not APP_SECRET:
        log.error("❌ FEISHU_DS_APP_ID / FEISHU_DS_APP_SECRET 未设置，退出")
        sys.exit(1)

    log.info("每日报告Bot 启动（新架构 scheduler_runner）")
    log.info("周一~周五：08:05抓取 / 08:10晨报 / 08:25自选股数据 / 08:30自选股日报 / 12:45午间复盘 / 16:30收盘复盘")
    log.info("周六：08:05抓取 / 08:10晨报 / 08:25自选股数据 / 08:30自选股日报")
    log.info("周日：19:00周末汇总")
    log.info("每天：09:30早间督促 / 20:00晚间训练提醒")

    scheduler = BlockingScheduler(timezone='Asia/Shanghai')

    tz = 'Asia/Shanghai'
    # 周一~周六
    scheduler.add_job(job_fetch_morning,   CronTrigger(day_of_week='mon-sat', hour=8,  minute=5,  timezone=tz))
    scheduler.add_job(job_watchlist,       CronTrigger(day_of_week='mon-sat', hour=8,  minute=25, timezone=tz))
    scheduler.add_job(job_morning_reports, CronTrigger(day_of_week='mon-sat', hour=8,  minute=10, timezone=tz))
    # 周一~周五
    scheduler.add_job(job_midday_review,   CronTrigger(day_of_week='mon-fri', hour=12, minute=45, timezone=tz))
    scheduler.add_job(job_review,          CronTrigger(day_of_week='mon-fri', hour=16, minute=30, timezone=tz))
    # 周日
    scheduler.add_job(job_weekend_summary, CronTrigger(day_of_week='sun',     hour=19, minute=0,  timezone=tz))
    # 每天：特种兵改造督促
    scheduler.add_job(job_morning_coach,   CronTrigger(hour=9,  minute=30, timezone=tz))
    scheduler.add_job(job_evening_coach,   CronTrigger(hour=20, minute=0,  timezone=tz))

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("每日报告Bot 已停止")

