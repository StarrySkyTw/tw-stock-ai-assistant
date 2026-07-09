from __future__ import annotations

import asyncio
from typing import Any

from app.core.config import get_settings
from app.services.analysis import AnalysisService
from app.services.calendar import taipei_now
from app.services.future_outlook import build_candidate_future_outlook
from app.services.industry import OTHER_INDUSTRY, SECTOR_THEMES, TECH_SECTORS, resolve_industry
from app.services.market_context import build_market_context
from app.services.market_risk import MarketRiskEngine

DEFAULT_AI_UNIVERSE = [
    "2330",
    "2317",
    "2454",
    "2308",
    "2382",
    "2412",
    "3711",
    "2603",
    "2609",
    "2615",
    "2881",
    "2882",
    "2891",
    "3008",
    "3034",
    "3443",
    "3661",
    "2357",
    "2379",
    "3231",
    "5871",
    "1216",
    "1303",
    "2002",
    "1101",
    "0050",
    "0056",
    "00878",
]

class AiStockPickerService:
    def __init__(self) -> None:
        self.analysis_service = AnalysisService()
        self.risk_engine = MarketRiskEngine()

    async def scan(
        self,
        universe: list[str] | None = None,
        limit: int = 5,
        min_score: float = 60.0,
    ) -> dict[str, Any]:
        symbols = normalize_universe(universe)
        settings = get_settings()
        market = await self.risk_engine.evaluate()
        analyses, failed = await self._analyze_universe(symbols, market, settings.analysis_background_timeout_seconds)
        all_candidates = [_build_candidate(item, market) for item in analyses]
        all_candidates.sort(key=lambda item: item["selection_score"], reverse=True)

        selected = [item for item in all_candidates if item["selection_score"] >= min_score]
        notes: list[str] = []
        if not selected and all_candidates:
            selected = all_candidates[:limit]
            notes.append(f"沒有標的達到 {min_score:.0f} 分門檻，先列出排序較高的候選股供複查。")
        selected = selected[:limit]
        for index, item in enumerate(selected, start=1):
            item["rank"] = index

        if failed:
            notes.append(f"{len(failed)} 檔資料載入失敗：{', '.join(failed[:8])}。")
        if market["lights"]["composite"] == "red":
            notes.append("大盤綜合燈號偏紅，候選股僅適合列入觀察，不宜把清單視為進場指令。")

        return {
            "generated_at": taipei_now(),
            "universe": symbols,
            "refresh": market["refresh"],
            "market_snapshot": {
                "status": market["status"],
                "score": market["score"],
                "light": market["lights"]["composite"],
                "reasons": market["reasons"],
                "indicators": market["indicators"],
                "generated_at": market["generated_at"],
                "market_date": market["market_date"],
                "refresh": market["refresh"],
            },
            "top_picks": selected,
            "selection_logic": [
                "先看基本面門檻：EPS、ROE、營收與利潤品質沒有過關，不因短線 K 線漂亮而優先。",
                "再看估值門檻：本益比是評價便宜或昂貴，不是股票價格高低。",
                "K 線只負責判斷時機：站穩中長期均線才加分，過熱急漲會觸發禁追。",
                "候選清單只供 3 個月到 2 年研究，不構成買進或下單指令。",
            ],
            "watch_notes": notes,
            "disclaimer": "AI 盤勢選股僅供研究與篩選，不構成投資建議、保證獲利或下單指令。",
        }

    async def _analyze_universe(
        self,
        symbols: list[str],
        market_risk: dict[str, Any],
        data_timeout_seconds: float | None = None,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        semaphore = asyncio.Semaphore(4)

        async def analyze_one(symbol: str) -> tuple[str, dict[str, Any] | None]:
            try:
                async with semaphore:
                    return symbol, await self.analysis_service.analyze(
                        symbol,
                        market_risk=market_risk,
                        data_timeout_seconds=data_timeout_seconds,
                    )
            except Exception:
                return symbol, None

        results = await asyncio.gather(*(analyze_one(symbol) for symbol in symbols))
        analyses = [analysis for _, analysis in results if analysis is not None]
        failed = [symbol for symbol, analysis in results if analysis is None]
        return analyses, failed


def normalize_universe(universe: list[str] | None = None) -> list[str]:
    raw_symbols = universe or DEFAULT_AI_UNIVERSE
    symbols: list[str] = []
    seen: set[str] = set()
    for item in raw_symbols:
        symbol = "".join(ch for ch in item.upper().strip() if ch.isalnum() or ch in {".", "^", "-"})
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        symbols.append(symbol)
        if len(symbols) >= 30:
            break
    return symbols or DEFAULT_AI_UNIVERSE


def _build_candidate(analysis: dict[str, Any], market: dict[str, Any]) -> dict[str, Any]:
    symbol = analysis["symbol"]
    industry = resolve_industry(symbol, analysis.get("name"), analysis.get("industry"))
    positive_factors: list[dict[str, str]] = []
    risk_factors: list[dict[str, str]] = []

    score = 45.0 + float(analysis["adjusted_score"]) * 0.15
    trusted_fundamental = _has_trusted_fundamental(analysis)
    score += _collect_gate_factors(analysis, positive_factors, risk_factors, trusted_fundamental)
    score += _collect_market_factors(market, industry, positive_factors, risk_factors)
    score += _collect_technical_factors(analysis["technical"], positive_factors, risk_factors) * 0.5
    score += _collect_institutional_factors(analysis["institutional"], positive_factors, risk_factors)
    score += _collect_strategy_factors(analysis["strategy_judgement"], positive_factors, risk_factors) * 0.5
    if trusted_fundamental:
        score += _collect_fundamental_factors(analysis["fundamental"], industry, positive_factors, risk_factors)
    else:
        score -= 10
        risk_factors.append(
            _factor("data_quality", "資料可信度", "基本面未接入可驗證真實來源，不採用 EPS、PE、ROE 或營收做排序理由。", "risk")
        )
    score += _collect_sentiment_factors(analysis["sentiment"], positive_factors, risk_factors)
    breakout = analysis["breakout_potential"]
    score += _collect_breakout_factor(breakout, positive_factors, risk_factors)
    candidate_status, blockers = classify_candidate_status(analysis, market)
    data_quality_score = _candidate_data_quality_score(analysis)
    score, score_cap_reason = _apply_score_quality_cap(score, candidate_status, analysis)
    score = round(max(0, min(100, score)), 2)
    why_ranked = _why_ranked(positive_factors, risk_factors, analysis)
    market_context = build_market_context(analysis, symbol)
    priority_factors = _candidate_future_priority_factors(analysis, market_context)

    if not positive_factors:
        positive_factors.append(
            _factor("summary", "綜合", "目前沒有明顯單一利多，需等待更清楚的量價或基本面訊號。", "neutral")
        )
    if not risk_factors:
        risk_factors.append(_factor("risk", "風險", "未偵測到重大單一風險，但仍需遵守停損與部位控管。", "neutral"))

    return {
        "rank": 0,
        "symbol": symbol,
        "name": analysis.get("name"),
        "industry": industry,
        "latest_close": analysis["technical"]["latest_close"],
        "recommendation": _candidate_action_label(candidate_status),
        "selection_score": score,
        "adjusted_score": analysis["adjusted_score"],
        "candidate_status": candidate_status,
        "data_quality_score": data_quality_score,
        "score_cap_reason": score_cap_reason,
        "bias": analysis["decision_plan"]["bias"],
        "confidence": analysis["research_decision"]["confidence"],
        "strategy_judgement": analysis["strategy_judgement"],
        "research_decision": analysis["research_decision"],
        "fundamental_gate": analysis["fundamental_gate"],
        "valuation_gate": analysis["valuation_gate"],
        "timing_gate": analysis["timing_gate"],
        "price_plan": analysis["price_plan"],
        "breakout_potential": breakout,
        "thesis": _thesis(symbol, analysis.get("name"), industry, score, positive_factors, market),
        "bullish_factors": positive_factors[:8],
        "risk_factors": risk_factors[:6],
        "score_breakdown": analysis["decision_plan"]["score_breakdown"],
        "data_quality": analysis["decision_plan"]["data_quality"],
        "source_notes": analysis["decision_plan"]["next_review_triggers"][:4],
        "data_sources": analysis["data_sources"],
        "blockers": blockers,
        "why_ranked": why_ranked,
        "no_chase_reason": _candidate_no_chase_reason(analysis),
        "future_outlook": build_candidate_future_outlook(
            analysis=analysis,
            market_context=market_context,
            priority_factors=priority_factors,
            latest_close=analysis.get("technical", {}).get("latest_close"),
            candidate_status=candidate_status,
        ),
    }


def build_candidate_from_analysis(analysis: dict[str, Any], market: dict[str, Any]) -> dict[str, Any]:
    return _build_candidate(analysis, market)


def classify_candidate_status(analysis: dict[str, Any], market: dict[str, Any]) -> tuple[str, list[str]]:
    data_sources = analysis.get("data_sources", {})
    decision = analysis["research_decision"]
    fundamental_gate = analysis["fundamental_gate"]
    valuation_gate = analysis["valuation_gate"]
    timing_gate = analysis["timing_gate"]
    composite_light = market.get("lights", {}).get("composite", "yellow")

    if not _is_trusted_source(str(data_sources.get("fundamental", "")), "fundamental"):
        blockers = [
            "基本面不是可驗證真實來源，僅能列為觀察，不能當成合格標的。",
            "估值與獲利數字不是可驗證真實來源，本輪不採用 PE、PB、ROE 或營收作判斷。",
        ]
        timing_reason = _technical_no_chase_reason(decision.get("do_not_chase_reason"))
        if timing_reason:
            blockers.append(timing_reason)
        return "watch_only", _dedupe(blockers)
    if not _is_trusted_source(str(data_sources.get("price", "")), "price"):
        blockers = [
            "價格資料不是可驗證日 K，不能建立支撐、壓力、失效價或波段候選。",
            "先補上可信價格來源，再重新掃描未來劇本。",
        ]
        return "watch_only", _dedupe(blockers)
    blockers = list(decision.get("blockers", []))
    if fundamental_gate["status"] == "fail":
        blockers.append("基本面門檻未通過。")
        return "reject", _dedupe(blockers)
    if composite_light == "red":
        blockers.append("大盤綜合燈號為紅燈。")
        return "reject", _dedupe(blockers)
    if timing_gate["status"] == "fail":
        blockers.append("K 線中長期趨勢未站穩。")
        return "reject", _dedupe(blockers)
    if valuation_gate["status"] in {"watch", "fail", "unknown"}:
        blockers.append(valuation_gate.get("warning") or "估值尚未進入合理或便宜區間。")
        return "wait_price", _dedupe(blockers)
    if decision.get("do_not_chase_reason") or timing_gate["status"] != "pass":
        blockers.append(decision.get("do_not_chase_reason") or "K 線時機尚未乾淨。")
        return "watch_only", _dedupe(blockers)
    if fundamental_gate["passed"] and valuation_gate["status"] in {"pass", "not_applicable"}:
        return "qualified_research", _dedupe(blockers)
    blockers.append("條件尚未完整，先維持觀察。")
    return "watch_only", _dedupe(blockers)


def _candidate_data_quality_score(analysis: dict[str, Any]) -> float:
    sources = analysis.get("data_sources", {})
    weights = {
        "fundamental": 40,
        "price": 20,
        "institutional": 12,
        "margin": 10,
        "news": 10,
        "shareholding": 8,
    }
    score = 0
    for key, weight in weights.items():
        if _is_trusted_source(str(sources.get(key, "")), key):
            score += weight
    return float(score)


def _has_trusted_fundamental(analysis: dict[str, Any]) -> bool:
    return _is_trusted_source(str(analysis.get("data_sources", {}).get("fundamental", "")), "fundamental")


def _candidate_no_chase_reason(analysis: dict[str, Any]) -> str | None:
    reason = analysis["research_decision"].get("do_not_chase_reason")
    if _has_trusted_fundamental(analysis):
        return reason
    return _technical_no_chase_reason(reason)


def _candidate_future_priority_factors(
    analysis: dict[str, Any],
    market_context: dict[str, Any],
) -> list[dict[str, Any]]:
    signals = [dict(signal) for signal in market_context.get("signals", [])]
    metrics = analysis.get("fundamental_gate", {}).get("metrics", {})
    revenue_yoy = _float_or_none(metrics.get("revenue_yoy"))
    revenue_mom = _float_or_none(metrics.get("revenue_mom"))
    valuation = analysis.get("valuation_gate", {})
    timing = analysis.get("timing_gate", {})

    if not _has_trusted_fundamental(analysis):
        signals.append(
            _candidate_signal(
                "revenue",
                "預期差",
                "基本面來源不足，不能用營收或估值推論未來利多。",
                "neutral",
                1,
            )
        )
    elif revenue_yoy is not None and revenue_yoy < 0:
        signals.append(
            _candidate_signal("revenue", "預期差", "營收年增轉負，存在負向預期差風險。", "risk", 1)
        )
    elif revenue_yoy is not None and revenue_yoy >= 20 and (revenue_mom is None or revenue_mom >= 0):
        signals.append(
            _candidate_signal(
                "revenue",
                "預期差",
                "營收動能有正向預期差雛形，但仍要等事件或價格確認。",
                "positive",
                1,
            )
        )
    else:
        signals.append(
            _candidate_signal("revenue", "預期差", "預期差尚未明顯打開，不能只因反彈就假設利多。", "neutral", 2)
        )

    valuation_status = str(valuation.get("status") or "unknown")
    if valuation_status in {"watch", "fail", "unknown"}:
        signals.append(
            _candidate_signal(
                "valuation",
                "估值空間",
                str(valuation.get("warning") or "估值還沒進入安全邊際，候選先等價位。"),
                "risk",
                1,
            )
        )
    else:
        signals.append(
            _candidate_signal("valuation", "估值空間", str(valuation.get("pe_band") or "估值未構成主要阻擋。"), "positive", 2)
        )

    timing_status = str(timing.get("status") or "unknown")
    if timing_status == "pass" and not analysis.get("research_decision", {}).get("do_not_chase_reason"):
        signals.append(
            _candidate_signal(
                "timing",
                "波段時機",
                str(timing.get("support_zone") or "K 線時機通過，等支撐回測或突破後確認。"),
                "positive",
                2,
            )
        )
    else:
        signals.append(
            _candidate_signal(
                "timing",
                "波段時機",
                str(analysis.get("research_decision", {}).get("do_not_chase_reason") or timing.get("trend") or "K 線時機未完整。"),
                "risk",
                1,
            )
        )

    return signals


def _candidate_signal(kind: str, label: str, detail: str, tone: str, priority: int) -> dict[str, Any]:
    return {"kind": kind, "label": label, "detail": detail, "tone": tone, "priority": priority}


def _technical_no_chase_reason(reason: str | None) -> str | None:
    if not reason:
        return None
    if any(keyword in reason for keyword in ("RSI", "量比", "MA20", "爆量", "K 線", "追高")):
        return reason
    return None


def _apply_score_quality_cap(
    score: float,
    candidate_status: str,
    analysis: dict[str, Any],
) -> tuple[float, str | None]:
    sources = analysis.get("data_sources", {})
    if not _is_trusted_source(str(sources.get("fundamental", "")), "fundamental"):
        return min(score, 49.0), "基本面不是真實可驗證資料，排序分數上限為 49。"
    if not _is_trusted_source(str(sources.get("price", "")), "price"):
        return min(score, 49.0), "價格資料不是可驗證日 K，波段候選分數上限為 49。"
    if candidate_status == "watch_only":
        return min(score, 69.0), "候選仍屬只觀察，排序分數上限為 69。"
    if candidate_status == "reject":
        return min(score, 39.0), "候選已被排除，排序分數上限為 39。"
    return score, None


def _candidate_action_label(candidate_status: str) -> str:
    labels = {
        "qualified_research": "合格研究",
        "wait_price": "等便宜價",
        "watch_only": "只觀察",
        "reject": "排除",
    }
    return labels.get(candidate_status, "只觀察")


def _is_trusted_source(source: str, key: str) -> bool:
    normalized = source.lower()
    if "sample" in normalized or not normalized or normalized == "unavailable":
        return False
    if key in {"fundamental", "institutional", "margin", "shareholding"}:
        trusted_by_key = {
            "fundamental": ("finmind", "twse-openapi", "tpex-openapi"),
            "institutional": ("finmind", "twse-t86", "tpex-insti"),
            "margin": ("finmind", "twse-margin", "tpex-margin"),
            "shareholding": ("finmind", "tdcc"),
        }
        return any(provider in normalized for provider in trusted_by_key[key])
    if key == "price":
        return any(provider in normalized for provider in ("finmind", "twse", "yahoo"))
    if key == "news":
        return any(provider in normalized for provider in ("finmind", "twse-material", "tpex-material"))
    return False


def _why_ranked(
    positive: list[dict[str, str]],
    risks: list[dict[str, str]],
    analysis: dict[str, Any],
) -> list[str]:
    reasons = [item["detail"] for item in positive if item.get("tone") == "positive"][:3]
    if (
        _has_trusted_fundamental(analysis)
        and analysis["valuation_gate"]["status"] in {"watch", "fail"}
        and analysis["valuation_gate"].get("warning")
    ):
        reasons.append(str(analysis["valuation_gate"]["warning"]))
    do_not_chase_reason = analysis["research_decision"].get("do_not_chase_reason")
    if do_not_chase_reason:
        if _has_trusted_fundamental(analysis):
            reasons.append(str(do_not_chase_reason))
        else:
            timing_reason = _technical_no_chase_reason(str(do_not_chase_reason))
            if timing_reason:
                reasons.append(timing_reason)
    if not reasons:
        reasons = [item["detail"] for item in [*positive, *risks]][:3]
    return _dedupe(reasons)[:4]


def _dedupe(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        output.append(normalized)
    return output


def _collect_gate_factors(
    analysis: dict[str, Any],
    positive: list[dict[str, str]],
    risks: list[dict[str, str]],
    trusted_fundamental: bool,
) -> float:
    bonus = 0.0
    fundamental_gate = analysis["fundamental_gate"]
    valuation_gate = analysis["valuation_gate"]
    timing_gate = analysis["timing_gate"]
    decision = analysis["research_decision"]

    if trusted_fundamental:
        if fundamental_gate["passed"]:
            bonus += 16
            positive.append(
                _factor("fundamental", "基本面門檻", f"基本面 {fundamental_gate['grade']} 級，先通過中長期研究門檻。")
            )
        elif fundamental_gate["status"] == "watch":
            bonus += 4
            risks.append(_factor("fundamental", "基本面門檻", "基本面只達觀察等級，不能因 K 線轉強就追。", "neutral"))
        else:
            bonus -= 24
            risks.append(
                _factor(
                    "fundamental",
                    "基本面門檻",
                    fundamental_gate["failed_reasons"][0] if fundamental_gate["failed_reasons"] else "基本面未通過。",
                    "risk",
                )
            )

        if valuation_gate["status"] == "pass":
            bonus += 14
            positive.append(_factor("valuation", "估值", f"本益比屬於{valuation_gate['pe_band']}，估值未明顯過熱。"))
        elif valuation_gate["status"] == "not_applicable":
            positive.append(_factor("valuation", "估值", "ETF 不用單一 PE 判斷，需改看成分股與大盤位置。", "neutral"))
        elif valuation_gate["status"] == "watch":
            bonus -= 2
            risks.append(_factor("valuation", "估值", valuation_gate["warning"] or "估值偏貴，等便宜價。", "neutral"))
        else:
            bonus -= 16
            risks.append(_factor("valuation", "估值", valuation_gate["warning"] or "估值未通過。", "risk"))

    if timing_gate["status"] == "pass":
        bonus += 8
        positive.append(_factor("timing", "K線時機", timing_gate["trend"]))
    elif timing_gate["status"] == "watch":
        risks.append(_factor("timing", "K線時機", timing_gate["no_chase_zone"], "neutral"))
    else:
        bonus -= 10
        risks.append(_factor("timing", "K線時機", timing_gate["trend"], "risk"))

    do_not_chase_reason = decision.get("do_not_chase_reason")
    if do_not_chase_reason and trusted_fundamental:
        bonus -= 5
        risks.append(_factor("discipline", "禁追", do_not_chase_reason, "risk"))
    elif do_not_chase_reason:
        timing_reason = _technical_no_chase_reason(str(do_not_chase_reason))
        if timing_reason:
            bonus -= 5
            risks.append(_factor("discipline", "禁追", timing_reason, "risk"))
    return bonus


def _collect_market_factors(
    market: dict[str, Any],
    industry: str,
    positive: list[dict[str, str]],
    risks: list[dict[str, str]],
) -> float:
    bonus = 0.0
    light = market["lights"]["composite"]
    indicators = market["indicators"]
    if light == "green":
        bonus += 3
        positive.append(_factor("market", "盤勢", f"大盤綜合燈號為綠燈，市場狀態偏向{market['status']}。"))
    elif light == "red":
        bonus -= 8
        risks.append(_factor("market", "盤勢", "大盤綜合燈號偏紅，需降低追價與持倉風險。", "risk"))
    else:
        positive.append(
            _factor("market", "盤勢", f"大盤狀態為{market['status']}，適合以條件篩選而非全面追價。", "neutral")
        )

    sox = _float_or_none(indicators.get("sox_change_5d"))
    nasdaq = _float_or_none(indicators.get("nasdaq_change_5d"))
    if industry in TECH_SECTORS:
        if (sox is not None and sox > 1) or (nasdaq is not None and nasdaq > 1):
            bonus += 3
            positive.append(_factor("industry", "產業", "Nasdaq 或費半近 5 日偏強，對電子與半導體族群情緒有加分。"))
        elif sox is not None and sox < -2:
            bonus -= 4
            risks.append(_factor("industry", "產業", "費半近 5 日轉弱，電子權值與半導體族群需保守。", "risk"))

    theme = SECTOR_THEMES.get(industry)
    if theme:
        positive.append(_factor("industry", "產業定位", theme, "neutral"))
    return bonus


def _collect_technical_factors(
    technical: dict[str, Any],
    positive: list[dict[str, str]],
    risks: list[dict[str, str]],
) -> float:
    bonus = 0.0
    trend = technical.get("trend")
    close = _float_or_none(technical.get("latest_close"))
    ma20 = _float_or_none(technical.get("ma", {}).get("ma20"))
    ma60 = _float_or_none(technical.get("ma", {}).get("ma60"))
    rsi14 = _float_or_none(technical.get("rsi", {}).get("rsi14"))
    osc = _float_or_none(technical.get("macd", {}).get("osc"))
    volume_ratio = _float_or_none(technical.get("volume_ratio"))

    if trend == "bullish":
        bonus += 3
        positive.append(_factor("technical", "趨勢", "均線多頭排列，短中期趨勢偏多。"))
    elif trend == "bearish":
        bonus -= 5
        risks.append(_factor("technical", "趨勢", "均線空頭排列，趨勢仍偏弱。", "risk"))

    if close is not None and ma20 is not None and ma60 is not None and close > ma20 > ma60:
        bonus += 3
        positive.append(_factor("technical", "價位", f"收盤價 {close:.2f} 站上 MA20 與 MA60。"))
    if osc is not None and osc > 0:
        bonus += 1.5
        positive.append(_factor("technical", "動能", "MACD 柱狀體為正，短線動能偏強。"))
    if volume_ratio is not None and volume_ratio >= 1.3:
        bonus += 1
        positive.append(_factor("technical", "量能", f"成交量約為 20 日均量 {volume_ratio:.1f} 倍，資金關注度提高。"))
    if rsi14 is not None:
        if 45 <= rsi14 <= 68:
            bonus += 1
            positive.append(_factor("technical", "RSI", f"RSI14 為 {rsi14:.1f}，動能未明顯過熱。"))
        elif rsi14 > 75:
            bonus -= 3
            risks.append(_factor("technical", "RSI", f"RSI14 已到 {rsi14:.1f}，短線過熱風險提高。", "risk"))
    return bonus


def _collect_institutional_factors(
    institutional: dict[str, Any],
    positive: list[dict[str, str]],
    risks: list[dict[str, str]],
) -> float:
    bonus = 0.0
    flow_5d = _float_or_none(institutional.get("five_day_total")) or 0.0
    flow_20d = _float_or_none(institutional.get("twenty_day_total")) or 0.0
    if flow_5d > 0 and flow_20d > 0:
        bonus += 4
        positive.append(
            _factor("institutional", "法人", f"三大法人 5 日與 20 日合計偏買超，20 日合計約 {flow_20d:,.0f}。")
        )
    elif flow_5d < 0 and flow_20d < 0:
        bonus -= 5
        risks.append(_factor("institutional", "法人", "三大法人短中期同步偏賣超，籌碼面需保守。", "risk"))
    if institutional.get("foreign_trend") == "accumulating":
        bonus += 1.5
        positive.append(_factor("institutional", "外資", "外資短中期趨勢偏累積。"))
    if institutional.get("investment_trust_trend") == "accumulating":
        bonus += 1
        positive.append(_factor("institutional", "投信", "投信短中期趨勢偏累積。"))
    return bonus


def _collect_strategy_factors(
    strategy: dict[str, Any],
    positive: list[dict[str, str]],
    risks: list[dict[str, str]],
) -> float:
    bonus = 0.0
    stance = strategy.get("stance")
    timing_score = _float_or_none(strategy.get("timing_score")) or 0.0
    if stance == "prepare_entry":
        bonus += 6
        positive.append(_factor("strategy", "進場時機", strategy.get("headline") or "接近可研究進場。"))
    elif stance == "hold_steady":
        bonus += 3
        positive.append(_factor("strategy", "守穩觀察", strategy.get("headline") or "價格仍守穩可觀察。", "neutral"))
    elif stance == "reduce_risk":
        bonus -= 7
        risks.append(_factor("strategy", "先守風險", strategy.get("headline") or "目前不急著進場。", "risk"))
    else:
        bonus -= 2
        risks.append(_factor("strategy", "等待訊號", strategy.get("headline") or "等待更乾淨訊號。", "neutral"))

    if timing_score >= 80:
        bonus += 3
        positive.append(_factor("strategy", "AI 時機分", f"策略時機分 {timing_score:.0f}，符合優先觀察門檻。"))
    elif timing_score < 55:
        bonus -= 3
        risks.append(_factor("strategy", "AI 時機分", f"策略時機分 {timing_score:.0f}，仍需等待。", "risk"))

    chip_cleanliness = strategy.get("chip_cleanliness")
    if chip_cleanliness:
        if stance in {"prepare_entry", "hold_steady"}:
            positive.append(_factor("strategy", "籌碼乾淨度", chip_cleanliness))
        else:
            risks.append(_factor("strategy", "籌碼乾淨度", chip_cleanliness, "neutral"))
    return bonus


def _collect_fundamental_factors(
    fundamental: dict[str, Any],
    industry: str,
    positive: list[dict[str, str]],
    risks: list[dict[str, str]],
) -> float:
    bonus = 0.0
    eps = _float_or_none(fundamental.get("eps"))
    roe = _float_or_none(fundamental.get("roe"))
    gross_margin = _float_or_none(fundamental.get("gross_margin"))
    revenue_yoy = _float_or_none(fundamental.get("revenue_yoy"))
    pe_ratio = _float_or_none(fundamental.get("pe_ratio"))

    if eps is not None and eps > 0:
        bonus += 1.5
        positive.append(_factor("fundamental", "獲利", f"EPS 為 {eps:.2f}，基本獲利為正。"))
    if roe is not None and roe >= 15:
        bonus += 2.5
        positive.append(_factor("fundamental", "ROE", f"ROE {roe:.1f}% 高於 15%，資本效率佳。"))
    elif roe is not None and roe < 8:
        bonus -= 2
        risks.append(_factor("fundamental", "ROE", f"ROE {roe:.1f}% 偏低，基本面品質需複查。", "risk"))
    if revenue_yoy is not None and revenue_yoy >= 10:
        bonus += 2
        positive.append(_factor("fundamental", "營收", f"營收年增 {revenue_yoy:.1f}%，成長動能明確。"))
    elif revenue_yoy is not None and revenue_yoy < 0:
        bonus -= 2
        risks.append(_factor("fundamental", "營收", f"營收年增 {revenue_yoy:.1f}%，成長動能轉弱。", "risk"))
    if gross_margin is not None and gross_margin >= 35:
        bonus += 1
        positive.append(_factor("fundamental", "毛利率", f"毛利率 {gross_margin:.1f}%，產業競爭力較佳。"))
    if pe_ratio is not None:
        if pe_ratio <= 25:
            bonus += 1
            positive.append(_factor("fundamental", "評價", f"本益比 {pe_ratio:.1f}，評價未明顯過熱。"))
        elif pe_ratio > 40:
            bonus -= 2
            risks.append(_factor("fundamental", "評價", f"本益比 {pe_ratio:.1f} 偏高，需留意評價修正。", "risk"))
    if industry == OTHER_INDUSTRY:
        risks.append(_factor("industry", "產業", "產業分類暫列其他產業，產業面仍需人工確認。", "neutral"))
    return bonus


def _collect_sentiment_factors(
    sentiment: dict[str, Any],
    positive: list[dict[str, str]],
    risks: list[dict[str, str]],
) -> float:
    score = _float_or_none(sentiment.get("score")) or 0.0
    if score > 0.25:
        positive.append(_factor("sentiment", "新聞", sentiment.get("summary") or "新聞情緒偏正向。"))
        return 1.5
    if score < -0.25:
        risks.append(_factor("sentiment", "新聞", sentiment.get("summary") or "新聞情緒偏負向。", "risk"))
        return -2
    positive.append(_factor("sentiment", "新聞", sentiment.get("summary") or "新聞情緒中性。", "neutral"))
    return 0.0


def _collect_breakout_factor(
    breakout: dict[str, Any],
    positive: list[dict[str, str]],
    risks: list[dict[str, str]],
) -> float:
    status = breakout.get("status")
    score = _float_or_none(breakout.get("score")) or 0.0
    headline = str(breakout.get("headline") or "等待爆發潛力判斷。")
    if status == "ready_setup":
        positive.append(_factor("breakout", "爆發潛力", headline))
        return min(7.0, max(3.0, (score - 65) * 0.18))
    if status == "wait_confirmation":
        positive.append(_factor("breakout", "爆發潛力", headline, "neutral"))
        return 2.0
    if status in {"wait_pullback", "too_extended"}:
        risks.append(_factor("breakout", "爆發潛力", breakout.get("no_chase_warning") or headline, "neutral"))
        return -2.0
    if status == "not_ready":
        risks.append(_factor("breakout", "爆發潛力", headline, "risk"))
        return -5.0
    risks.append(_factor("breakout", "爆發潛力", "資料不足，不判斷爆發潛力。", "neutral"))
    return -4.0


def _thesis(
    symbol: str,
    name: str | None,
    industry: str,
    score: float,
    factors: list[dict[str, str]],
    market: dict[str, Any],
) -> str:
    display = f"{symbol} {name}" if name else symbol
    highlights = [_clause(item["detail"]) for item in factors if item["tone"] == "positive"][:3]
    if not highlights:
        highlights = [_clause(item["detail"]) for item in factors[:2]]
    joined = "；".join(highlights)
    market_status = market["status"]
    if market["lights"]["composite"] == "red":
        return f"{display} 分數 {score:.0f}，但今日盤勢為{market_status}且風險偏高，適合先列觀察並等待確認。"
    if industry == OTHER_INDUSTRY:
        return f"{display} 產業分類暫列其他產業，今日盤勢為{market_status}；{joined}，可先列觀察並確認公司業務。"
    return f"{display} 屬於{industry}，今日盤勢為{market_status}；{joined}，可列入優先研究候選。"


def _factor(kind: str, label: str, detail: str, tone: str = "positive") -> dict[str, str]:
    return {"kind": kind, "label": label, "detail": detail, "tone": tone}


def _clause(value: str) -> str:
    return value.strip().rstrip("。；;，, ")


def _float_or_none(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
