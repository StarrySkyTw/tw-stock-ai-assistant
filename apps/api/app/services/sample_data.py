from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd

from app.services.calendar import taipei_now, taipei_today

STOCK_NAMES = {
    "0050": "元大台灣50",
    "0056": "元大高股息",
    "00878": "國泰永續高股息",
    "2330": "台積電",
    "2317": "鴻海",
    "2454": "聯發科",
    "2308": "台達電",
    "2382": "廣達",
    "2412": "中華電",
    "3711": "日月光投控",
    "2603": "長榮",
    "2609": "陽明",
    "2615": "萬海",
    "2881": "富邦金",
    "2882": "國泰金",
    "2891": "中信金",
    "3008": "大立光",
    "3034": "聯詠",
    "3443": "創意",
    "3661": "世芯-KY",
    "2357": "華碩",
    "2379": "瑞昱",
    "3231": "緯創",
    "5871": "中租-KY",
    "1216": "統一",
    "1303": "南亞",
    "2002": "中鋼",
    "1101": "台泥",
}


def _seed(symbol: str) -> int:
    return sum(ord(ch) for ch in symbol) % 10000


def stock_name(symbol: str) -> str | None:
    return STOCK_NAMES.get(symbol.upper())


def make_price_history(symbol: str, years: int = 2) -> pd.DataFrame:
    rng = np.random.default_rng(_seed(symbol))
    periods = max(260 * years, 260)
    dates = pd.bdate_range(end=taipei_today(), periods=periods)
    drift = 0.00045 if symbol in {"2330", "2454", "2317"} else 0.0002
    volatility = 0.018 + (_seed(symbol) % 9) / 1000
    returns = rng.normal(drift, volatility, len(dates))
    base_price = 80 + (_seed(symbol) % 900)
    close = base_price * np.exp(np.cumsum(returns))
    open_ = close * (1 + rng.normal(0, 0.004, len(dates)))
    high = np.maximum(open_, close) * (1 + rng.uniform(0.001, 0.018, len(dates)))
    low = np.minimum(open_, close) * (1 - rng.uniform(0.001, 0.018, len(dates)))
    volume_base = 8_000_000 + (_seed(symbol) % 30) * 600_000
    volume = rng.lognormal(np.log(volume_base), 0.28, len(dates))
    if len(dates) > 30:
        volume[-3:] *= 1.7
        close[-10:] *= np.linspace(1.0, 1.08, 10)

    return pd.DataFrame(
        {
            "date": dates.date,
            "open": np.round(open_, 2),
            "high": np.round(high, 2),
            "low": np.round(low, 2),
            "close": np.round(close, 2),
            "volume": np.round(volume, 0),
        }
    )


def make_institutional_flows(symbol: str, days: int = 80) -> pd.DataFrame:
    rng = np.random.default_rng(_seed(symbol) + 41)
    dates = pd.bdate_range(end=taipei_today(), periods=days)
    bias = 350 if symbol in {"2330", "2454", "2317"} else 80
    foreign = rng.normal(bias, 900, len(dates)).round(0)
    trust = rng.normal(bias / 4, 300, len(dates)).round(0)
    dealer = rng.normal(0, 260, len(dates)).round(0)
    if len(dates) > 10:
        foreign[-5:] += 900
        trust[-5:] += 250
    total = foreign + trust + dealer
    return pd.DataFrame(
        {
            "date": dates.date,
            "foreign_net": foreign,
            "investment_trust_net": trust,
            "dealer_net": dealer,
            "total_net": total,
        }
    )


def make_fundamental(symbol: str) -> dict[str, float | None]:
    base = _seed(symbol)
    return {
        "eps": round(2.5 + (base % 90) / 10, 2),
        "roe": round(8 + (base % 220) / 10, 2),
        "gross_margin": round(22 + (base % 420) / 10, 2),
        "operating_margin": round(8 + (base % 280) / 10, 2),
        "pe_ratio": round(10 + (base % 260) / 10, 2),
        "pb_ratio": round(1 + (base % 70) / 10, 2),
        "revenue_yoy": round(-5 + (base % 360) / 10, 2),
        "revenue_mom": round(-8 + (base % 220) / 10, 2),
    }


def make_margin(symbol: str, days: int = 80) -> pd.DataFrame:
    rng = np.random.default_rng(_seed(symbol) + 88)
    dates = pd.bdate_range(end=taipei_today(), periods=days)
    margin = rng.normal(20000, 1800, len(dates)).clip(1000)
    short = rng.normal(900, 160, len(dates)).clip(0)
    ratio = np.where(margin == 0, 0, short / margin * 100)
    return pd.DataFrame(
        {
            "date": dates.date,
            "margin_purchase_balance": margin.round(0),
            "short_sale_balance": short.round(0),
            "short_margin_ratio": ratio.round(2),
        }
    )


def make_shareholding(symbol: str) -> dict[str, float | int | None]:
    base = _seed(symbol)
    return {
        "large_holder_ratio": round(42 + (base % 420) / 10, 2),
        "shareholder_count": 30000 + base * 3,
    }


def make_news(symbol: str) -> list[dict[str, str]]:
    today = taipei_now()
    return [
        {
            "published_at": (today - timedelta(days=1)).isoformat(),
            "title": f"{symbol} 法說會聚焦營收與毛利率展望",
            "source": "sample",
            "url": "",
        },
        {
            "published_at": (today - timedelta(days=2)).isoformat(),
            "title": f"{symbol} 外資連續買超，市場關注 AI 與高階製程需求",
            "source": "sample",
            "url": "",
        },
    ]
