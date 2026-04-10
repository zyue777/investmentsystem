#!/usr/bin/env python3
# daily_reporter/scheduler.py
# 定时任务调度器
#
# ━━━━ 工作日（周一~周五）━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#   08:25  抓取晨间数据缓存
#   08:30  发送自选股日报
#   09:00  发送晨报·股票版 + 晨报·大宗商品版
#   12:30  发送午间复盘（A/H板块 + 重大新闻）
#   16:30  发送每日复盘
#
# ━━━━ 周六 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#   08:25  抓取晨间数据缓存
#   08:30  发送自选股日报
#   09:00  发送晨报·股票版 + 晨报·大宗商品版（无午间复盘/收盘复盘）
#
# ━━━━ 周日 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#   19:00  发送周末汇总（自选股 + 重大新闻 + AI产业动态）

import json
import os
import sys
import time
import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

# 路径设置
_THIS_DIR   = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR   = os.path.dirname(_THIS_DIR)
_SHARED_DIR = os.path.join(_ROOT_DIR, 'shared')
sys.path.insert(0, _ROOT_DIR)
sys.path.insert(0, _SHARED_DIR)

from shared.feishu_utils import get_tenant_access_token, send_text_message
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

# ── 日志 ──────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s %(message)s',
    datefmt='%H:%M:%S'
)
log = logging.getLogger('scheduler')

# ── 读取配置 ──────────────────────────────────────────────────────────────────
with open(os.path.join(_THIS_DIR, 'config.json'), 'r', encoding='utf-8') as f:
    CFG = json.load(f)

APP_ID     = CFG['feishu_app_id']
APP_SECRET = CFG['feishu_app_secret']

REGISTRY_PATH = os.path.join(_SHARED_DIR, 'user_registry.json')

# 晨间数据缓存（8:25 抓取，8:30 和 9:00 复用）
_morning_cache: dict = {}


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def _get_recipients() -> list:
    """从 user_registry.json 读取所有已注册用户的 open_id"""
    try:
        if not os.path.exists(REGISTRY_PATH):
            log.warning("user_registry.json 不存在，请先给 DeepSeek 机器人发一条消息")
            return []
        with open(REGISTRY_PATH, 'r', encoding='utf-8') as f:
            reg = json.load(f)
        return list(reg.get('open_ids', {}).values()) or list(reg.values())
    except Exception as e:
        log.error(f"读取 registry 失败: {e}")
        return []


def _send_to_all(text: str):
    """发送消息给所有注册用户"""
    recipients = _get_recipients()
    if not recipients:
        log.warning("没有注册用户，消息未发送")
        return
    token = get_tenant_access_token(APP_ID, APP_SECRET)
    if not token:
        log.error("获取飞书 token 失败")
        return
    for open_id in recipients:
        ok = send_text_message(token, open_id, text)
        log.info(f"发送给 {open_id[:8]}...  {'✅' if ok else '❌'}")


def _truncate(text: str, limit: int = 3000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + '\n\n…（内容过长已截断）'


# ── 任务函数 ──────────────────────────────────────────────────────────────────

def job_fetch_morning():
    """08:25（周一~周六）— 抓取晨间数据，缓存备用"""
    global _morning_cache
    log.info("开始抓取晨间数据...")
    try:
        _morning_cache['stock']     = fetch_morning_stock()
        _morning_cache['commodity'] = fetch_morning_commodity()
        _morning_cache['watchlist'] = fetch_watchlist()
        log.info("晨间数据抓取完成")
    except Exception as e:
        log.error(f"晨间数据抓取失败: {e}")


def job_watchlist():
    """08:30（周一~周六）— 发送自选股日报"""
    log.info("生成自选股日报...")
    try:
        data   = _morning_cache.get('watchlist') or fetch_watchlist()
        report = build_watchlist(data)
        _send_to_all(_truncate(report))
        log.info("自选股日报已发送")
    except Exception as e:
        log.error(f"自选股日报失败: {e}")
        _send_to_all(f"❌ 自选股日报生成失败：{e}")


def job_morning_reports():
    """09:00（周一~周六）— 发送晨报·股票版 + 晨报·大宗商品版"""
    log.info("生成晨报...")
    try:
        stock_data     = _morning_cache.get('stock')     or fetch_morning_stock()
        commodity_data = _morning_cache.get('commodity') or fetch_morning_commodity()

        stock_report     = build_morning_stock(stock_data)
        commodity_report = build_morning_commodity(commodity_data)

        _send_to_all(_truncate(stock_report))
        time.sleep(2)
        _send_to_all(_truncate(commodity_report))
        log.info("晨报已发送")
    except Exception as e:
        log.error(f"晨报失败: {e}")
        _send_to_all(f"❌ 晨报生成失败：{e}")


def job_midday_review():
    """12:30（周一~周五）— 发送午间复盘"""
    log.info("生成午间复盘...")
    try:
        data   = fetch_midday_review()
        report = build_midday_review(data)
        _send_to_all(_truncate(report))
        log.info("午间复盘已发送")
    except Exception as e:
        log.error(f"午间复盘失败: {e}")
        _send_to_all(f"❌ 午间复盘生成失败：{e}")


def job_review():
    """16:30（周一~周五）— 发送每日复盘"""
    log.info("生成每日复盘...")
    try:
        data   = fetch_review()
        report = build_review(data)
        _send_to_all(_truncate(report))
        log.info("每日复盘已发送")
    except Exception as e:
        log.error(f"复盘失败: {e}")
        _send_to_all(f"❌ 每日复盘生成失败：{e}")


def job_weekend_summary():
    """19:00（仅周日）— 发送周末汇总"""
    log.info("生成周末汇总...")
    try:
        data   = fetch_weekend_summary()
        report = build_weekend_summary(data)
        _send_to_all(_truncate(report))
        log.info("周末汇总已发送")
    except Exception as e:
        log.error(f"周末汇总失败: {e}")
        _send_to_all(f"❌ 周末汇总生成失败：{e}")


# ── 启动调度器 ────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    log.info("每日报告调度器启动（时区：Asia/Shanghai）")
    log.info("周一~周五：08:25抓取 / 08:30自选股 / 09:00晨报 / 12:30午间复盘 / 16:30收盘复盘")
    log.info("周六：08:25抓取 / 08:30自选股 / 09:00晨报（无午间/收盘复盘）")
    log.info("周日：19:00周末汇总")

    scheduler = BlockingScheduler(timezone='Asia/Shanghai')

    # 周一~周六：晨间数据 + 自选股 + 晨报
    scheduler.add_job(job_fetch_morning,   CronTrigger(day_of_week='mon-sat', hour=8,  minute=25, timezone='Asia/Shanghai'))
    scheduler.add_job(job_watchlist,       CronTrigger(day_of_week='mon-sat', hour=8,  minute=30, timezone='Asia/Shanghai'))
    scheduler.add_job(job_morning_reports, CronTrigger(day_of_week='mon-sat', hour=9,  minute=0,  timezone='Asia/Shanghai'))

    # 周一~周五：午间复盘 + 收盘复盘
    scheduler.add_job(job_midday_review,   CronTrigger(day_of_week='mon-fri', hour=12, minute=30, timezone='Asia/Shanghai'))
    scheduler.add_job(job_review,          CronTrigger(day_of_week='mon-fri', hour=16, minute=30, timezone='Asia/Shanghai'))

    # 周日：周末汇总
    scheduler.add_job(job_weekend_summary, CronTrigger(day_of_week='sun',     hour=19, minute=0,  timezone='Asia/Shanghai'))

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("调度器已停止")
