# sentiment_monitor/diary.py
# 自选股日记管理：每只股票一个月度 md，按日追加，幂等写入
#
# 文件结构：
#   sentiment_monitor/data/{TICKER_DIR}/{YYYY-MM}.md
#   ticker 映射：9858.HK → HK09858，CROX → CROX
#
# 每日条目格式：
#   ## 2026-04-10
#   **重大公告：**
#   ...
#   **社区讨论要点：**
#   ...
#   ---

import os
import re
from datetime import datetime, timedelta

_DIARY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')


def ticker_to_dir(ticker: str) -> str:
    """将 ticker 映射为日记目录名：9858.HK → HK09858，CROX → CROX"""
    if ticker.endswith('.HK'):
        return 'HK' + ticker.replace('.HK', '').zfill(5)
    return ticker


def _month_path(ticker: str) -> str:
    month = datetime.now().strftime('%Y-%m')
    return os.path.join(_DIARY_DIR, ticker_to_dir(ticker), f'{month}.md')


def today_written(ticker: str) -> bool:
    """检查今日条目是否已写入（幂等判断）"""
    path = _month_path(ticker)
    if not os.path.exists(path):
        return False
    today = datetime.now().strftime('%Y-%m-%d')
    with open(path, 'r', encoding='utf-8') as f:
        return f'## {today}' in f.read()


def write_entry(ticker: str, name: str, ann_text: str, sentiment_text: str) -> bool:
    """
    写入今日日记条目（幂等：今日已存在则跳过）。
    返回 True=写入成功，False=已存在跳过。
    """
    path = _month_path(ticker)
    today = datetime.now().strftime('%Y-%m-%d')

    os.makedirs(os.path.dirname(path), exist_ok=True)

    # 幂等检查
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            if f'## {today}' in f.read():
                return False
    else:
        # 新文件：写入标题行
        with open(path, 'w', encoding='utf-8') as f:
            f.write(f'# {ticker_to_dir(ticker)} ({name}) 自选股日志\n\n')

    # 追加今日条目
    entry = (
        f'## {today}\n\n'
        f'**重大公告：**\n{ann_text}\n\n'
        f'**社区讨论要点：**\n{sentiment_text}\n\n'
        f'---\n\n'
    )
    with open(path, 'a', encoding='utf-8') as f:
        f.write(entry)
    return True


def read_recent(ticker: str, days: int = 7) -> str:
    """读取最近 N 天的日记条目，返回 markdown 文本"""
    path = _month_path(ticker)
    if not os.path.exists(path):
        return '[暂无历史记录]'

    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 按日期块分割（## YYYY-MM-DD 开头）
    blocks = re.split(r'\n(?=## \d{4}-\d{2}-\d{2})', content)
    cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

    recent = []
    for block in blocks:
        m = re.match(r'## (\d{4}-\d{2}-\d{2})', block.strip())
        if m and m.group(1) >= cutoff:
            recent.append(block.strip())

    return '\n\n'.join(recent) if recent else '[近期暂无记录]'
