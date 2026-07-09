from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from app.services.calendar import taipei_today
from app.services.source_quality import is_trusted_source


@dataclass(frozen=True)
class CatalystEvent:
    date: date
    label: str
    source: str
    symbols: tuple[str, ...] = ()


CATALYSTS: tuple[CatalystEvent, ...] = (
    CatalystEvent(
        date=date(2026, 7, 14),
        label="美國 June 2026 CPI 公布",
        source="BLS official schedule",
    ),
    CatalystEvent(
        date=date(2026, 7, 16),
        label="台積電 2Q'26 法說會",
        source="TSMC investor calendar",
        symbols=("2330", "TSM", "TAIEX"),
    ),
)


def build_market_context(analysis: dict[str, Any], symbol: str, today: date | None = None) -> dict[str, Any]:
    current_date = today or taipei_today()
    upcoming = _upcoming_catalysts(symbol, current_date)
    signals = [
        _catalyst_signal(upcoming),
        _chip_signal(analysis),
        _discipline_signal(analysis),
    ]
    event_window = bool(upcoming)
    chip_wash = any(signal["kind"] == "chip_context" and signal["tone"] == "neutral" for signal in signals)
    no_confirmed_bullish = _no_confirmed_bullish(analysis)

    return {
        "event_window": event_window,
        "chip_wash": chip_wash,
        "no_confirmed_bullish": no_confirmed_bullish,
        "catalysts": [
            {
                "date": item.date.isoformat(),
                "label": item.label,
                "source": item.source,
            }
            for item in upcoming
        ],
        "signals": signals,
        "review_triggers": _review_triggers(upcoming),
        "data_quality": _data_quality(upcoming),
    }


def _upcoming_catalysts(symbol: str, today: date) -> list[CatalystEvent]:
    normalized = symbol.upper()
    result: list[CatalystEvent] = []
    for event in CATALYSTS:
        days_until = (event.date - today).days
        if days_until < 0 or days_until > 10:
            continue
        if event.symbols and normalized not in event.symbols and normalized != "2330":
            continue
        result.append(event)
    return result


def _catalyst_signal(upcoming: list[CatalystEvent]) -> dict[str, Any]:
    if not upcoming:
        return _signal(
            "catalyst",
            "事件催化",
            "未偵測到 10 天內的內建重大催化；仍需留意公司公告、月營收與總經事件。",
            "neutral",
            1,
        )
    event_text = "、".join(f"{item.date.strftime('%m/%d')} {item.label}" for item in upcoming[:3])
    return _signal(
        "catalyst",
        "事件催化",
        f"{event_text} 前，震盪先視為事件前籌碼整理；沒有實質利多前不追價，等公告後再重判斷。",
        "neutral",
        1,
    )


def _chip_signal(analysis: dict[str, Any]) -> dict[str, Any]:
    margin = analysis.get("margin", {})
    institutional = analysis.get("institutional", {})
    technical = analysis.get("technical", {})
    latest_close = _float_or_none(technical.get("latest_close"))
    ma = technical.get("ma", {})
    ma20 = _float_or_none(ma.get("ma20"))
    ma60 = _float_or_none(ma.get("ma60"))
    margin_5d = _float_or_none(margin.get("five_day_change"))
    margin_20d = _float_or_none(margin.get("twenty_day_change"))
    inst_5d = _float_or_none(institutional.get("five_day_total"))
    inst_20d = _float_or_none(institutional.get("twenty_day_total"))
    volume_ratio = _float_or_none(technical.get("volume_ratio"))

    above_key_support = latest_close is not None and (
        (ma20 is not None and latest_close >= ma20) or (ma60 is not None and latest_close >= ma60)
    )
    financing_cleaning = margin_5d is not None and margin_5d < 0 and (margin_20d is None or margin_20d >= 0)
    institutional_mixed = (inst_5d is not None and inst_5d < 0) or (inst_20d is not None and inst_20d < 0)

    if financing_cleaning and above_key_support:
        return _signal(
            "chip_context",
            "籌碼情境",
            "融資短線下降但價格仍守關鍵支撐，較像籌碼清洗；等法人賣壓收斂或量縮止跌，不把震盪直接視為利空。",
            "neutral",
            1,
        )
    if institutional_mixed and margin_20d is not None and margin_20d > 0:
        return _signal(
            "chip_context",
            "籌碼情境",
            "法人偏賣且融資仍增加，籌碼沒有洗乾淨，反彈先當降低風險或等待確認。",
            "risk",
            1,
        )
    if volume_ratio is not None and volume_ratio >= 1.8 and latest_close is not None and ma20 is not None and latest_close > ma20:
        return _signal(
            "chip_context",
            "籌碼情境",
            "爆量站高容易變成追價區，先等回測支撐與量縮確認。",
            "risk",
            1,
        )
    return _signal(
        "chip_context",
        "籌碼情境",
        "籌碼訊號未明確轉強或轉弱，先用支撐、法人與融資變化確認，不用單日波動下結論。",
        "neutral",
        1,
    )


def _discipline_signal(analysis: dict[str, Any]) -> dict[str, Any]:
    valuation = analysis.get("valuation_gate", {})
    fundamental = analysis.get("fundamental_gate", {})
    timing = analysis.get("timing_gate", {})
    decision = analysis.get("research_decision", {})
    data_sources = analysis.get("data_sources", {})

    valuation_status = str(valuation.get("status") or "unknown")
    fundamental_status = str(fundamental.get("status") or "unknown")
    timing_status = str(timing.get("status") or "unknown")
    has_trusted_fundamental = is_trusted_source(data_sources.get("fundamental"), "fundamental")
    no_chase = bool(decision.get("do_not_chase_reason"))

    if not has_trusted_fundamental:
        return _signal(
            "discipline",
            "投資紀律",
            "基本面來源不足時，先保留現金與觀察，不用便宜或成長故事說服自己加碼。",
            "neutral",
            1,
        )
    if valuation_status in {"watch", "fail"} or no_chase:
        return _signal(
            "discipline",
            "投資紀律",
            "好公司也要有安全邊際；估值不便宜或禁追條件存在時，只能續抱或等待，不做追價加碼。",
            "risk",
            1,
        )
    if fundamental_status == "pass" and timing_status == "pass":
        return _signal(
            "discipline",
            "投資紀律",
            "基本面與時機同時過關才允許小幅分批；仍要先設定失效價，錯了就承認。",
            "positive",
            1,
        )
    return _signal(
        "discipline",
        "投資紀律",
        "沒有明確優勢時，等待本身就是決策；先看風險報酬與失效條件，不為了交易而交易。",
        "neutral",
        1,
    )


def _no_confirmed_bullish(analysis: dict[str, Any]) -> bool:
    sentiment = analysis.get("sentiment", {})
    sentiment_label = str(sentiment.get("label") or "neutral")
    sentiment_error = str(sentiment.get("error") or "")
    revenue_yoy = _float_or_none(analysis.get("fundamental_gate", {}).get("metrics", {}).get("revenue_yoy"))
    no_positive_news = sentiment_label != "positive" or sentiment_error == "no_news"
    no_strong_revenue = revenue_yoy is None or revenue_yoy < 10
    return no_positive_news and no_strong_revenue


def _review_triggers(upcoming: list[CatalystEvent]) -> list[str]:
    triggers = [f"{item.date.strftime('%m/%d')} {item.label} 後重新判斷，不沿用事件前結論。" for item in upcoming]
    triggers.extend(
        [
            "事件前若只是震盪且未跌破失效價，先檢查籌碼是否清洗，不急著放大部位。",
            "事件後若營收/法說/通膨方向不如預期，再把續抱改為減碼檢查。",
        ]
    )
    return triggers[:5]


def _data_quality(upcoming: list[CatalystEvent]) -> list[str]:
    if not upcoming:
        return ["催化事件層目前只使用內建公開行事曆；未列入事件仍需人工留意。"]
    sources = sorted({item.source for item in upcoming})
    return [f"催化事件來源：{', '.join(sources)}。日期需以官方更新為準。"]


def _signal(kind: str, label: str, detail: str, tone: str, priority: int) -> dict[str, Any]:
    return {"kind": kind, "label": label, "detail": detail, "tone": tone, "priority": priority}


def _float_or_none(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
