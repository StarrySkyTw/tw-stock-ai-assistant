from __future__ import annotations

import pandas as pd


def recommendation_from_score(score: float) -> str:
    if score >= 90:
        return "強力買進"
    if score >= 75:
        return "買進"
    if score >= 60:
        return "觀察"
    if score >= 40:
        return "減碼"
    return "賣出"


def score_technical(summary: dict) -> tuple[float, list[str], list[str]]:
    score = 20.0
    reasons: list[str] = []
    risks: list[str] = []
    trend = summary["trend"]
    rsi14 = summary["rsi"].get("rsi14")
    osc = summary["macd"].get("osc")
    volume_ratio = summary.get("volume_ratio")
    signals = summary.get("signals", [])

    if trend == "bullish":
        score += 8
        reasons.append("均線呈多頭排列，波段趨勢偏多。")
    elif trend == "bearish":
        score -= 8
        risks.append("均線呈空頭排列，趨勢尚未轉強。")

    if rsi14 is not None:
        if 45 <= rsi14 <= 65:
            score += 4
            reasons.append("RSI14 位於健康區間，沒有明顯過熱。")
        elif rsi14 > 75:
            score -= 5
            risks.append("RSI14 過熱，追價風險提高。")
        elif rsi14 < 30:
            score -= 2
            risks.append("RSI14 超賣，需等待止跌確認。")

    if osc is not None:
        if osc > 0:
            score += 4
            reasons.append("MACD OSC 為正，動能偏強。")
        else:
            score -= 4
            risks.append("MACD OSC 為負，短線動能偏弱。")

    if "KD 黃金交叉" in signals:
        score += 3
        reasons.append("KD 黃金交叉，短線轉強。")
    if "KD 死亡交叉" in signals:
        score -= 3
        risks.append("KD 死亡交叉，短線轉弱。")
    if "成交量放大" in signals:
        score += 2
        reasons.append("成交量放大，買盤參與度提高。")
    if volume_ratio and volume_ratio > 2.5:
        risks.append("爆量後波動容易放大，需搭配停損。")

    return max(0, min(40, score)), reasons, risks


def summarize_institutional(flows: pd.DataFrame) -> dict:
    flows = flows.sort_values("date")
    windows = {5: flows.tail(5), 20: flows.tail(20), 60: flows.tail(60)}

    def total(window: int, column: str = "total_net") -> float:
        return float(windows[window][column].sum()) if not windows[window].empty else 0.0

    signals: list[str] = []
    if total(5) > 0 and total(20) > 0:
        signals.append("三大法人短中期同步買超")
    if total(5) < 0 and total(20) < 0:
        signals.append("三大法人短中期同步賣超")
    if len(flows) >= 5 and (flows.tail(5)["foreign_net"] > 0).all():
        signals.append("外資連續 5 日買超")

    return {
        "five_day_total": total(5),
        "twenty_day_total": total(20),
        "sixty_day_total": total(60),
        "foreign_trend": _trend(total(5, "foreign_net"), total(20, "foreign_net")),
        "investment_trust_trend": _trend(
            total(5, "investment_trust_net"), total(20, "investment_trust_net")
        ),
        "dealer_trend": _trend(total(5, "dealer_net"), total(20, "dealer_net")),
        "signals": signals,
    }


def summarize_margin(margin: pd.DataFrame) -> dict:
    margin = margin.sort_values("date")
    latest = margin.tail(1)

    if latest.empty:
        return {
            "latest_balance": None,
            "five_day_change": 0.0,
            "five_day_change_pct": None,
            "twenty_day_change": 0.0,
            "twenty_day_change_pct": None,
            "short_margin_ratio": None,
            "status": "unknown",
            "signals": ["融資資料不足，籌碼乾淨度需要用法人與技術面交叉確認。"],
        }

    latest_row = latest.iloc[-1]
    latest_balance = _to_float(latest_row.get("margin_purchase_balance"))
    short_margin_ratio = _to_float(latest_row.get("short_margin_ratio"))
    five_day_change, five_day_pct = _balance_change(margin, latest_balance, 6)
    twenty_day_change, twenty_day_pct = _balance_change(margin, latest_balance, 21)

    signals: list[str] = []
    if five_day_change < 0:
        signals.append(f"近 5 日融資減少 {abs(five_day_change):,.0f}，短線浮額有下降。")
    elif five_day_change > 0:
        signals.append(f"近 5 日融資增加 {five_day_change:,.0f}，追價籌碼仍需留意。")

    if twenty_day_change < 0:
        signals.append(f"近 20 日融資減少 {abs(twenty_day_change):,.0f}，籌碼有整理跡象。")
    elif twenty_day_change > 0:
        signals.append(f"近 20 日融資增加 {twenty_day_change:,.0f}，籌碼尚未完全沉澱。")

    if short_margin_ratio is not None:
        if short_margin_ratio <= 5:
            signals.append(f"券資比 {short_margin_ratio:.1f}% 偏低，融券壓力不高。")
        elif short_margin_ratio >= 15:
            signals.append(f"券資比 {short_margin_ratio:.1f}% 偏高，籌碼波動風險較高。")

    if not signals:
        signals.append("融資變化中性，暫無明顯籌碼轉乾淨或過熱訊號。")

    status = "neutral"
    if five_day_change < 0 and twenty_day_change < 0:
        status = "cleaning"
    elif five_day_change > 0 and twenty_day_change > 0:
        status = "crowded"
    elif five_day_change < 0:
        status = "improving"

    return {
        "latest_balance": latest_balance,
        "five_day_change": round(five_day_change, 2),
        "five_day_change_pct": five_day_pct,
        "twenty_day_change": round(twenty_day_change, 2),
        "twenty_day_change_pct": twenty_day_pct,
        "short_margin_ratio": short_margin_ratio,
        "status": status,
        "signals": signals,
    }


def score_margin(summary: dict) -> tuple[float, list[str], list[str]]:
    adjustment = 0.0
    reasons: list[str] = []
    risks: list[str] = []
    five_day_change = summary.get("five_day_change", 0) or 0
    twenty_day_change = summary.get("twenty_day_change", 0) or 0
    short_margin_ratio = summary.get("short_margin_ratio")

    if five_day_change < 0:
        adjustment += 2
        reasons.append("近 5 日融資餘額下降，短線籌碼比較乾淨。")
    elif five_day_change > 0:
        adjustment -= 2
        risks.append("近 5 日融資餘額增加，追價籌碼還沒完全洗掉。")

    if twenty_day_change < 0:
        adjustment += 3
        reasons.append("近 20 日融資同步下降，籌碼沉澱加分。")
    elif twenty_day_change > 0:
        adjustment -= 3
        risks.append("近 20 日融資仍增加，進場前要等籌碼更乾淨。")

    if short_margin_ratio is not None and short_margin_ratio >= 15:
        adjustment -= 1
        risks.append("券資比偏高，籌碼波動可能放大。")

    return max(-6, min(6, adjustment)), reasons, risks


def _trend(short: float, medium: float) -> str:
    if short > 0 and medium > 0:
        return "accumulating"
    if short < 0 and medium < 0:
        return "distributing"
    return "mixed"


def _balance_change(
    margin: pd.DataFrame,
    latest_balance: float | None,
    lookback_rows: int,
) -> tuple[float, float | None]:
    if latest_balance is None or len(margin) < 2:
        return 0.0, None
    base_index = max(0, len(margin) - lookback_rows)
    base_balance = _to_float(margin.iloc[base_index].get("margin_purchase_balance"))
    if base_balance is None:
        return 0.0, None
    change = latest_balance - base_balance
    change_pct = round(change / base_balance * 100, 2) if base_balance else None
    return change, change_pct


def _to_float(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def score_institutional(summary: dict, large_holder_ratio: float | None = None) -> tuple[float, list[str], list[str]]:
    score = 12.5
    reasons: list[str] = []
    risks: list[str] = []
    if summary["five_day_total"] > 0:
        score += 4
        reasons.append("近 5 日法人合計買超。")
    else:
        score -= 4
        risks.append("近 5 日法人合計偏賣超。")
    if summary["twenty_day_total"] > 0:
        score += 5
        reasons.append("近 20 日法人籌碼偏多。")
    else:
        score -= 5
        risks.append("近 20 日法人籌碼偏空。")
    if summary["sixty_day_total"] > 0:
        score += 2.5
    if large_holder_ratio is not None and large_holder_ratio >= 55:
        score += 3
        reasons.append("大戶持股比例偏高，籌碼集中度佳。")
    elif large_holder_ratio is not None and large_holder_ratio < 35:
        score -= 3
        risks.append("大戶持股比例偏低，籌碼穩定度不足。")
    return max(0, min(25, score)), reasons, risks


def score_fundamental(fundamental: dict) -> tuple[float, list[str], list[str]]:
    score = 12.5
    reasons: list[str] = []
    risks: list[str] = []
    eps = fundamental.get("eps")
    roe = fundamental.get("roe")
    revenue_yoy = fundamental.get("revenue_yoy")
    gross_margin = fundamental.get("gross_margin")
    pe_ratio = fundamental.get("pe_ratio")

    if eps is not None and eps > 0:
        score += 4
        reasons.append("EPS 為正，具獲利基礎。")
    else:
        score -= 5
        risks.append("EPS 不佳，獲利品質需留意。")
    if roe is not None and roe >= 15:
        score += 5
        reasons.append("ROE 高於 15%，資本效率佳。")
    elif roe is not None and roe < 8:
        score -= 4
        risks.append("ROE 偏低。")
    if revenue_yoy is not None and revenue_yoy >= 10:
        score += 4
        reasons.append("營收年增率高於 10%，成長性佳。")
    elif revenue_yoy is not None and revenue_yoy < 0:
        score -= 4
        risks.append("營收年增率衰退。")
    if gross_margin is not None and gross_margin >= 35:
        score += 2
    if pe_ratio is not None and pe_ratio > 35:
        risks.append("本益比偏高，評價面需保守。")
        score -= 2
    return max(0, min(25, score)), reasons, risks


def score_sentiment(sentiment: dict) -> tuple[float, list[str], list[str]]:
    value = sentiment.get("score", 0)
    score = max(0, min(10, 5 + value * 5))
    if score >= 7:
        return score, ["新聞與重大資訊情緒偏正向。"], []
    if score <= 3:
        return score, [], ["新聞與重大資訊情緒偏負向。"]
    return score, ["新聞情緒中性。"], []
