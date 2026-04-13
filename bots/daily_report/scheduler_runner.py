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


# ── 入口 ──────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    if not APP_ID or not APP_SECRET:
        log.error("❌ FEISHU_DS_APP_ID / FEISHU_DS_APP_SECRET 未设置，退出")
        sys.exit(1)

    log.info("每日报告Bot 启动（新架构 scheduler_runner）")
    log.info("周一~周五：08:05抓取 / 08:10晨报 / 08:25自选股数据 / 08:30自选股日报 / 12:45午间复盘 / 16:30收盘复盘")
    log.info("周六：08:05抓取 / 08:10晨报 / 08:25自选股数据 / 08:30自选股日报")
    log.info("周日：19:00周末汇总")

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

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("每日报告Bot 已停止")
