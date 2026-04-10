# daily_reporter/data_fetcher.py
# 统一市场数据抓取模块
# 原则：所有数字由本模块抓取，DeepSeek 不生成任何价格/涨跌幅
#
# 数据源：
#   yfinance  — 美股、港股、大宗商品期货（免费）
#   akshare   — 财联社新闻、A股板块、港股（免费）
#   tushare   — A股指数、北向资金、公告（已有 token）

import json
import os
import ssl
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime

import yfinance as yf
import akshare as ak
import tushare as ts

# ── 初始化 Tushare ────────────────────────────────────────────────────────────
_DIR = os.path.dirname(__file__)
with open(os.path.join(_DIR, 'config.json'), 'r', encoding='utf-8') as _f:
    _CFG = json.load(_f)

ts.set_token(_CFG['tushare_token'])
_pro = ts.pro_api()

WATCHLIST: dict = _CFG['watchlist']  # {"优然牧业": "9858.HK", ...}
FRED_KEY: str = _CFG.get('fred_api_key', '')


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def _safe(fn, default='[数据缺失]'):
    """执行 fn()，任何异常返回 default"""
    try:
        return fn()
    except Exception as e:
        print(f"[data_fetcher] {fn.__name__ if hasattr(fn,'__name__') else '?'} 失败: {e}")
        return default


def _yf_price(ticker: str) -> dict:
    """返回 {close, prev_close, pct_chg} 或 {error}"""
    try:
        t = yf.Ticker(ticker)
        h = t.history(period='5d')
        if len(h) < 2:
            return {'error': '数据不足'}
        close = round(float(h['Close'].iloc[-1]), 4)
        prev  = round(float(h['Close'].iloc[-2]), 4)
        pct   = round((close / prev - 1) * 100, 2)
        return {'close': close, 'prev_close': prev, 'pct_chg': pct}
    except Exception as e:
        return {'error': str(e)[:60]}


def _fmt_price(d: dict, unit: str = '') -> str:
    """把 _yf_price 结果格式化成字符串"""
    if 'error' in d:
        return '[数据缺失]'
    sign = '+' if d['pct_chg'] >= 0 else ''
    return f"{d['close']}{unit}  {sign}{d['pct_chg']}%"


def _tushare_fut_pct(df, prefix: str) -> dict:
    """
    从 tushare fut_daily 结果（无 pct_chg 列）中提取主连数据，
    用 close/pre_close 手动计算涨跌幅。
    返回 {close, pre_close, pct_chg} 或 {error}
    """
    try:
        row = df[df['ts_code'] == prefix].iloc[0]
        close = float(row['close'])
        pre   = float(row['pre_close'])
        pct   = round((close / pre - 1) * 100, 2)
        return {'close': round(close, 2), 'pre_close': round(pre, 2), 'pct_chg': pct}
    except Exception as e:
        return {'error': str(e)[:60]}


def _fred_yield(series_id: str) -> float | None:
    """从 FRED API 取最新收益率（%），返回 float 或 None"""
    if not FRED_KEY:
        return None
    url = (f"https://api.stlouisfed.org/fred/series/observations"
           f"?series_id={series_id}&api_key={FRED_KEY}"
           f"&file_type=json&sort_order=desc&limit=5")
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode())
        for obs in data.get('observations', []):
            if obs['value'] != '.':
                return round(float(obs['value']), 3)
    except Exception as e:
        print(f"[data_fetcher] FRED {series_id} 失败: {e}")
    return None


_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE

_INVEST_RSS = {
    'economy': 'https://www.investing.com/rss/news_14.rss',
    'general': 'https://www.investing.com/rss/news.rss',
}

def _fetch_investing_news(n: int = 5, hours_back: int = 16) -> str:
    """
    从 Investing.com RSS 取最近财经头条（免费）。
    hours_back: 只保留最近 N 小时内的新闻（过滤老旧条目）。
    返回多行字符串，每行 "[MM-DD HH:MM] title"。
    """
    cutoff = datetime.utcnow() - timedelta(hours=hours_back)
    seen, lines = set(), []

    for url in [_INVEST_RSS['economy'], _INVEST_RSS['general']]:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10, context=_SSL_CTX) as r:
                root = ET.fromstring(r.read().decode('utf-8', errors='ignore'))
        except Exception as e:
            print(f"[data_fetcher] Investing RSS {url}: {e}")
            continue

        for item in root.findall('.//item'):
            title_el = item.find('title')
            pub_el   = item.find('pubDate')
            if not (title_el is not None and title_el.text):
                continue
            t = title_el.text.strip()
            if len(t) < 20 or 'test' in t.lower() or t in seen:
                continue
            time_str = ''
            if pub_el is not None and pub_el.text:
                raw_t = pub_el.text.strip()
                try:
                    # email RFC 2822 格式：Thu, 10 Apr 2026 09:18:32 +0000
                    pub_dt = parsedate_to_datetime(raw_t).replace(tzinfo=None)
                    if pub_dt < cutoff:
                        continue
                    time_str = pub_dt.strftime('%m-%d %H:%M')
                except Exception:
                    # 回退：直接截取字符串（格式如 2026-04-10 09:18:32）
                    time_str = raw_t[:16] if len(raw_t) >= 16 else raw_t
            seen.add(t)
            lines.append(f"[{time_str}] {t}")
            if len(lines) >= n:
                break
        if len(lines) >= n:
            break

    return '\n'.join(lines) if lines else '[数据缺失]'


# ── 1. 晨报·股票版 数据 ────────────────────────────────────────────────────────

def fetch_morning_stock() -> dict:
    """
    返回晨报股票版所需数据字典。
    在 8:25 左右调用，取美股昨夜收盘数据。
    """
    data = {}

    # 美股三大指数
    indices = {}
    for name, sym in [('标普500', '^GSPC'), ('纳斯达克', '^IXIC'), ('道琼斯', '^DJI')]:
        indices[name] = _fmt_price(_yf_price(sym))
    data['美股三大指数'] = indices

    # VIX 恐慌指数
    vix_d = _yf_price('^VIX')
    if 'error' not in vix_d:
        lvl  = vix_d['close']
        pct  = vix_d['pct_chg']
        sign = '+' if pct >= 0 else ''
        # 水位标注
        if lvl >= 30:
            level_tag = '（极度恐慌）'
        elif lvl >= 25:
            level_tag = '（市场恐慌）'
        elif lvl <= 15:
            level_tag = '（极度平静）'
        else:
            level_tag = ''
        data['VIX恐慌指数'] = f"{lvl}  {sign}{pct}%{level_tag}"
    else:
        data['VIX恐慌指数'] = '[数据缺失]'

    # 美元指数 & 人民币汇率
    data['美元指数DXY'] = _fmt_price(_yf_price('DX-Y.NYB'))
    rmb_d = _yf_price('CNY=X')   # 在岸 USD/CNY，离岸 CNH 走势基本一致
    if 'error' not in rmb_d:
        pct  = rmb_d['pct_chg']
        sign = '+' if pct >= 0 else ''
        # pct>0 表示美元升值/人民币贬值
        direction = '（人民币贬值）' if pct > 0.1 else ('（人民币升值）' if pct < -0.1 else '')
        data['美元/人民币'] = f"{rmb_d['close']}  {sign}{pct}%{direction}"
    else:
        data['美元/人民币'] = '[数据缺失]'

    # 中概ADR（5只代表性股票）
    adr = {}
    for name, sym in [('阿里BABA', 'BABA'), ('网易NTES', 'NTES'),
                      ('京东JD', 'JD'), ('拼多多PDD', 'PDD'), ('携程TCOM', 'TCOM')]:
        adr[name] = _fmt_price(_yf_price(sym), '$')
    data['中概ADR'] = adr

    # 美股科技巨头（用于亮点点评）
    tech = {}
    for name, sym in [('英伟达NVDA', 'NVDA'), ('苹果AAPL', 'AAPL'),
                      ('微软MSFT', 'MSFT'), ('特斯拉TSLA', 'TSLA'), ('Meta', 'META')]:
        tech[name] = _fmt_price(_yf_price(sym), '$')
    data['美股科技巨头'] = tech

    # S&P 500 主要板块 ETF（用于领涨/领跌判断）
    sector_map = {
        'XLK科技': 'XLK', 'XLF金融': 'XLF', 'XLE能源': 'XLE',
        'XLY非必需消费': 'XLY', 'XLC通信': 'XLC', 'XLI工业': 'XLI',
        'XLV医疗': 'XLV', 'XLP必需消费': 'XLP', 'XLB材料': 'XLB',
    }
    sectors = {}
    for name, sym in sector_map.items():
        sectors[name] = _fmt_price(_yf_price(sym))
    data['美股板块ETF'] = sectors

    # 财联社全球快讯（前 10 条，供 DeepSeek 定位大涨/大跌原因）
    try:
        df = ak.stock_info_global_cls()
        if not df.empty:
            lines = []
            for _, row in df.head(10).iterrows():
                t     = str(row.get('发布时间', ''))[:5]
                title = str(row.get('标题', '') or row.get('内容', ''))[:100]
                lines.append(f"[{t}] {title}")
            data['财联社快讯'] = '\n'.join(lines)
        else:
            data['财联社快讯'] = '[数据缺失]'
    except Exception as e:
        data['财联社快讯'] = f'[数据缺失]'

    # 今日宏观日程
    try:
        cal = ak.news_economic_baidu()
        if not cal.empty:
            today = datetime.now().strftime('%Y-%m-%d')
            rows = cal[cal.get('date', cal.columns[0]).astype(str).str.startswith(today)] if 'date' in cal.columns else cal.head(5)
            data['宏观日历'] = '\n'.join(rows.iloc[:, 1].astype(str).head(5).tolist()) if not rows.empty else '[无重要事件]'
        else:
            data['宏观日历'] = '[数据缺失]'
    except Exception:
        data['宏观日历'] = '[数据缺失]'

    # 隔夜国际财经头条（Investing.com，免费 RSS）
    data['隔夜国际头条'] = _fetch_investing_news(n=5, hours_back=14)

    data['生成时间'] = datetime.now().strftime('%Y-%m-%d %H:%M')
    return data


# ── 2. 晨报·大宗商品版 数据 ───────────────────────────────────────────────────

def _recent_tushare_date(exchange: str, days_back: int = 5) -> str | None:
    """向前查找最近有数据的交易日，返回 yyyymmdd 或 None"""
    today = datetime.now()
    for i in range(1, days_back + 1):
        d = (today - timedelta(days=i)).strftime('%Y%m%d')
        try:
            df = _pro.fut_daily(trade_date=d, fut_type='1', exchange=exchange)
            if df is not None and not df.empty:
                return d
        except Exception:
            continue
    return None


def _fmt_tushare(d: dict, unit: str = '') -> str:
    """格式化 _tushare_fut_pct 结果"""
    if 'error' in d:
        return '[数据缺失]'
    sign = '+' if d['pct_chg'] >= 0 else ''
    flag = '  ⚠️异常波动' if abs(d['pct_chg']) >= 3 else ''
    return f"{d['close']}{unit}  {sign}{d['pct_chg']}%{flag}"


def fetch_morning_commodity() -> dict:
    """返回大宗商品晨报数据（截至当日9点开盘前的前一日收盘），含涨跌幅及异常标注"""
    data = {}

    # ── yfinance 品种（国际市场，前一日收盘）────────────────────────────────────
    yf_map = {
        # 能源
        'WTI原油':     ('CL=F',    '$'),
        '布伦特原油':   ('BZ=F',    '$'),
        '欧洲天然气TTF': ('TTF=F',  '€/MWh'),
        # 贵金属
        '黄金':        ('GC=F',    '$'),
        '白银':        ('SI=F',    '$'),
        '铂金':        ('PL=F',    '$'),
        '钯金':        ('PA=F',    '$'),
        # 基本金属
        '铜':          ('HG=F',    '$'),
        # 农产品
        '小麦':        ('ZW=F',    '¢'),
        '玉米':        ('ZC=F',    '¢'),
        '大豆':        ('ZS=F',    '¢'),
        '棉花':        ('CT=F',    '¢'),
        '糖':          ('SB=F',    '¢'),
        '育肥牛':       ('GF=F',   '¢/lb'),
        # 数字资产
        '比特币':       ('BTC-USD', '$'),
        # 美债期货
        '30年美债期货':  ('ZB=F',   '$'),
    }

    for name, (sym, unit) in yf_map.items():
        d = _yf_price(sym)
        text = _fmt_price(d, unit)
        if 'pct_chg' in d and abs(d['pct_chg']) >= 3.0:
            text += '  ⚠️异常波动'
        data[name] = text

    # ── 10-2 美债收益率曲线（FRED）──────────────────────────────────────────────
    y10 = _fred_yield('DGS10')
    y2  = _fred_yield('DGS2')
    if y10 is not None and y2 is not None:
        spread = round(y10 - y2, 3)
        sign   = '+' if spread >= 0 else ''
        data['10Y美债收益率'] = f"{y10}%"
        data['2Y美债收益率']  = f"{y2}%"
        data['10-2收益率曲线'] = f"{sign}{spread}%（10Y{y10}% - 2Y{y2}%）"
    else:
        data['10-2收益率曲线'] = '[数据缺失]'

    # ── 国内期货（tushare，取最近交易日）────────────────────────────────────────
    # 黑色系：螺纹钢(RB) SHFE、铁矿石(I) DCE
    shfe_date = _recent_tushare_date('SHFE')
    dce_date  = _recent_tushare_date('DCE')
    gfex_date = _recent_tushare_date('GFEX')

    if shfe_date:
        df_shfe = _pro.fut_daily(trade_date=shfe_date, fut_type='1', exchange='SHFE')
    else:
        df_shfe = None

    if dce_date:
        df_dce = _pro.fut_daily(trade_date=dce_date, fut_type='1', exchange='DCE')
    else:
        df_dce = None

    if gfex_date:
        df_gfex = _pro.fut_daily(trade_date=gfex_date, fut_type='1', exchange='GFEX')
    else:
        df_gfex = None

    # 黑色系
    for name, ts_code, df in [('螺纹钢', 'RB.SFE', df_shfe),
                               ('铁矿石', 'I.DCE',  df_dce)]:
        if df is not None and not df.empty:
            # 主连代码 SHFE=RB.SFE / DCE=I.DCE，tushare 主连后缀
            # 直接取以品种开头的第一行（主力或主连）
            prefix = ts_code.split('.')[0]
            sub = df[df['ts_code'].str.startswith(prefix + '.')]
            d = _tushare_fut_pct(sub.iloc[:1].reset_index(drop=True).rename(
                columns={'ts_code': 'ts_code'}), sub.iloc[0]['ts_code']) if not sub.empty else {'error': '无数据'}
            # 简化：直接拿第一行计算
            if not sub.empty:
                row = sub.iloc[0]
                try:
                    close = round(float(row['close']), 2)
                    pre   = round(float(row['pre_close']), 2)
                    pct   = round((close / pre - 1) * 100, 2)
                    sign  = '+' if pct >= 0 else ''
                    flag  = '  ⚠️异常波动' if abs(pct) >= 3 else ''
                    data[name] = f"{close}元  {sign}{pct}%{flag}"
                except Exception:
                    data[name] = '[数据缺失]'
            else:
                data[name] = '[数据缺失]'
        else:
            data[name] = '[数据缺失]'

    # 铝/锌/镍/锡 SHFE
    for name, prefix in [('铝', 'AL'), ('锌', 'ZN'), ('镍', 'NI'), ('锡', 'SN')]:
        if df_shfe is not None and not df_shfe.empty:
            sub = df_shfe[df_shfe['ts_code'].str.startswith(prefix + '.')]
            if not sub.empty:
                row = sub.iloc[0]
                try:
                    close = round(float(row['close']), 2)
                    pre   = round(float(row['pre_close']), 2)
                    pct   = round((close / pre - 1) * 100, 2)
                    sign  = '+' if pct >= 0 else ''
                    flag  = '  ⚠️异常波动' if abs(pct) >= 3 else ''
                    data[name] = f"{close}元  {sign}{pct}%{flag}"
                except Exception:
                    data[name] = '[数据缺失]'
            else:
                data[name] = '[数据缺失]'
        else:
            data[name] = '[数据缺失]'

    # 多晶硅主连 PS.GFE（GFEX）
    if df_gfex is not None and not df_gfex.empty:
        sub = df_gfex[df_gfex['ts_code'] == 'PS.GFE']
        if not sub.empty:
            row = sub.iloc[0]
            try:
                close = round(float(row['close']), 2)
                pre   = round(float(row['pre_close']), 2)
                pct   = round((close / pre - 1) * 100, 2)
                sign  = '+' if pct >= 0 else ''
                flag  = '  ⚠️异常波动' if abs(pct) >= 3 else ''
                data['多晶硅'] = f"{close}元/吨  {sign}{pct}%{flag}"
            except Exception:
                data['多晶硅'] = '[数据缺失]'
        else:
            data['多晶硅'] = '[数据缺失]'
    else:
        data['多晶硅'] = '[数据缺失]'

    # 生猪主连 LH.DCE（DCE）
    if df_dce is not None and not df_dce.empty:
        sub = df_dce[df_dce['ts_code'] == 'LH.DCE']
        if not sub.empty:
            row = sub.iloc[0]
            try:
                close = round(float(row['close']), 2)
                pre   = round(float(row['pre_close']), 2)
                pct   = round((close / pre - 1) * 100, 2)
                sign  = '+' if pct >= 0 else ''
                flag  = '  ⚠️异常波动' if abs(pct) >= 3 else ''
                data['生猪'] = f"{close}元/吨  {sign}{pct}%{flag}"
            except Exception:
                data['生猪'] = '[数据缺失]'
        else:
            data['生猪'] = '[数据缺失]'
    else:
        data['生猪'] = '[数据缺失]'

    data['生成时间'] = datetime.now().strftime('%Y-%m-%d %H:%M')
    return data


# ── 3. 自选股日报 数据 ────────────────────────────────────────────────────────

def fetch_watchlist() -> dict:
    """
    返回7只自选股的前日涨跌幅、公告摘要、相关新闻。
    在 8:25 左右调用。
    """
    data = {'stocks': {}}
    today = datetime.now()
    yest  = (today - timedelta(days=1)).strftime('%Y%m%d')

    for name, ticker in WATCHLIST.items():
        info = {'ticker': ticker}

        # 1. 价格/涨跌
        pd = _yf_price(ticker)
        info['价格'] = _fmt_price(pd)

        # 2. 公告扫描
        ann_text = '[无重大公告]'
        if ticker.endswith('.HK'):
            # 港股用 tushare（港股代码如 09858.HK → 09858）
            try:
                hk_code = ticker.replace('.HK', '').zfill(5) + '.HK'
                anns = _pro.anns(ts_code=hk_code, start_date=yest, end_date=yest,
                                 ann_type='A')
                if anns is not None and not anns.empty:
                    titles = anns['title'].dropna().head(3).tolist()
                    ann_text = '；'.join(titles) if titles else '[无重大公告]'
            except Exception:
                ann_text = '[公告接口暂不可用]'
        else:
            # 美股：yfinance .news (最近新闻作为公告替代)
            try:
                t = yf.Ticker(ticker)
                news = t.news
                if news:
                    recent = [n['content']['title'] for n in news[:2]
                              if 'content' in n and 'title' in n['content']]
                    ann_text = '；'.join(recent) if recent else '[无新闻]'
            except Exception:
                ann_text = '[数据缺失]'
        info['公告'] = ann_text

        # 3. AI行业新闻（只在最后一条单独处理）
        data['stocks'][name] = info

    # 4. AI/科技行业重大新闻（取一条）
    try:
        df = ak.stock_info_global_cls()
        if not df.empty:
            ai_kws = ['AI', '人工智能', '大模型', 'GPT', 'Gemini', '芯片', '英伟达',
                      'OpenAI', 'DeepSeek', '算力']
            ai_news = []
            for _, row in df.iterrows():
                text = str(row.get('标题', '') or '') + str(row.get('内容', '') or '')
                if any(k in text for k in ai_kws):
                    ai_news.append(text[:100])
                    if len(ai_news) >= 1:
                        break
            data['AI行业动态'] = ai_news[0] if ai_news else '[今日暂无AI重大新闻]'
        else:
            data['AI行业动态'] = '[数据缺失]'
    except Exception:
        data['AI行业动态'] = '[数据缺失]'

    data['生成时间'] = datetime.now().strftime('%Y-%m-%d %H:%M')
    return data


# ── 4. 每日复盘 数据 ──────────────────────────────────────────────────────────

def fetch_review() -> dict:
    """
    返回复盘报告所需数据。
    在 16:25 左右调用，A股已收盘。
    """
    data = {}
    today_str = datetime.now().strftime('%Y%m%d')

    # A股主要指数
    index_map = {
        '上证指数': '000001.SH',
        '深成指': '399001.SZ',
        '创业板': '399006.SZ',
    }
    for name, code in index_map.items():
        try:
            df = _pro.index_daily(ts_code=code, start_date=today_str, end_date=today_str)
            if df is not None and not df.empty:
                row = df.iloc[0]
                pct  = round(float(row['pct_chg']), 2)
                cls  = round(float(row['close']), 2)
                vol  = round(float(row['amount']) / 1e8, 2)  # 亿元
                sign = '+' if pct >= 0 else ''
                data[name] = f"{cls}  {sign}{pct}%  成交{vol}亿"
            else:
                data[name] = '[数据缺失]'
        except Exception as e:
            data[name] = '[数据缺失]'

    # 港股指数（tushare index_global，HKTECH=恒生科技）
    for code, name in [('HSI', '恒生指数'), ('HKTECH', '恒生科技')]:
        try:
            end_d = datetime.now().strftime('%Y%m%d')
            start_d = (datetime.now() - timedelta(days=5)).strftime('%Y%m%d')
            df_hk = _pro.index_global(ts_code=code, start_date=start_d, end_date=end_d)
            if df_hk is not None and not df_hk.empty:
                row = df_hk.iloc[0]
                pct  = round(float(row['pct_chg']), 2)
                cls  = round(float(row['close']), 2)
                sign = '+' if pct >= 0 else ''
                data[name] = f"{cls}  {sign}{pct}%"
            else:
                data[name] = '[数据缺失]'
        except Exception:
            data[name] = '[数据缺失]'

    # 北向资金（当日数据有时延迟，回退到最近可用交易日）
    try:
        mf = None
        for days_back in range(0, 4):
            check_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y%m%d')
            df_mf = _pro.moneyflow_hsgt(trade_date=check_date)
            if df_mf is not None and not df_mf.empty:
                mf = df_mf
                break
        if mf is not None:
            row   = mf.iloc[0]
            north = round(float(row['north_money']) / 1e4, 2)  # 万元→亿元
            south = round(float(row['south_money']) / 1e4, 2)
            n_sign = '+' if north >= 0 else ''
            s_sign = '+' if south >= 0 else ''
            data['北向资金'] = f"{n_sign}{north}亿元（南向{s_sign}{south}亿元）"
        else:
            data['北向资金'] = '[数据缺失]'
    except Exception as e:
        data['北向资金'] = '[数据缺失]'

    # 申万一级行业涨跌（前3涨/前3跌）
    try:
        df = ak.stock_board_industry_name_em()
        if df is not None and not df.empty:
            pct_col = '涨跌幅' if '涨跌幅' in df.columns else df.columns[2]
            name_col = '板块名称' if '板块名称' in df.columns else df.columns[0]
            df[pct_col] = df[pct_col].astype(float)
            top3    = df.nlargest(3, pct_col)[[name_col, pct_col]]
            bot3    = df.nsmallest(3, pct_col)[[name_col, pct_col]]
            tops = '  '.join(f"{r[name_col]}({r[pct_col]:+.2f}%)" for _, r in top3.iterrows())
            bots = '  '.join(f"{r[name_col]}({r[pct_col]:+.2f}%)" for _, r in bot3.iterrows())
            data['领涨板块'] = tops
            data['领跌板块'] = bots
        else:
            data['领涨板块'] = '[数据缺失]'
            data['领跌板块'] = '[数据缺失]'
    except Exception as e:
        data['领涨板块'] = '[数据缺失]'
        data['领跌板块'] = '[数据缺失]'

    # 财联社当日快讯（复盘参考）
    try:
        df = ak.stock_info_global_cls()
        if not df.empty:
            lines = []
            for _, row in df.head(6).iterrows():
                t = str(row.get('发布时间', ''))[:5]
                title = str(row.get('标题', '') or row.get('内容', ''))[:80]
                lines.append(f"[{t}] {title}")
            data['今日财联社'] = '\n'.join(lines)
        else:
            data['今日财联社'] = '[数据缺失]'
    except Exception:
        data['今日财联社'] = '[数据缺失]'

    data['生成时间'] = datetime.now().strftime('%Y-%m-%d %H:%M')
    return data


# ── 5. 午间复盘 数据（12:30 调用）────────────────────────────────────────────

def fetch_midday_review() -> dict:
    """
    午间复盘：A股上午板块涨跌 + 港股指数 + 3条最重大财经新闻。
    """
    data = {}

    # A股板块（实时，取前3涨/前3跌）
    try:
        df = ak.stock_board_industry_name_em()
        if df is not None and not df.empty:
            pct_col  = '涨跌幅'  if '涨跌幅'  in df.columns else df.columns[2]
            name_col = '板块名称' if '板块名称' in df.columns else df.columns[0]
            df[pct_col] = df[pct_col].astype(float)
            top3 = df.nlargest(3, pct_col)[[name_col, pct_col]]
            bot3 = df.nsmallest(3, pct_col)[[name_col, pct_col]]
            data['A股领涨板块'] = '  '.join(
                f"{r[name_col]}({r[pct_col]:+.2f}%)" for _, r in top3.iterrows())
            data['A股领跌板块'] = '  '.join(
                f"{r[name_col]}({r[pct_col]:+.2f}%)" for _, r in bot3.iterrows())
        else:
            data['A股领涨板块'] = '[数据缺失]'
            data['A股领跌板块'] = '[数据缺失]'
    except Exception:
        data['A股领涨板块'] = '[数据缺失]'
        data['A股领跌板块'] = '[数据缺失]'

    # 港股指数（tushare index_global）
    for code, name in [('HSI', '恒生指数'), ('HKTECH', '恒生科技')]:
        try:
            end_d   = datetime.now().strftime('%Y%m%d')
            start_d = (datetime.now() - timedelta(days=5)).strftime('%Y%m%d')
            df_hk   = _pro.index_global(ts_code=code, start_date=start_d, end_date=end_d)
            if df_hk is not None and not df_hk.empty:
                row  = df_hk.iloc[0]
                pct  = round(float(row['pct_chg']), 2)
                cls  = round(float(row['close']), 2)
                sign = '+' if pct >= 0 else ''
                data[name] = f"{cls}  {sign}{pct}%"
            else:
                data[name] = '[数据缺失]'
        except Exception:
            data[name] = '[数据缺失]'

    # 午间重大财经新闻（Investing.com，过去12小时）
    data['重大财经新闻'] = _fetch_investing_news(n=5, hours_back=12)

    # 财联社快讯（最新6条，供补充）
    try:
        df = ak.stock_info_global_cls()
        if not df.empty:
            lines = []
            for _, row in df.head(6).iterrows():
                t     = str(row.get('发布时间', ''))[:5]
                title = str(row.get('标题', '') or row.get('内容', ''))[:80]
                lines.append(f"[{t}] {title}")
            data['财联社快讯'] = '\n'.join(lines)
        else:
            data['财联社快讯'] = '[数据缺失]'
    except Exception:
        data['财联社快讯'] = '[数据缺失]'

    data['生成时间'] = datetime.now().strftime('%Y-%m-%d %H:%M')
    return data


# ── 6. 周末汇总 数据（周日 19:00 调用）────────────────────────────────────────

def fetch_weekend_summary() -> dict:
    """
    周日晚间汇总：自选股（周五收盘）+ 周末重大国内外新闻 + AI产业动态。
    """
    data = {'stocks': {}}

    # 自选股（yfinance，取最近收盘）
    for name, ticker in WATCHLIST.items():
        pd = _yf_price(ticker)
        data['stocks'][name] = {
            'ticker': ticker,
            '价格':   _fmt_price(pd),
        }

    # 周末重大财经新闻（Investing.com，过去56小时覆盖周六+周日）
    data['周末国际要闻'] = _fetch_investing_news(n=6, hours_back=56)

    # 财联社周末快讯
    try:
        df = ak.stock_info_global_cls()
        if not df.empty:
            lines = []
            for _, row in df.head(8).iterrows():
                t     = str(row.get('发布时间', ''))[:5]
                title = str(row.get('标题', '') or row.get('内容', ''))[:80]
                lines.append(f"[{t}] {title}")
            data['财联社周末快讯'] = '\n'.join(lines)
        else:
            data['财联社周末快讯'] = '[数据缺失]'
    except Exception:
        data['财联社周末快讯'] = '[数据缺失]'

    # AI/科技行业重大新闻（从财联社关键词过滤）
    try:
        df = ak.stock_info_global_cls()
        if not df.empty:
            ai_kws = ['AI', '人工智能', '大模型', 'GPT', 'Gemini', '芯片', '英伟达',
                      'OpenAI', 'DeepSeek', '算力', 'Claude', 'Anthropic', '机器人']
            ai_news = []
            for _, row in df.iterrows():
                text = str(row.get('标题', '') or '') + str(row.get('内容', '') or '')
                if any(k in text for k in ai_kws):
                    ai_news.append(text[:100])
                if len(ai_news) >= 3:
                    break
            data['AI产业动态'] = '\n'.join(ai_news) if ai_news else '[本周末暂无AI重大新闻]'
        else:
            data['AI产业动态'] = '[数据缺失]'
    except Exception:
        data['AI产业动态'] = '[数据缺失]'

    data['生成时间'] = datetime.now().strftime('%Y-%m-%d %H:%M')
    return data
