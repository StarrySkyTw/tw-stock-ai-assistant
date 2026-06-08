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


def _trend(short: float, medium: float) -> str:
    if short > 0 and medium > 0:
        return "accumulating"
    if short < 0 and medium < 0:
        return "distributing"
    return "mixed"


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

