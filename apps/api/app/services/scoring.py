from __future__ import annotations

from typing import Any

import pandas as pd

from app.services.source_quality import is_trusted_source

ETF_SYMBOL_PREFIXES = ("00",)
TECH_SYMBOLS = {
    "2330",
    "2317",
    "2454",
    "2308",
    "2382",
    "3711",
    "3008",
    "3034",
    "3443",
    "3661",
    "2357",
    "2379",
    "3231",
}
FINANCIAL_SYMBOL_PREFIXES = ("28",)
FINANCIAL_SYMBOLS = {"5871"}


def recommendation_from_score(score: float) -> str:
    if score >= 90:
        return "優先研究"
    if score >= 75:
        return "可研究"
    if score >= 60:
        return "觀察"
    if score >= 40:
        return "降低風險"
    return "暫避"


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


def evaluate_fundamental_gate(fundamental: dict[str, Any]) -> dict[str, Any]:
    eps = _to_float(fundamental.get("eps"))
    roe = _to_float(fundamental.get("roe"))
    revenue_yoy = _to_float(fundamental.get("revenue_yoy"))
    revenue_mom = _to_float(fundamental.get("revenue_mom"))
    gross_margin = _to_float(fundamental.get("gross_margin"))
    operating_margin = _to_float(fundamental.get("operating_margin"))
    pe_ratio = _to_float(fundamental.get("pe_ratio"))
    pb_ratio = _to_float(fundamental.get("pb_ratio"))

    score = 0.0
    failed: list[str] = []

    if eps is not None and eps > 0:
        score += 3
    else:
        failed.append("EPS 必須為正，否則低本益比也可能是獲利衰退陷阱。")

    if roe is None:
        failed.append("ROE 資料不足，無法確認資本效率。")
    elif roe >= 15:
        score += 3
    elif roe >= 8:
        score += 1.5
    else:
        failed.append(f"ROE {roe:.1f}% 偏低，基本面品質未達中長期研究門檻。")

    if revenue_yoy is None:
        failed.append("營收年增資料不足，無法確認成長或防守能力。")
    elif revenue_yoy >= 10:
        score += 2
    elif revenue_yoy >= 0:
        score += 1
    else:
        failed.append(f"營收年增 {revenue_yoy:.1f}% 為負，先等營收趨勢修復。")

    if revenue_mom is not None and revenue_mom >= 0:
        score += 0.75
    elif revenue_mom is not None and revenue_mom <= -10:
        failed.append(f"營收月減 {abs(revenue_mom):.1f}% 過大，需確認是否為短期或結構性衰退。")

    if gross_margin is not None and gross_margin >= 30:
        score += 0.75
    if operating_margin is not None and operating_margin >= 10:
        score += 0.75

    if score >= 8:
        grade = "A"
    elif score >= 6:
        grade = "B"
    elif score >= 4:
        grade = "C"
    else:
        grade = "D"

    passed = not failed and grade in {"A", "B"}
    if passed:
        status = "pass"
    elif grade == "C" and not any("EPS 必須" in item for item in failed):
        status = "watch"
    else:
        status = "fail"

    return {
        "status": status,
        "grade": grade,
        "passed": passed,
        "failed_reasons": failed,
        "metrics": {
            "eps": eps,
            "roe": roe,
            "gross_margin": gross_margin,
            "operating_margin": operating_margin,
            "revenue_yoy": revenue_yoy,
            "revenue_mom": revenue_mom,
            "pe_ratio": pe_ratio,
            "pb_ratio": pb_ratio,
        },
    }


def evaluate_valuation_gate(symbol: str, fundamental: dict[str, Any]) -> dict[str, Any]:
    symbol = symbol.upper().strip()
    pe_ratio = _to_float(fundamental.get("pe_ratio"))
    sector_band = _valuation_sector_band(symbol)

    if _is_etf(symbol):
        return {
            "status": "not_applicable",
            "pe_ratio": pe_ratio,
            "pe_band": "不適用",
            "sector_band": "ETF 不用單一公司本益比判斷",
            "is_low_valuation": False,
            "warning": "ETF 應改看折溢價、成分股品質、配息穩定度與大盤位置，不用單一 PE gate。",
        }

    if pe_ratio is None or pe_ratio <= 0:
        return {
            "status": "unknown",
            "pe_ratio": pe_ratio,
            "pe_band": "資料不足",
            "sector_band": sector_band["label"],
            "is_low_valuation": False,
            "warning": "本益比資料不足，不能把估值當成已通過。",
        }

    cheap = sector_band["cheap"]
    fair = sector_band["fair"]
    expensive = sector_band["expensive"]
    if pe_ratio <= cheap:
        status = "pass"
        pe_band = "便宜"
        warning = None
    elif pe_ratio <= fair:
        status = "pass"
        pe_band = "合理"
        warning = None
    elif pe_ratio <= expensive:
        status = "watch"
        pe_band = "偏貴"
        warning = f"本益比 {pe_ratio:.1f} 已偏貴，除非基本面成長明確，否則等便宜價。"
    else:
        status = "fail"
        pe_band = "避免追高"
        warning = f"本益比 {pe_ratio:.1f} 高於本策略上限，低價位條件不成立。"

    return {
        "status": status,
        "pe_ratio": pe_ratio,
        "pe_band": pe_band,
        "sector_band": sector_band["label"],
        "is_low_valuation": pe_ratio <= cheap,
        "warning": warning,
    }


def evaluate_timing_gate(technical: dict[str, Any]) -> dict[str, Any]:
    close = _to_float(technical.get("latest_close"))
    ma = technical.get("ma", {})
    ma20 = _to_float(ma.get("ma20"))
    ma60 = _to_float(ma.get("ma60"))
    ma120 = _to_float(ma.get("ma120"))
    ma240 = _to_float(ma.get("ma240"))
    atr14 = _to_float(technical.get("atr14"))
    rsi14 = _to_float(technical.get("rsi", {}).get("rsi14"))
    volume_ratio = _to_float(technical.get("volume_ratio"))

    long_line = ma240 or ma120 or ma60
    medium_line = ma120 or ma60 or ma20
    invalidation_candidates = [value for value in [ma120, ma240, ma60] if value is not None]
    invalidation_price = round(min(invalidation_candidates), 2) if invalidation_candidates else None

    too_far_from_ma20 = (
        close is not None
        and ma20 is not None
        and atr14 is not None
        and close > ma20 + 1.5 * atr14
    )
    rsi_overheated = bool(rsi14 is not None and rsi14 > 70)
    volume_chase = bool(volume_ratio is not None and volume_ratio >= 2.2 and close is not None and ma20 is not None and close > ma20)
    no_chase = too_far_from_ma20 or rsi_overheated or volume_chase

    below_medium = close is not None and medium_line is not None and close < medium_line
    below_long = close is not None and long_line is not None and close < long_line
    above_ma60 = close is not None and ma60 is not None and close >= ma60
    above_ma120 = close is not None and ma120 is not None and close >= ma120

    if below_long or below_medium:
        status = "fail"
        trend = "中長期趨勢未站穩"
    elif no_chase:
        status = "watch"
        trend = "趨勢偏多但短線過熱"
    elif above_ma60 and (above_ma120 or ma120 is None):
        status = "pass"
        trend = "中長期趨勢可觀察"
    else:
        status = "watch"
        trend = "訊號未完整"

    support_values = [value for value in [ma60, ma120, ma240] if value is not None]
    if support_values:
        support_zone = f"{min(support_values):.2f} - {max(support_values):.2f}"
    else:
        support_zone = "資料不足"

    chase_reasons: list[str] = []
    if too_far_from_ma20:
        chase_reasons.append("價格高於 MA20 超過 1.5 ATR")
    if rsi_overheated:
        chase_reasons.append(f"RSI14 {rsi14:.1f} 過熱")
    if volume_chase:
        chase_reasons.append(f"量比 {volume_ratio:.1f} 偏高且價格在 MA20 上方")
    no_chase_zone = "、".join(chase_reasons) if chase_reasons else "未觸發禁追條件"

    entry_conditions = [
        "基本面與估值先通過，再看 K 線時機。",
        "價格回測 MA60/MA120 支撐區後不跌破。",
        "RSI14 回到 45-65，且量能不是爆量追高。",
        "若突破後離 MA20 太遠，等回測，不追第一根急漲。",
    ]

    return {
        "status": status,
        "trend": trend,
        "support_zone": support_zone,
        "no_chase_zone": no_chase_zone,
        "entry_conditions": entry_conditions,
        "invalidation_price": invalidation_price,
    }


def build_price_plan(
    technical: dict[str, Any],
    timing_gate: dict[str, Any],
    valuation_gate: dict[str, Any],
) -> dict[str, Any]:
    close = _to_float(technical.get("latest_close"))
    ma = technical.get("ma", {})
    ma20 = _to_float(ma.get("ma20"))
    ma60 = _to_float(ma.get("ma60"))
    ma120 = _to_float(ma.get("ma120"))
    atr14 = _to_float(technical.get("atr14"))

    if timing_gate["status"] == "pass" and valuation_gate["status"] in {"pass", "not_applicable"}:
        research_price = close
        hint = "10-25%，先小部位研究，失效價先寫好。"
    elif timing_gate["status"] == "watch":
        research_price = ma60 or ma20
        hint = "0-10%，等回測或估值更便宜再考慮。"
    else:
        research_price = None
        hint = "0%，先不建立新研究部位。"

    watch_candidates = [value for value in [ma60, ma120, ma20] if value is not None]
    watch_price = min(watch_candidates) if watch_candidates else None
    invalidation_price = timing_gate.get("invalidation_price")
    if invalidation_price is None and close is not None and atr14 is not None:
        invalidation_price = round(close - 2 * atr14, 2)

    return {
        "research_price": round(research_price, 2) if research_price is not None else None,
        "watch_price": round(watch_price, 2) if watch_price is not None else None,
        "invalidation_price": invalidation_price,
        "position_size_hint": hint,
    }


def build_research_decision(
    *,
    fundamental_gate: dict[str, Any],
    valuation_gate: dict[str, Any],
    timing_gate: dict[str, Any],
    price_plan: dict[str, Any],
    risk_lights: dict[str, Any],
    data_sources: dict[str, str],
) -> dict[str, Any]:
    blockers: list[str] = []
    composite_light = risk_lights.get("composite", "yellow")
    price_source = data_sources.get("price", "").lower()
    untrusted_price = not price_source or "sample" in price_source

    if fundamental_gate["failed_reasons"]:
        blockers.extend(fundamental_gate["failed_reasons"][:3])
    if valuation_gate.get("warning"):
        blockers.append(str(valuation_gate["warning"]))
    if timing_gate["status"] == "fail":
        blockers.append("K 線中長期趨勢未站穩，先不要把下跌當成便宜。")
    if composite_light == "red":
        blockers.append("大盤綜合燈號為紅燈，先降低進場慾望。")
    if not is_trusted_source(data_sources.get("fundamental"), "fundamental"):
        blockers.append("基本面目前不是可驗證真實來源，不採用 EPS、PE、ROE 或營收做結論。")
    if untrusted_price:
        blockers.append("價格資料不是可驗證歷史日 K，不採用均線、支撐、壓力或失效價。")

    if composite_light == "red" or timing_gate["status"] == "fail":
        stance = "reduce_risk"
        summary = "先降低風險，等大盤或中長期均線修復。"
        next_action = "暫停新倉；若已持有，檢查失效價與部位大小。"
    elif not is_trusted_source(data_sources.get("fundamental"), "fundamental"):
        stance = "watch"
        summary = "基本面資料仍不是可驗證真實來源，只能當觀察流程，不能下研究結論。"
        next_action = "先補真實基本面資料；補齊前只檢查價位、K 線與資料來源。"
    elif untrusted_price:
        stance = "watch"
        summary = "價格資料仍是範例來源，不能用均線、支撐或失效價判斷時機。"
        next_action = "等真實日 K 或即時報價接上後，再重新判斷 K 線時機。"
    elif fundamental_gate["status"] == "fail":
        stance = "avoid"
        summary = "基本面沒有先過關，低本益比或漂亮 K 線都不能單獨說服進場。"
        next_action = "先移出優先研究清單，等 EPS、ROE 或營收改善後再看。"
    elif valuation_gate["status"] == "fail":
        stance = "wait_better_price"
        summary = "公司品質可研究，但目前本益比不符合低估或合理價。"
        next_action = "列入觀察，不追高；等 PE 回到合理帶或價格回測支撐。"
    elif timing_gate["status"] == "watch" or timing_gate["no_chase_zone"] != "未觸發禁追條件":
        stance = "watch"
        summary = "基本面與估值有研究價值，但 K 線時機還不夠乾淨。"
        next_action = "等回測支撐、量能冷卻或 RSI 降溫，再重新判斷。"
    elif fundamental_gate["passed"] and valuation_gate["status"] in {"pass", "not_applicable"}:
        stance = "worth_research"
        summary = "基本面先過濾、估值未明顯過熱，K 線時機可列入研究。"
        next_action = "只用小部位研究，先設定失效價，不把系統結論當下單指令。"
    else:
        stance = "watch"
        summary = "條件尚未完整，適合放進觀察清單而不是急著行動。"
        next_action = "等待基本面、估值與 K 線至少兩項同步改善。"

    fallback_count = sum(1 for key, source in data_sources.items() if not is_trusted_source(source, key))
    if fallback_count >= 2 or not is_trusted_source(data_sources.get("fundamental"), "fundamental"):
        confidence = "低"
    elif blockers:
        confidence = "中"
    else:
        confidence = "高"

    do_not_chase_reason = None
    if timing_gate["no_chase_zone"] != "未觸發禁追條件":
        do_not_chase_reason = f"禁止追高：{timing_gate['no_chase_zone']}。"
    elif valuation_gate["status"] in {"watch", "fail"}:
        do_not_chase_reason = "估值還沒便宜，不因短線上漲追價。"

    return {
        "stance": stance,
        "horizon": "3個月-2年",
        "confidence": confidence,
        "summary": summary,
        "next_action": next_action,
        "do_not_chase_reason": do_not_chase_reason,
        "blockers": blockers[:5],
        "review_triggers": [
            "下一次月營收公布後重新檢查基本面。",
            "價格回測支撐區或跌破失效價時重新判斷。",
            "本益比回到合理帶或財報公布後重估。",
            "大盤綜合燈號轉紅或轉綠時更新結論。",
            f"目前失效價參考：{price_plan.get('invalidation_price') or '資料不足'}。",
        ],
    }


def evaluate_breakout_potential(
    *,
    fundamental_gate: dict[str, Any],
    valuation_gate: dict[str, Any],
    timing_gate: dict[str, Any],
    price_plan: dict[str, Any],
    technical: dict[str, Any],
    institutional: dict[str, Any],
    margin: dict[str, Any],
    sentiment: dict[str, Any],
    risk_lights: dict[str, Any],
    data_sources: dict[str, str],
) -> dict[str, Any]:
    trusted_fundamental = is_trusted_source(data_sources.get("fundamental"), "fundamental")
    trusted_price = is_trusted_source(data_sources.get("price"), "price")
    missing: list[str] = []

    if not trusted_fundamental:
        missing.append("補上官方或 FinMind 基本面，才判斷獲利、估值與成長。")
    if not trusted_price:
        missing.append("接上可驗證日 K，才判斷突破、支撐、壓力與失效價。")

    if missing:
        return {
            "status": "data_limited",
            "label": "資料不足",
            "score": 18.0 if trusted_price else 8.0,
            "confidence": "低",
            "headline": "先補核心資料，不判斷爆發潛力",
            "thesis": "這檔目前只能當觀察標的；資料未可信前，不用漂亮分數或短線波動推論未來趨勢。",
            "leading_signals": ["可以先觀察價格結構與產業題材，但不列為合格爆發候選。"],
            "missing_confirmations": missing,
            "trigger_conditions": [
                "基本面來源變成官方、FinMind、TWSE 或 TPEX 可驗證資料。",
                "價格來源變成 FinMind、Yahoo 或 TWSE/TPEX 可驗證日 K。",
                "資料補齊後重新檢查基本面、估值與 K 線是否同時轉強。",
            ],
            "invalidation": "資料不足時不建立失效價，先避免把觀察當成進場依據。",
            "no_chase_warning": "資料不足時不追高，也不把候選清單視為飆股清單。",
        }

    score = 35.0
    leading: list[str] = []
    risks: list[str] = []
    composite_light = risk_lights.get("composite", "yellow")
    no_chase_zone = str(timing_gate.get("no_chase_zone") or "")
    has_no_chase = bool(no_chase_zone and no_chase_zone != "未觸發禁追條件")

    if fundamental_gate.get("passed"):
        score += 20
        leading.append(f"基本面 {fundamental_gate.get('grade', '-') } 級，獲利與成長先過研究門檻。")
    elif fundamental_gate.get("status") == "watch":
        score += 8
        missing.append("基本面只到觀察等級，需要下一次營收或財報確認。")
    else:
        score -= 24
        missing.append("基本面未通過，不能只靠題材或 K 線判斷爆發。")

    valuation_status = valuation_gate.get("status")
    if valuation_status == "pass":
        score += 12
        leading.append(f"估值落在{valuation_gate.get('pe_band', '合理')}區間，還沒有明顯追高。")
    elif valuation_status == "not_applicable":
        score += 4
        missing.append("ETF 或特殊標的不能用單一 PE 判斷，需要改看成分與大盤位置。")
    elif valuation_status == "watch":
        score -= 3
        missing.append(str(valuation_gate.get("warning") or "估值偏貴，等更好的價格。"))
    else:
        score -= 15
        missing.append(str(valuation_gate.get("warning") or "估值未通過，爆發潛力先降級。"))

    timing_status = timing_gate.get("status")
    if timing_status == "pass" and not has_no_chase:
        score += 16
        leading.append(f"K 線時機：{timing_gate.get('trend', '趨勢可觀察')}，且未觸發禁追。")
    elif timing_status == "watch":
        score += 4
        missing.append(f"K 線還要等：{no_chase_zone or timing_gate.get('trend', '訊號未完整')}。")
    else:
        score -= 18
        missing.append("K 線中長期趨勢未站穩，先不要把反彈當爆發。")

    score += _collect_breakout_technical_signals(technical, leading, risks)
    score += _collect_breakout_chip_signals(institutional, margin, leading, risks)
    score += _collect_breakout_sentiment_signal(sentiment, leading, risks)

    if composite_light == "green":
        score += 4
        leading.append("大盤綜合燈號偏綠，市場環境有利於強勢股延續。")
    elif composite_light == "red":
        score -= 20
        risks.append("大盤綜合燈號偏紅，爆發候選也要先降低追價慾望。")

    if has_no_chase:
        score -= 12
        risks.append(f"短線禁追：{no_chase_zone}。")

    score = round(max(0, min(100, score)), 2)
    status = _breakout_status(
        score=score,
        fundamental_gate=fundamental_gate,
        valuation_gate=valuation_gate,
        timing_gate=timing_gate,
        composite_light=composite_light,
        has_no_chase=has_no_chase,
    )
    no_chase_warning = _breakout_no_chase_warning(status, no_chase_zone, valuation_gate)
    trigger_conditions = _unique_nonempty(
        [
            *timing_gate.get("entry_conditions", [])[:2],
            "法人 5 日與 20 日維持偏買超或賣壓明顯收斂。",
            "下一次月營收或財報延續成長，不是只有題材發酵。",
        ]
    )[:4]

    return {
        "status": status,
        "label": _breakout_label(status),
        "score": score,
        "confidence": _breakout_confidence(status, score, missing, risks),
        "headline": _breakout_headline(status),
        "thesis": _breakout_thesis(status),
        "leading_signals": _unique_nonempty(leading)[:5]
        or ["尚未看到足以領先市場的基本面、籌碼與量價共振。"],
        "missing_confirmations": _unique_nonempty([*missing, *risks])[:5],
        "trigger_conditions": trigger_conditions,
        "invalidation": _breakout_invalidation(price_plan, timing_gate),
        "no_chase_warning": no_chase_warning,
    }


def _collect_breakout_technical_signals(
    technical: dict[str, Any],
    leading: list[str],
    risks: list[str],
) -> float:
    score = 0.0
    close = _to_float(technical.get("latest_close"))
    ma = technical.get("ma", {})
    ma20 = _to_float(ma.get("ma20"))
    ma60 = _to_float(ma.get("ma60"))
    ma120 = _to_float(ma.get("ma120"))
    rsi14 = _to_float(technical.get("rsi", {}).get("rsi14"))
    osc = _to_float(technical.get("macd", {}).get("osc"))
    volume_ratio = _to_float(technical.get("volume_ratio"))

    if technical.get("trend") == "bullish":
        score += 5
        leading.append("均線結構偏多，趨勢已比弱勢股更早轉強。")
    if close is not None and ma20 is not None and ma60 is not None and close > ma20 > ma60:
        score += 6
        leading.append("價格站上 MA20 與 MA60，短中期結構轉強。")
    elif close is not None and ma60 is not None and close < ma60:
        score -= 5
        risks.append("價格仍在 MA60 下方，還不是強勢啟動結構。")
    if close is not None and ma60 is not None and ma120 is not None and close > ma60 > ma120:
        score += 4
        leading.append("MA60 站上 MA120，中期趨勢有轉強跡象。")
    if osc is not None and osc > 0:
        score += 4
        leading.append("MACD 動能為正，短線資金動能沒有熄火。")
    if volume_ratio is not None:
        if 1.2 <= volume_ratio <= 2.0:
            score += 5
            leading.append(f"量比 {volume_ratio:.1f} 倍，資金開始注意但還不到爆量追高。")
        elif volume_ratio >= 2.5:
            score -= 5
            risks.append(f"量比 {volume_ratio:.1f} 倍偏高，可能已進入追價區。")
    if rsi14 is not None:
        if 50 <= rsi14 <= 68:
            score += 4
            leading.append(f"RSI14 {rsi14:.1f}，動能偏強但未明顯過熱。")
        elif rsi14 > 72:
            score -= 7
            risks.append(f"RSI14 {rsi14:.1f} 過熱，等回測再看。")
    return score


def _collect_breakout_chip_signals(
    institutional: dict[str, Any],
    margin: dict[str, Any],
    leading: list[str],
    risks: list[str],
) -> float:
    score = 0.0
    five_day_total = _to_float(institutional.get("five_day_total")) or 0.0
    twenty_day_total = _to_float(institutional.get("twenty_day_total")) or 0.0
    if five_day_total > 0 and twenty_day_total > 0:
        score += 8
        leading.append("法人 5 日與 20 日同步偏買，籌碼方向有延續性。")
    elif five_day_total < 0 and twenty_day_total < 0:
        score -= 8
        risks.append("法人短中期同步偏賣，爆發前需要先看到賣壓收斂。")
    if institutional.get("foreign_trend") == "accumulating":
        score += 3
        leading.append("外資趨勢偏累積，有利於波段資金延續。")
    if institutional.get("investment_trust_trend") == "accumulating":
        score += 2
        leading.append("投信趨勢偏累積，內資籌碼有支撐。")

    margin_status = margin.get("status")
    if margin_status in {"cleaning", "improving"}:
        score += 4
        leading.append("融資籌碼有沉澱或改善，追價浮額壓力較低。")
    elif margin_status == "crowded":
        score -= 6
        risks.append("融資籌碼偏擁擠，短線容易洗盤或回檔。")
    return score


def _collect_breakout_sentiment_signal(
    sentiment: dict[str, Any],
    leading: list[str],
    risks: list[str],
) -> float:
    score = _to_float(sentiment.get("score")) or 0.0
    if score > 0.35:
        leading.append("消息面偏正向，但只作輔助，不取代基本面與量價。")
        return 2.0
    if score < -0.35:
        risks.append("消息面偏負向，爆發假設需要更嚴格確認。")
        return -4.0
    return 0.0


def _breakout_status(
    *,
    score: float,
    fundamental_gate: dict[str, Any],
    valuation_gate: dict[str, Any],
    timing_gate: dict[str, Any],
    composite_light: str,
    has_no_chase: bool,
) -> str:
    if composite_light == "red" or fundamental_gate.get("status") == "fail" or timing_gate.get("status") == "fail":
        return "not_ready"
    if has_no_chase:
        return "too_extended"
    if valuation_gate.get("status") in {"watch", "fail", "unknown"}:
        return "wait_pullback"
    if score >= 78 and fundamental_gate.get("passed") and timing_gate.get("status") == "pass":
        return "ready_setup"
    if score >= 58:
        return "wait_confirmation"
    return "not_ready"


def _breakout_label(status: str) -> str:
    labels = {
        "ready_setup": "高潛力準備",
        "wait_confirmation": "等待確認",
        "wait_pullback": "等便宜價",
        "too_extended": "過熱禁追",
        "not_ready": "條件未齊",
        "data_limited": "資料不足",
    }
    return labels.get(status, "資料不足")


def _breakout_headline(status: str) -> str:
    headlines = {
        "ready_setup": "有領先轉強跡象，但仍用條件進場",
        "wait_confirmation": "有一些轉強訊號，等突破或回測確認",
        "wait_pullback": "公司可研究，但價格或估值還不夠漂亮",
        "too_extended": "已經急漲或過熱，現在不是聰明追價點",
        "not_ready": "爆發條件還沒湊齊，先把資金留給更清楚的標的",
        "data_limited": "先補核心資料，不判斷爆發潛力",
    }
    return headlines.get(status, "先補核心資料，不判斷爆發潛力")


def _breakout_thesis(status: str) -> str:
    theses = {
        "ready_setup": "基本面、估值、K 線與籌碼出現共振，適合列為優先研究候選；重點是等觸發條件，不追第一段急漲。",
        "wait_confirmation": "部分訊號已轉強，但還缺一到兩個確認點；適合放進觀察清單，等待條件完成。",
        "wait_pullback": "標的品質或趨勢可追蹤，但風報比還不夠好；等估值或價格回到計畫區再重算。",
        "too_extended": "題材與量價可能已被市場看見，現在追容易買在情緒高點；等回測、降溫或新基本面確認。",
        "not_ready": "目前不是爆發前的好結構；不要因為短線波動或單一題材就提高信心。",
        "data_limited": "資料未可信前，不把任何候選當成飆股或合格研究標的。",
    }
    return theses.get(status, theses["data_limited"])


def _breakout_confidence(status: str, score: float, missing: list[str], risks: list[str]) -> str:
    if status == "data_limited" or score < 45:
        return "低"
    if status == "ready_setup" and score >= 82 and not missing and not risks:
        return "高"
    if status in {"ready_setup", "wait_confirmation"} and score >= 65:
        return "中"
    return "低"


def _breakout_no_chase_warning(
    status: str,
    no_chase_zone: str,
    valuation_gate: dict[str, Any],
) -> str | None:
    if no_chase_zone and no_chase_zone != "未觸發禁追條件":
        return f"禁止追高：{no_chase_zone}。"
    if status == "wait_pullback":
        return str(valuation_gate.get("warning") or "估值或價格還不夠有優勢，不因短線上漲追價。")
    if status == "ready_setup":
        return "就算列為高潛力，也只等條件，不追急漲。"
    return None


def _breakout_invalidation(price_plan: dict[str, Any], timing_gate: dict[str, Any]) -> str:
    invalidation = _to_float(price_plan.get("invalidation_price")) or _to_float(timing_gate.get("invalidation_price"))
    if invalidation is None:
        return "尚未建立失效價，先不把它列為高信心候選。"
    return f"跌破 {invalidation:.2f} 代表爆發假設失效，重新檢查基本面與 K 線。"


def _unique_nonempty(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)
    return output


def _is_etf(symbol: str) -> bool:
    return symbol.startswith(ETF_SYMBOL_PREFIXES)


def _valuation_sector_band(symbol: str) -> dict[str, Any]:
    if symbol in TECH_SYMBOLS:
        return {"cheap": 18, "fair": 28, "expensive": 40, "label": "電子/半導體：便宜<=18，合理<=28，偏貴<=40"}
    if symbol.startswith(FINANCIAL_SYMBOL_PREFIXES) or symbol in FINANCIAL_SYMBOLS:
        return {"cheap": 12, "fair": 18, "expensive": 18, "label": "金融股：便宜<=12，合理<=18，>18偏貴"}
    return {"cheap": 15, "fair": 25, "expensive": 35, "label": "一般產業：便宜<=15，合理<=25，偏貴<=35"}


def score_sentiment(sentiment: dict) -> tuple[float, list[str], list[str]]:
    if sentiment.get("error") == "no_news" or not sentiment.get("headlines"):
        return 0.0, [], ["目前沒有可用新聞，不把新聞情緒納入加分或扣分。"]
    value = sentiment.get("score", 0)
    score = max(0, min(10, 5 + value * 5))
    if score >= 7:
        return score, ["新聞與重大資訊情緒偏正向。"], []
    if score <= 3:
        return score, [], ["新聞與重大資訊情緒偏負向。"]
    return score, ["新聞情緒中性。"], []
