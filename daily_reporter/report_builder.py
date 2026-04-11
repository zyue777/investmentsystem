# daily_reporter/report_builder.py
# 组装 prompt → 调用 DeepSeek → 返回报告文本
# 被 scheduler.py（定时）和 bot_gemini/bot.py（按需）共同调用

import json
import os
import re
import sys
import urllib.request
import urllib.error
from datetime import datetime

_DIR = os.path.dirname(__file__)
with open(os.path.join(_DIR, 'config.json'), 'r', encoding='utf-8') as _f:
    _CFG = json.load(_f)

DEEPSEEK_API_KEY = _CFG['deepseek_api_key']
DEEPSEEK_URL     = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL   = "deepseek-chat"

SYSTEM_PROMPT = (
    "你是越越的财经助手，负责撰写每日财经报告。"
    "风格：简洁、有重点、有逻辑，不写废话，不长篇大论。"
    "格式要符合微信/飞书阅读的舒适感，适当分段，重点加粗用【】标注。"
    "【铁律，违者报告作废】\n"
    "1. 只使用用户消息中明确提供的数字，禁止自行估算、推断或补充任何价格/涨跌幅。\n"
    "2. 若某项数据标注[数据缺失]，原文写【数据暂缺】，不得猜测或用历史数据替代。\n"
    "3. 涨跌幅点评：只对幅度>=±2%的品种撰写原因；若提供的新闻中未提及该品种，"
    "直接写【原因暂未明确】，严禁推断或编造背景。\n"
    "4. 新闻解读仅限用户提供的新闻文本，不得自行添加市场背景或常识性解释。\n"
    "5. 若有整体判断但缺乏数据支撑，写【暂无足够信息支持判断】。"
)


# ── DeepSeek 调用 ─────────────────────────────────────────────────────────────

def _call_deepseek(user_prompt: str) -> str:
    payload = json.dumps({
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_prompt},
        ],
        "max_tokens": 1200,
    }).encode('utf-8')

    req = urllib.request.Request(
        DEEPSEEK_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode('utf-8'))
        choices = result.get('choices', [])
        if choices:
            return choices[0].get('message', {}).get('content', '').strip()
        return "（DeepSeek 无输出）"
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='ignore')
        return f"❌ HTTP错误 {e.code}: {body[:200]}"
    except Exception as e:
        return f"❌ 调用失败: {e}"


# ── 数据格式化辅助 ────────────────────────────────────────────────────────────

def _dict_to_text(d: dict, indent: int = 0) -> str:
    lines = []
    pad = '  ' * indent
    for k, v in d.items():
        if isinstance(v, dict):
            lines.append(f"{pad}{k}：")
            lines.append(_dict_to_text(v, indent + 1))
        else:
            lines.append(f"{pad}{k}：{v}")
    return '\n'.join(lines)


# ── 1. 晨报·股票版 ────────────────────────────────────────────────────────────

def build_morning_stock(data: dict) -> str:
    today = data.get('生成时间', datetime.now().strftime('%Y-%m-%d'))
    data_text = _dict_to_text({k: v for k, v in data.items() if k != '生成时间'})

    prompt = f"""今天是 {today}，请根据以下实时数据撰写【晨报·股票版】。

--- 数据开始 ---
{data_text}
--- 数据结束 ---

输出格式（严格按此结构，300字以内）：
📰 晨报·股票版 | {today[:10]}

【昨夜美股】标普/纳指/道指 涨跌幅。涨跌幅≥±2%才写"⚡"加1句原因（必须来自新闻数据，无数据则写"原因暂未明确"）。

【VIX & 美元】VIX水位+情绪1句。DXY和美元/人民币方向。

【隔夜国际头条】从"隔夜国际头条"数据中，选出最多3条对A股/全球市场影响最大的新闻，每条1行。没有重大新闻则写"暂无重大事件"。

【中概ADR】5只涨跌+1句整体判断。

【A股盘前关注】从宏观日历+财联社快讯提炼2条。

【核心逻辑】1句，今日最值得关注的信号或风险。"""

    return _call_deepseek(prompt)


# ── 2. 晨报·大宗商品版 ───────────────────────────────────────────────────────

def build_morning_commodity(data: dict) -> str:
    today = data.get('生成时间', datetime.now().strftime('%Y-%m-%d'))
    data_text = _dict_to_text({k: v for k, v in data.items() if k != '生成时间'})

    prompt = f"""今天是 {today}，请根据以下实时数据撰写【晨报·大宗商品版】。

--- 数据开始 ---
{data_text}
--- 数据结束 ---

输出格式要求（字数400字以内）：
📊 晨报·大宗商品版 | {today[:10]}

【能源】WTI / 布伦特 / 欧洲天然气TTF  涨跌幅
【贵金属】黄金 白银 铂 钯  涨跌幅
【基本金属】铜 铝 锌 镍 锡  涨跌幅
【农产品】小麦 玉米 大豆 棉花 糖 育肥牛  涨跌幅
【黑色系】螺纹钢 铁矿石  涨跌幅
【新能源】多晶硅  涨跌幅
【生猪】生猪  涨跌幅
【数字资产】比特币  涨跌幅
【美债】30年美债期货 / 10-2收益率曲线（利差方向判断：正=正常，负=倒挂）

标注规则：⚠️ 表示异常波动（±3%以上），在该品种后用1-2句精炼写出核心原因（不超过20字）。
最后一行：【整体判断】1句话概括今日大宗商品整体情绪。"""

    return _call_deepseek(prompt)


# ── 3. 自选股日报 ─────────────────────────────────────────────────────────────

def _write_diary_entries(diary_text: str, stocks: dict):
    """
    解析 DeepSeek 输出的 [DIARY]...[/DIARY] 内容并写入日记文件。
    格式：中文股票名|1-2句基本面摘要
    """
    try:
        _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if _root not in sys.path:
            sys.path.insert(0, _root)
        from sentiment_monitor.diary import write_entry
    except ImportError as e:
        print(f'[report_builder] diary import 失败: {e}')
        return

    diary_map = {}
    for line in diary_text.split('\n'):
        line = line.strip()
        if '|' in line:
            name, summary = line.split('|', 1)
            diary_map[name.strip()] = summary.strip()

    for name, info in stocks.items():
        ticker  = info.get('ticker', '')
        ann     = info.get('公告', '[无重大公告]')
        summary = diary_map.get(name, '暂无')
        try:
            write_entry(ticker=ticker, name=name,
                        ann_text=ann, sentiment_text=summary)
        except Exception as e:
            print(f'[report_builder] 写日记 {name} 失败: {e}')


def build_watchlist(data: dict) -> str:
    today = data.get('生成时间', datetime.now().strftime('%Y-%m-%d'))
    stocks = data.get('stocks', {})
    ai_news = data.get('AI行业动态', '[数据缺失]')

    # 格式化自选股数据（含 StockTwits 原文，供 DeepSeek 提炼）
    stock_lines = []
    for name, info in stocks.items():
        ticker = info.get('ticker', '')
        price  = info.get('价格', '[数据缺失]')
        ann    = info.get('公告', '[无重大公告]')
        raw    = info.get('舆情原始', [])

        line = f'  {name}({ticker})  {price}  公告：{ann}'
        if raw:
            line += '\n  StockTwits近期讨论（原文）：'
            for i, msg in enumerate(raw[:5], 1):
                line += f'\n    {i}. {msg}'
        else:
            line += '\n  社区讨论：暂无数据'
        stock_lines.append(line)

    stocks_text = '\n'.join(stock_lines)

    prompt = f"""今天是 {today}，请根据以下数据完成两项任务。

--- 自选股数据 ---
{stocks_text}

--- AI行业动态 ---
{ai_news}
--- 数据结束 ---

严格按以下格式输出，两个标签缺一不可：

[REPORT]
📌 自选股日报 | {today[:10]}

（每只股票一行：股票名(代码)  涨跌幅  公告情况一句话）
（若有StockTwits讨论原文，在下方缩进一行：└ 基本面：从原文提炼1条运营/产品/竞争观点，忽略价格预测和纯交易讨论）

【社区关注】今日哪只股票的讨论最有基本面价值（无有效数据写"暂无社区讨论数据"）
【AI行业】{ai_news[:80]}
[/REPORT]
[DIARY]
（每只股票一行，格式：中文股票名|1-2句基本面摘要，只写原文直接支持的观点，无数据写"暂无"）
[/DIARY]"""

    full_output = _call_deepseek(prompt)

    # 解析报告部分（fallback：使用全部输出）
    report_match = re.search(r'\[REPORT\](.*?)\[/REPORT\]', full_output, re.DOTALL)
    report_text  = report_match.group(1).strip() if report_match else full_output

    # 解析日记部分并写入文件（side effect，不影响报告返回）
    diary_match = re.search(r'\[DIARY\](.*?)\[/DIARY\]', full_output, re.DOTALL)
    if diary_match:
        _write_diary_entries(diary_match.group(1).strip(), stocks)

    return report_text


# ── 4. 每日复盘 ───────────────────────────────────────────────────────────────

def build_review(data: dict) -> str:
    today = data.get('生成时间', datetime.now().strftime('%Y-%m-%d'))
    data_text = _dict_to_text({k: v for k, v in data.items() if k != '生成时间'})

    prompt = f"""今天是 {today}，请根据以下实时数据撰写【每日复盘】。

--- 数据开始 ---
{data_text}
--- 数据结束 ---

输出格式要求（字数500字以内，逻辑清晰，因果分明）：
📉 每日复盘 | {today[:10]}

【A股指数】上证 / 深成 / 创业板  涨跌幅 + 成交额
【港股】恒指 / 恒生科技  涨跌幅
【板块】领涨：... / 领跌：...（写出代表股 + 一句逻辑）
【资金面】北向资金净流入/流出 + 1句判断
【今日驱动】逐条列出核心因素（2-4条，每条一行，必须来自数据；无数据则写"暂无足够信息"）
【结构信号】若今日波动不大，分析资金在哪些方向聚集/撤离（无数据则跳过此节）"""

    return _call_deepseek(prompt)


# ── 5. 午间复盘 ───────────────────────────────────────────────────────────────

def build_midday_review(data: dict) -> str:
    today = data.get('生成时间', datetime.now().strftime('%Y-%m-%d'))
    data_text = _dict_to_text({k: v for k, v in data.items() if k != '生成时间'})

    prompt = f"""今天是 {today}，请根据以下数据撰写【午间复盘】（200字以内）。

--- 数据开始 ---
{data_text}
--- 数据结束 ---

格式：
🕛 午间复盘 | {today[:10]}

【上午重大事件】从"重大财经新闻"和"财联社快讯"中，严格筛选出最多3条真正重大的宏观或行业事件（央行决策/重大经济数据/地缘政治/监管政策/重大并购）。无足够重大事件则写"暂无重大事件"。每条1行，不超过30字。

【A股上午板块】
领涨：（板块名+涨幅，逐一列出）
领跌：（板块名+跌幅，逐一列出）

【港股】恒指/恒生科技 各报多少，涨跌幅。

注意：板块点评只写数字事实，无新闻支撑则不写原因。"""

    return _call_deepseek(prompt)


# ── 6. 周末汇总 ───────────────────────────────────────────────────────────────

def build_weekend_summary(data: dict) -> str:
    today = data.get('生成时间', datetime.now().strftime('%Y-%m-%d'))
    stocks = data.get('stocks', {})

    stock_lines = []
    for name, info in stocks.items():
        ticker = info.get('ticker', '')
        price  = info.get('价格', '[数据缺失]')
        stock_lines.append(f"  {name}({ticker})  {price}")
    stocks_text = '\n'.join(stock_lines)

    intl_news   = data.get('周末国际要闻', '[数据缺失]')
    cls_news    = data.get('财联社周末快讯', '[数据缺失]')
    ai_news     = data.get('AI产业动态', '[数据缺失]')

    prompt = f"""今天是 {today}（周日），请根据以下数据撰写【周末汇总】（350字以内）。

--- 自选股（周五收盘）---
{stocks_text}

--- 周末国际要闻 ---
{intl_news}

--- 财联社周末快讯 ---
{cls_news}

--- AI产业动态 ---
{ai_news}

格式：
📋 周末汇总 | {today[:10]}

【自选股本周表现】每只1行：名称 涨跌幅 一句话（无公告则写"无公告"）。

【本周末重大事件】严格从以上新闻数据中选出不超过5条宏观/行业重大事件，按影响力排序。\
无充分数据支撑的事件不列入。

【AI产业最新动态】仅列出有新闻数据支撑的重大AI产业变化（不超过3条），无数据则写"本周末暂无重大AI动态"。

【值得关注的信号】若新闻数据中有明确的重要信号，列出1-2条。若数据不足，写"数据不足，暂不点评"。"""

    return _call_deepseek(prompt)


# ── 快捷入口（供 bot 按需调用）────────────────────────────────────────────────

def generate_morning_stock() -> str:
    from .data_fetcher import fetch_morning_stock
    return build_morning_stock(fetch_morning_stock())


def generate_morning_commodity() -> str:
    from .data_fetcher import fetch_morning_commodity
    return build_morning_commodity(fetch_morning_commodity())


def generate_watchlist() -> str:
    from .data_fetcher import fetch_watchlist
    return build_watchlist(fetch_watchlist())


def generate_review() -> str:
    from .data_fetcher import fetch_review
    return build_review(fetch_review())


def generate_midday_review() -> str:
    from .data_fetcher import fetch_midday_review
    return build_midday_review(fetch_midday_review())


def generate_weekend_summary() -> str:
    from .data_fetcher import fetch_weekend_summary
    return build_weekend_summary(fetch_weekend_summary())
