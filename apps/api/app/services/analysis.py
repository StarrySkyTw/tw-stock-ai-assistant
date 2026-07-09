from __future__ import annotations

import asyncio
from time import monotonic

import pandas as pd

from app.core.config import get_settings
from app.services import sample_data
from app.services.calendar import market_refresh_clock, taipei_now, taipei_today
from app.services.data_providers import MarketDataService
from app.services.data_providers.base import FundamentalData, ShareholdingData
from app.services.data_providers.composite import _empty_institutional_flows, _empty_margin_balances
from app.services.indicators import calculate_indicators, summarize_technical
from app.services.industry import resolve_industry
from app.services.market_risk import MarketRiskEngine
from app.services.scoring import (
    build_price_plan,
    build_research_decision,
    evaluate_breakout_potential,
    evaluate_fundamental_gate,
    evaluate_timing_gate,
    evaluate_valuation_gate,
    recommendation_from_score,
    score_fundamental,
    score_institutional,
    score_margin,
    score_sentiment,
    score_technical,
    summarize_institutional,
    summarize_margin,
)
from app.services.sentiment import analyze_news_sentiment
from app.services.source_quality import is_trusted_source


class AnalysisService:
    def __init__(self) -> None:
        self.data = MarketDataService()
        self.risk_engine = MarketRiskEngine()

    async def analyze(
        self,
        symbol: str,
        entry_price: float | None = None,
        highest_price: float | None = None,
        atr_multiplier: float = 2.0,
        market_risk: dict | None = None,
        data_timeout_seconds: float | None = None,
    ) -> dict:
        symbol = symbol.upper().strip()
        settings = get_settings()
        explicit_data_budget = data_timeout_seconds is not None
        data_budget = max(0.35, data_timeout_seconds if explicit_data_budget else settings.analysis_data_timeout_seconds)
        deadline = monotonic() + data_budget
        source_timeout = _source_timeout_seconds(data_budget, explicit_data_budget)
        risk_task = asyncio.create_task(self.risk_engine.evaluate()) if market_risk is None else None
        (
            stock_profile,
            (prices, price_source),
            (flows, flow_source),
            (margin_rows, margin_source),
            (fundamentals, fundamental_source),
            (shareholding, shareholding_source),
            (news, news_source),
        ) = await asyncio.gather(
            _with_timeout(self.data.stock_profile(symbol), _fallback_stock_profile(symbol), source_timeout),
            _with_timeout(self.data.prices(symbol, years=2), _fallback_prices(symbol), source_timeout),
            _with_timeout(self.data.institutional_flows(symbol), (_empty_institutional_flows(), "unavailable"), source_timeout),
            _with_timeout(self.data.margin_balances(symbol), (_empty_margin_balances(), "unavailable"), source_timeout),
            _with_timeout(self.data.fundamentals(symbol), (FundamentalData().to_dict(), "unavailable"), source_timeout),
            _with_timeout(self.data.shareholding(symbol), (ShareholdingData().to_dict(), "unavailable"), source_timeout),
            _with_timeout(self.data.news(symbol), ([], "unavailable"), source_timeout),
        )
        stock_name = stock_profile.get("name")
        industry = stock_profile.get("industry")
        risk = market_risk if market_risk is not None else await _with_timeout(
            risk_task,
            _fallback_market_risk(),
            _remaining_timeout(deadline),
        )
        indicators = calculate_indicators(prices)
        technical = summarize_technical(indicators)
        institutional = summarize_institutional(flows)
        margin = summarize_margin(margin_rows)
        sentiment = await _with_timeout(
            analyze_news_sentiment(symbol, news),
            _fallback_sentiment(news),
            _remaining_timeout(deadline),
        )
        data_sources = {
            "price": price_source,
            "institutional": flow_source,
            "margin": margin_source,
            "fundamental": fundamental_source,
            "shareholding": shareholding_source,
            "news": news_source,
        }

        technical_score, tech_reasons, tech_risks = score_technical(technical)
        institutional_score, inst_reasons, inst_risks = score_institutional(
            institutional, _float_or_none(shareholding.get("large_holder_ratio"))
        )
        margin_adjustment, margin_reasons, margin_risks = score_margin(margin)
        fundamental_score, fund_reasons, fund_risks = score_fundamental(fundamentals)
        sentiment_score, sentiment_reasons, sentiment_risks = score_sentiment(sentiment)
        if not is_trusted_source(flow_source, "institutional"):
            institutional_score = 0.0
            inst_reasons = []
            inst_risks = ["法人籌碼資料未接入或不是可驗證真實來源，本輪不納入加減分。"]
        if not is_trusted_source(margin_source, "margin"):
            margin_adjustment = 0.0
            margin_reasons = []
            margin_risks = ["信用交易資料未接入或不是可驗證真實來源，本輪不納入加減分。"]
        if not is_trusted_source(fundamental_source, "fundamental"):
            fundamental_score = 0.0
            fund_reasons = []
            fund_risks = ["基本面資料不是可驗證真實來源，不採用 EPS、PE、ROE 或營收計分。"]
        if not is_trusted_source(news_source, "news"):
            sentiment_score = 0.0
            sentiment_reasons = []
            sentiment_risks = [_source_missing_note("新聞情緒", news_source)]
        if _is_sample_source(price_source):
            technical_score = 0.0
            tech_reasons = []
            tech_risks = ["價格資料不是可驗證歷史日 K，不採用 K 線或技術分數。"]

        raw_score = technical_score + institutional_score + fundamental_score + sentiment_score
        adjusted_score = raw_score
        adjusted_score += margin_adjustment
        risk_adjustment = 0.0
        risks = tech_risks + inst_risks + margin_risks + fund_risks + sentiment_risks
        reasons = tech_reasons + inst_reasons + margin_reasons + fund_reasons + sentiment_reasons
        if risk["lights"]["risk_indicator"] == "red":
            risk_adjustment = -8.0
            adjusted_score += risk_adjustment
            risks.append("Market Risk Engine 顯示風險紅燈，總分下修 8 分。")
        adjusted_score = max(0, min(100, adjusted_score))
        adjusted_score, data_quality_caps = _apply_data_quality_score_cap(adjusted_score, data_sources)
        if data_quality_caps:
            risks.extend(data_quality_caps)
        score_breakdown = {
            "technical": round(technical_score, 2),
            "institutional": round(institutional_score, 2),
            "margin": round(margin_adjustment, 2),
            "fundamental": round(fundamental_score, 2),
            "sentiment": round(sentiment_score, 2),
            "market_risk_adjustment": risk_adjustment,
        }

        latest = indicators.iloc[-1]
        close = float(latest["close"])
        effective_entry = entry_price or close
        stop_loss = _stop_loss(effective_entry, technical, close)
        trailing = _trailing_take_profit(
            indicators, effective_entry, highest_price, atr_multiplier=atr_multiplier
        )
        if _is_sample_source(price_source):
            stop_loss = _untrusted_stop_loss()
            trailing = _untrusted_trailing_take_profit(atr_multiplier)
        fundamental_gate = evaluate_fundamental_gate(fundamentals)
        valuation_gate = evaluate_valuation_gate(symbol, fundamentals)
        timing_gate = evaluate_timing_gate(technical)
        fundamental_gate, valuation_gate, timing_gate = _apply_data_quality_gate_guards(
            fundamental_gate=fundamental_gate,
            valuation_gate=valuation_gate,
            timing_gate=timing_gate,
            data_sources=data_sources,
        )
        price_plan = (
            _untrusted_price_plan()
            if _is_sample_source(price_source)
            else build_price_plan(technical, timing_gate, valuation_gate)
        )
        research_decision = build_research_decision(
            fundamental_gate=fundamental_gate,
            valuation_gate=valuation_gate,
            timing_gate=timing_gate,
            price_plan=price_plan,
            risk_lights=risk["lights"],
            data_sources=data_sources,
        )
        strategy_judgement = _strategy_judgement(
            adjusted_score=adjusted_score,
            technical=technical,
            institutional=institutional,
            margin=margin,
            risk_lights=risk["lights"],
        )
        breakout_potential = evaluate_breakout_potential(
            fundamental_gate=fundamental_gate,
            valuation_gate=valuation_gate,
            timing_gate=timing_gate,
            price_plan=price_plan,
            technical=technical,
            institutional=institutional,
            margin=margin,
            sentiment=sentiment,
            risk_lights=risk["lights"],
            data_sources=data_sources,
        )

        reasons.append(f"價格資料來源：{price_source}；法人資料來源：{flow_source}。")
        if not is_trusted_source(fundamental_source, "fundamental"):
            reasons.append("基本面資料未接入可驗證真實來源，補齊後才採用 EPS、PE、ROE 或營收。")
        if news_source == "sample":
            reasons.append("新聞情緒目前使用示範來源，本輪不納入情緒加減分。")
        elif not is_trusted_source(news_source, "news"):
            reasons.append("新聞情緒資料未接入，本輪不納入情緒加減分。")
        recommendation = _recommendation_for_analysis(adjusted_score, data_sources)
        decision_plan = _decision_plan(
            symbol=symbol,
            name=stock_name,
            recommendation=recommendation,
            adjusted_score=adjusted_score,
            raw_score=raw_score,
            score_breakdown=score_breakdown,
            technical=technical,
            institutional=institutional,
            margin=margin,
            sentiment=sentiment,
            stop_loss=stop_loss,
            trailing=trailing,
            risk_lights=risk["lights"],
            reasons=reasons,
            risks=risks,
            data_sources=data_sources,
        )

        return {
            "symbol": symbol,
            "name": stock_name,
            "industry": industry,
            "analysis_date": taipei_today(),
            "generated_at": taipei_now(),
            "refresh": risk["refresh"],
            "data_sources": data_sources,
            "raw_score": round(raw_score, 2),
            "adjusted_score": round(adjusted_score, 2),
            "recommendation": recommendation,
            "reasons": reasons,
            "risks": risks or ["目前未偵測到重大單一風險，但仍需遵守停損。"],
            "technical": technical,
            "institutional": institutional,
            "margin": margin,
            "fundamental": _fundamentals_for_response(fundamentals, fundamental_source, fund_reasons),
            "sentiment": sentiment,
            "stop_loss": stop_loss,
            "trailing_take_profit": trailing,
            "risk_lights": risk["lights"],
            "decision_plan": decision_plan,
            "research_decision": research_decision,
            "fundamental_gate": fundamental_gate,
            "valuation_gate": valuation_gate,
            "timing_gate": timing_gate,
            "price_plan": price_plan,
            "strategy_judgement": strategy_judgement,
            "breakout_potential": breakout_potential,
            "kline_analysis": (
                _untrusted_kline_analysis()
                if _is_sample_source(price_source)
                else _kline_analysis(technical, stop_loss, trailing, strategy_judgement)
            ),
        }

    async def chart(self, symbol: str, range_name: str = "1y") -> dict:
        symbol = symbol.upper().strip()
        stock_name = await self.data.stock_name(symbol)
        years = 5 if range_name == "5y" else 3 if range_name == "3y" else 1
        prices, _ = await self.data.prices(symbol, years=years)
        df = calculate_indicators(prices)
        dates = [item.isoformat() for item in pd.to_datetime(df["date"]).dt.date]
        figure = {
            "data": [
                {
                    "type": "candlestick",
                    "name": "K線",
                    "x": dates,
                    "open": _series_to_numbers(df["open"]),
                    "high": _series_to_numbers(df["high"]),
                    "low": _series_to_numbers(df["low"]),
                    "close": _series_to_numbers(df["close"]),
                },
                {
                    "type": "bar",
                    "name": "成交量",
                    "x": dates,
                    "y": _series_to_numbers(df["volume"]),
                },
            ],
            "layout": {
                "title": f"{symbol} {stock_name or ''} 技術圖表".strip(),
                "source": "compact-candles",
            },
        }
        return {"symbol": symbol, "name": stock_name, "range": range_name, "figure": figure}

    async def intraday(self, symbol: str) -> dict:
        symbol = symbol.upper().strip()
        stock_name, (points, metadata) = await asyncio.gather(
            self.data.stock_name(symbol),
            self.data.intraday_prices(symbol),
        )
        source = str(metadata.get("source") or "unavailable")
        if points.empty:
            return {
                "symbol": symbol,
                "name": stock_name,
                "source": source,
                "interval": "1m",
                "trade_date": None,
                "previous_close": None,
                "open": None,
                "high": None,
                "low": None,
                "latest": None,
                "change": None,
                "change_percent": None,
                "volume": None,
                "updated_at": taipei_now(),
                "points": [],
            }

        sorted_points = points.sort_values("time").reset_index(drop=True)
        first = sorted_points.iloc[0]
        latest = sorted_points.iloc[-1]
        latest_close = _float_or_none(latest.get("close"))
        previous_close = _float_or_none(metadata.get("previous_close"))
        change = (
            latest_close - previous_close
            if latest_close is not None and previous_close is not None
            else None
        )
        change_percent = (
            change / previous_close * 100
            if change is not None and previous_close not in (None, 0)
            else None
        )
        trade_time = pd.to_datetime(latest["time"])
        updated_at = metadata.get("regular_market_time")
        if not hasattr(updated_at, "isoformat"):
            updated_at = taipei_now()
        volume = _float_or_none(metadata.get("regular_market_volume"))
        if volume is None:
            volume = float(sorted_points["volume"].sum())

        return {
            "symbol": symbol,
            "name": stock_name,
            "source": source,
            "interval": "1m",
            "trade_date": trade_time.date(),
            "previous_close": previous_close,
            "open": _float_or_none(first.get("open")),
            "high": _float_or_none(sorted_points["high"].max()),
            "low": _float_or_none(sorted_points["low"].min()),
            "latest": latest_close,
            "change": round(change, 2) if change is not None else None,
            "change_percent": round(change_percent, 2) if change_percent is not None else None,
            "volume": volume,
            "updated_at": updated_at,
            "points": [
                {
                    "time": row["time"],
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row["volume"]),
                }
                for _, row in sorted_points.iterrows()
            ],
        }


def _kline_analysis(technical: dict, stop_loss: dict, trailing: dict, strategy: dict) -> dict:
    close = _float_or_none(technical.get("latest_close"))
    ma20 = _float_or_none(technical.get("ma", {}).get("ma20"))
    ma60 = _float_or_none(technical.get("ma", {}).get("ma60"))
    ma120 = _float_or_none(technical.get("ma", {}).get("ma120"))
    ma240 = _float_or_none(technical.get("ma", {}).get("ma240"))
    rsi14 = _float_or_none(technical.get("rsi", {}).get("rsi14"))
    atr_stop = _float_or_none(stop_loss.get("atr_stop"))
    take_profit = _float_or_none(trailing.get("current_take_profit_price"))
    stance = str(strategy.get("stance", "wait"))
    trend = str(technical.get("trend", "unknown"))

    support_levels = [
        _level_text("MA20", ma20),
        _level_text("MA60", ma60),
        _level_text("ATR stop", atr_stop),
    ]
    if ma120 is not None:
        support_levels.append(_level_text("MA120", ma120))
    if ma240 is not None:
        support_levels.append(_level_text("MA240", ma240))

    resistance_levels = []
    if take_profit is not None:
        resistance_levels.append(_level_text("trailing take-profit", take_profit))
    if close is not None and ma20 is not None:
        resistance_levels.append(f"Close vs MA20: {_fmt(close - ma20)}")
    if rsi14 is not None:
        resistance_levels.append(f"RSI14: {_fmt(rsi14)}")

    if stance == "prepare_entry":
        headline = "K 線偏多，等回測支撐或突破後分批，不追高。"
        strategy_notes = [
            "逢低買的前提是 MA20 或前低守住，且量能沒有失控放大。",
            "不要在急跌破 MA60 時攤平；先等止跌 K 線和法人籌碼回穩。",
            "若價格站上 MA20 且 RSI 未過熱，可用小部位試單，再用停損控風險。",
        ]
    elif stance == "hold_steady":
        headline = "K 線偏整理，等拉回不破支撐再評估。"
        strategy_notes = [
            "已有持股以 MA20/ATR 停損管理，不因短線震盪情緒性殺低。",
            "沒有持股先等回測支撐、量縮止跌，避免在區間上緣追價。",
            "若 RSI 過熱或爆量長上影，先降低加碼速度。",
        ]
    elif stance == "reduce_risk":
        headline = "K 線防守優先，破線時先降風險。"
        strategy_notes = [
            "跌破 MA60 或市場風險轉紅時，不把下跌誤判成逢低買。",
            "先保留現金與觀察名單，等重新站回 MA20/MA60 再討論進場。",
            "若已持有，依 ATR 或 MA60 停損檢查，不用情緒硬撐。",
        ]
    else:
        headline = "K 線訊號不足，先等更清楚的支撐或轉強。"
        strategy_notes = [
            "等待價格回到 MA20 之上，或跌到支撐後出現止跌訊號。",
            "沒有明確優勢時，先小部位或不交易，避免因想買而買。",
            "把下一次判斷點放在 MA20、MA60、RSI 與量能變化。",
        ]

    invalidation = [
        f"Close below MA120: {_fmt(ma120)}" if ma120 is not None else "MA120 unavailable",
        f"Close below MA240: {_fmt(ma240)}" if ma240 is not None else "MA240 unavailable",
        f"Close below MA60: {_fmt(ma60)}" if ma60 is not None else "MA60 unavailable",
        f"ATR stop: {_fmt(atr_stop)}" if atr_stop is not None else "ATR stop unavailable",
        "Market risk light turns red or key support breaks with volume.",
    ]

    return {
        "headline": headline,
        "trend": trend,
        "support_levels": support_levels,
        "resistance_levels": resistance_levels,
        "strategy_notes": strategy_notes,
        "invalidation": invalidation,
    }


def _level_text(label: str, value: float | None) -> str:
    return f"{label}: {_fmt(value)}"


def _series_to_numbers(series: pd.Series) -> list[float | None]:
    values = pd.to_numeric(series, errors="coerce")
    return [None if pd.isna(value) else float(value) for value in values]


def _apply_data_quality_score_cap(adjusted_score: float, data_sources: dict[str, str]) -> tuple[float, list[str]]:
    cap = 100.0
    notes: list[str] = []
    if not is_trusted_source(data_sources.get("fundamental"), "fundamental"):
        cap = min(cap, 49.0)
        notes.append("基本面資料不是可驗證真實來源，研究分數上限降到 49，只能觀察。")
    if _is_sample_source(data_sources.get("price")):
        cap = min(cap, 59.0)
        notes.append("價格資料不是可驗證歷史日 K，不能用技術分數判斷進場。")

    if adjusted_score > cap:
        return cap, notes
    return adjusted_score, notes


def _recommendation_for_analysis(adjusted_score: float, data_sources: dict[str, str]) -> str:
    if not is_trusted_source(data_sources.get("fundamental"), "fundamental") or _is_sample_source(data_sources.get("price")):
        return "只觀察"
    return recommendation_from_score(adjusted_score)


def _apply_data_quality_gate_guards(
    *,
    fundamental_gate: dict,
    valuation_gate: dict,
    timing_gate: dict,
    data_sources: dict[str, str],
) -> tuple[dict, dict, dict]:
    if not is_trusted_source(data_sources.get("fundamental"), "fundamental"):
        fundamental_gate = _untrusted_fundamental_gate()
        valuation_gate = _untrusted_valuation_gate()
    if _is_sample_source(data_sources.get("price")):
        timing_gate = _untrusted_timing_gate()
    return fundamental_gate, valuation_gate, timing_gate


def _untrusted_fundamental_gate() -> dict:
    return {
        "status": "unknown",
        "grade": "資料不足",
        "passed": False,
        "failed_reasons": ["基本面資料不是可驗證真實來源，不採用 EPS、PE、ROE 或營收做結論。"],
        "metrics": {
            "eps": None,
            "roe": None,
            "gross_margin": None,
            "operating_margin": None,
            "revenue_yoy": None,
            "revenue_mom": None,
            "pe_ratio": None,
            "pb_ratio": None,
        },
    }


def _untrusted_valuation_gate() -> dict:
    return {
        "status": "unknown",
        "pe_ratio": None,
        "pe_band": "資料不足",
        "sector_band": "等待真實基本面",
        "is_low_valuation": False,
        "warning": "基本面不是可驗證真實來源，不採用 PE、PB 或產業估值區間。",
    }


def _untrusted_timing_gate() -> dict:
    return {
        "status": "unknown",
        "trend": "等待真實日 K",
        "support_zone": "等待真實日 K",
        "no_chase_zone": "等待真實日 K",
        "entry_conditions": [
            "先接上 FinMind、Yahoo 或 TWSE 可驗證價格資料。",
            "沒有真實日 K 前，不使用支撐、壓力、均線或失效價。",
        ],
        "invalidation_price": None,
    }


def _untrusted_price_plan() -> dict:
    return {
        "research_price": None,
        "watch_price": None,
        "invalidation_price": None,
        "position_size_hint": "0%，價格資料不是可驗證歷史日 K；等真實日 K 後再建立研究價與失效價。",
    }


def _untrusted_stop_loss() -> dict:
    return {
        "fixed_5_percent": None,
        "fixed_8_percent": None,
        "fixed_10_percent": None,
        "atr_stop": None,
        "ma20_stop_triggered": False,
        "ma60_stop_triggered": False,
        "notes": ["價格資料不是可驗證歷史日 K，不計算停損、停利或 ATR 風險位。"],
    }


def _untrusted_trailing_take_profit(atr_multiplier: float) -> dict:
    return {
        "current_take_profit_price": None,
        "atr_multiplier": atr_multiplier,
        "estimated_return_percent": None,
        "risk_reward_ratio": None,
        "highest_price_used": None,
        "is_estimated_highest_price": False,
    }


def _untrusted_kline_analysis() -> dict:
    return {
        "headline": "價格來源不足，K 線數字暫不採用",
        "trend": "等待真實日 K",
        "support_levels": ["等待真實日 K"],
        "resistance_levels": ["等待真實日 K"],
        "strategy_notes": [
            "目前價格資料不是可驗證歷史日 K，不畫推估支撐或壓力。",
            "先確認資料來源，再討論進場條件、失效價與部位大小。",
        ],
        "invalidation": ["等待真實日 K"],
    }


def _fundamentals_for_response(
    fundamentals: dict[str, float | None],
    fundamental_source: str,
    signals: list[str],
) -> dict[str, float | list[str] | None]:
    if is_trusted_source(fundamental_source, "fundamental"):
        return {**fundamentals, "signals": signals[:4]}
    return {
        **{key: None for key in fundamentals},
        "signals": ["基本面資料不是可驗證真實來源，不顯示未驗證 EPS、PE、ROE 或營收。"],
    }


def _is_sample_source(source: str | None) -> bool:
    return not source or "sample" in source.lower()


def _source_missing_note(label: str, source: str) -> str:
    if source == "sample":
        return f"{label}仍是示範來源，本輪不納入加減分。"
    return f"{label}資料未接入，本輪不納入加減分。"


def _decision_plan(
    *,
    symbol: str,
    name: str | None,
    recommendation: str,
    adjusted_score: float,
    raw_score: float,
    score_breakdown: dict[str, float],
    technical: dict,
    institutional: dict,
    margin: dict,
    sentiment: dict,
    stop_loss: dict,
    trailing: dict,
    risk_lights: dict,
    reasons: list[str],
    risks: list[str],
    data_sources: dict[str, str],
) -> dict:
    composite_light = risk_lights.get("composite", "yellow")
    risk_indicator = risk_lights.get("risk_indicator", "yellow")
    trend = technical.get("trend", "neutral")
    price_untrusted = _is_sample_source(data_sources.get("price"))
    if price_untrusted:
        trend = "neutral"
    close = _float_or_none(technical.get("latest_close"))
    ma20 = _float_or_none(technical.get("ma", {}).get("ma20"))
    ma60 = _float_or_none(technical.get("ma", {}).get("ma60"))
    atr_stop = _float_or_none(stop_loss.get("atr_stop"))
    take_profit = _float_or_none(trailing.get("current_take_profit_price"))
    risk_reward = _float_or_none(trailing.get("risk_reward_ratio"))
    if price_untrusted:
        close = None
        ma20 = None
        ma60 = None
        atr_stop = None
        take_profit = None
        risk_reward = None
    flow_5d = _float_or_none(institutional.get("five_day_total")) or 0.0
    flow_20d = _float_or_none(institutional.get("twenty_day_total")) or 0.0
    margin_5d = _float_or_none(margin.get("five_day_change")) or 0.0
    margin_20d = _float_or_none(margin.get("twenty_day_change")) or 0.0

    bias = _decision_bias(adjusted_score, composite_light, trend)
    confidence = _decision_confidence(adjusted_score, composite_light, trend, data_sources, reasons, risks)
    action = _decision_action(adjusted_score, composite_light, risk_indicator, trend)
    research_position_size = _research_position_size(adjusted_score, composite_light, confidence)

    headline = f"{recommendation}，但先看條件是否成立"
    if bias == "bearish":
        headline = "風險優先，先保護本金"
    elif bias == "bullish":
        headline = "偏多觀察，可用條件分批驗證"

    checklist = {
        "進場條件": [
            f"總分維持 75 以上，目前 {round(adjusted_score, 1)}。",
            f"大盤綜合燈號不是紅燈，目前為 {_light_label(composite_light)}。",
            _price_condition("收盤價守在 MA20 上方", close, ma20),
            "近 5 日或 20 日法人合計轉為買超。",
            _margin_condition("融資 5 日與 20 日同步下降", margin_5d, margin_20d),
            _risk_reward_condition(risk_reward),
        ],
        "不進場條件": [
            "Market Risk Engine 或綜合燈號轉紅。",
            _break_condition("收盤價跌破 MA60", close, ma60),
            _margin_risk_condition("融資連續增加", margin_5d, margin_20d),
            "RSI14 高於 75 且沒有回測支撐，不追價。",
            "新聞或基本面資料不是可驗證真實來源時，不把結論當成完整事實。",
        ],
        "出場條件": [
            _stop_condition("跌破 ATR 停損", close, atr_stop),
            _stop_condition("跌破移動停利", close, take_profit),
            "跌破 MA60 或分數降到 40 以下時，優先降風險。",
            "重大利空新聞出現時，重新產生分析，不延用舊結論。",
        ],
    }

    scenarios = [
        {
            "name": "偏多情境",
            "condition": (
                f"收盤價站穩 MA20({_fmt(ma20)})，法人 5 日與 20 日至少一個維持買超，"
                f"綜合燈號為 {_light_label(composite_light)} 或轉綠。"
            ),
            "action": "只在條件成立時分批研究，優先用小部位驗證，不用一次押滿。",
            "invalidation": f"跌破 MA20({_fmt(ma20)}) 或風險燈號轉紅。",
        },
        {
            "name": "中性情境",
            "condition": f"分數落在 60 到 75，或價格在 MA20({_fmt(ma20)}) 附近震盪。",
            "action": "保持觀察，等待量能、法人或新聞脈絡給出更明確方向。",
            "invalidation": "連續弱於大盤、法人轉賣超，或分數跌破 60。",
        },
        {
            "name": "偏空情境",
            "condition": (
                f"跌破 MA60({_fmt(ma60)})、Market Risk Engine 轉紅，"
                f"或法人轉賣超，目前 5 日 {_fmt(flow_5d, 0)}、20 日 {_fmt(flow_20d, 0)}。"
            ),
            "action": "先避開新倉或降低研究部位，等趨勢修復後再評估。",
            "invalidation": "重新站回 MA20，法人買盤回來，且風險燈號不再是紅燈。",
        },
    ]

    next_review_triggers = [
        "價格觸及停損、移動停利或 MA60。",
        "總分跨越 75、60、40 任一門檻。",
        "Market Risk Engine 燈號改變。",
        "財報、月營收、法說會或重大新聞公布後。",
        "至少每 5 個交易日重新整理一次，不用舊資料做新決策。",
    ]

    data_quality = [
        f"價格資料來源：{data_sources.get('price', 'unknown')}",
        f"法人資料來源：{data_sources.get('institutional', 'unknown')}",
        f"融資資料來源：{data_sources.get('margin', 'unknown')}",
        f"基本面資料來源：{data_sources.get('fundamental', 'unknown')}",
        f"新聞資料來源：{data_sources.get('news', 'unknown')}",
    ]
    if not is_trusted_source(data_sources.get("fundamental"), "fundamental"):
        data_quality.append("基本面不是可驗證真實來源時，只能當觀察流程，不列為可研究依據。")
    if data_sources.get("news") not in {"finmind", "sample"}:
        data_quality.append("新聞資料未接入時，不使用情緒分數加減分。")

    return {
        "headline": headline,
        "bias": bias,
        "action": action,
        "confidence": confidence,
        "research_position_size": research_position_size,
        "score_breakdown": score_breakdown,
        "checklist": checklist,
        "scenarios": scenarios,
        "next_review_triggers": next_review_triggers,
        "data_quality": data_quality,
        "ai_snapshot_prompt": _ai_snapshot_prompt(
            symbol=symbol,
            name=name,
            adjusted_score=adjusted_score,
            raw_score=raw_score,
            recommendation=recommendation,
            technical=technical,
            institutional=institutional,
            sentiment=sentiment,
            risk_lights=risk_lights,
            stop_loss=stop_loss,
            trailing=trailing,
            margin=margin,
            reasons=reasons,
            risks=risks,
            data_quality=data_quality,
        ),
    }


def _decision_bias(adjusted_score: float, composite_light: str, trend: str) -> str:
    if adjusted_score >= 75 and composite_light != "red" and trend == "bullish":
        return "bullish"
    if adjusted_score < 40 or composite_light == "red":
        return "bearish"
    return "neutral"


def _decision_action(adjusted_score: float, composite_light: str, risk_indicator: str, trend: str) -> str:
    if composite_light == "red" or risk_indicator == "red" or adjusted_score < 40:
        return "暫停新倉或減碼，先等風險燈號與趨勢修復。"
    if adjusted_score >= 75 and trend == "bullish":
        return "列入分批研究名單，只在進場條件成立時執行。"
    if adjusted_score >= 60:
        return "保持觀察，不追價；等價格、量能與法人同步後再行動。"
    return "偏弱觀察，除非出現明確轉強訊號，否則先保留現金。"


def _decision_confidence(
    adjusted_score: float,
    composite_light: str,
    trend: str,
    data_sources: dict[str, str],
    reasons: list[str],
    risks: list[str],
) -> str:
    price_source = str(data_sources.get("price", "")).lower()
    core_untrusted = not is_trusted_source(data_sources.get("fundamental"), "fundamental") or not (
        "sample" not in price_source and any(provider in price_source for provider in ("finmind", "twse", "yahoo"))
    )
    mixed_evidence = bool(reasons and risks)
    if core_untrusted or composite_light == "red":
        return "低"
    if adjusted_score >= 75 and trend == "bullish" and composite_light == "green" and not mixed_evidence:
        return "高"
    return "中"


def _research_position_size(adjusted_score: float, composite_light: str, confidence: str) -> str:
    if composite_light == "red" or adjusted_score < 40:
        return "0%，先不建立新的研究部位。"
    if adjusted_score < 60 or confidence == "低":
        return "0-10%，只適合觀察或極小部位驗證。"
    if adjusted_score < 75 or composite_light == "yellow":
        return "10-25%，分批且保留現金。"
    return "25-40%，仍需分批，並先設定停損。"


def _strategy_judgement(
    *,
    adjusted_score: float,
    technical: dict,
    institutional: dict,
    margin: dict,
    risk_lights: dict,
) -> dict:
    composite_light = risk_lights.get("composite", "yellow")
    close = _float_or_none(technical.get("latest_close"))
    ma20 = _float_or_none(technical.get("ma", {}).get("ma20"))
    ma60 = _float_or_none(technical.get("ma", {}).get("ma60"))
    rsi14 = _float_or_none(technical.get("rsi", {}).get("rsi14"))
    osc = _float_or_none(technical.get("macd", {}).get("osc"))
    volume_ratio = _float_or_none(technical.get("volume_ratio"))
    flow_5d = _float_or_none(institutional.get("five_day_total")) or 0.0
    flow_20d = _float_or_none(institutional.get("twenty_day_total")) or 0.0
    margin_5d = _float_or_none(margin.get("five_day_change")) or 0.0
    margin_20d = _float_or_none(margin.get("twenty_day_change")) or 0.0

    market_pass = composite_light != "red"
    price_holds_ma20 = close is not None and ma20 is not None and close >= ma20
    price_holds_ma60 = close is not None and ma60 is not None and close >= ma60
    institutions_buying = flow_5d > 0 or flow_20d > 0
    margin_improving = margin_5d < 0 or margin_20d < 0
    margin_clean = margin_5d < 0 and margin_20d < 0
    overheat = bool(rsi14 is not None and rsi14 >= 75) or bool(volume_ratio is not None and volume_ratio >= 2.5)

    timing_score = adjusted_score
    timing_score += 5 if market_pass else -12
    timing_score += 5 if price_holds_ma20 else -8
    timing_score += 4 if price_holds_ma60 else -10
    timing_score += 4 if institutions_buying else -3
    timing_score += 6 if margin_clean else 3 if margin_improving else -4
    timing_score += 2 if osc is not None and osc > 0 else 0
    timing_score -= 8 if overheat else 0
    timing_score = round(max(0, min(100, timing_score)), 2)

    if not market_pass or adjusted_score < 40 or not price_holds_ma60:
        stance = "reduce_risk"
        headline = "先守風險，不急著進場"
        action = "大盤或中期趨勢還沒站穩，先保留現金，等重新站回 MA60 且風險燈號改善。"
    elif timing_score >= 75 and price_holds_ma20 and institutions_buying and margin_improving and not overheat:
        stance = "prepare_entry"
        headline = "接近可研究進場"
        action = "條件已接近進場區，適合用小部位分批驗證，並把 MA20/MA60 當成失效線。"
    elif timing_score >= 60 and price_holds_ma20:
        stance = "hold_steady"
        headline = "可以守穩觀察"
        action = "價格仍守在短線支撐上，先持有或觀察，不追高，等籌碼或量價再確認。"
    else:
        stance = "wait"
        headline = "等待更乾淨的訊號"
        action = "目前還不是乾淨進場點，等融資下降、法人轉買或收盤重新站穩 MA20。"

    checks = [
        _strategy_check("大盤風險", "pass" if market_pass else "fail", f"綜合燈號為 {_light_label(composite_light)}。"),
        _strategy_check(
            "守穩 MA20",
            _pass_watch_fail(price_holds_ma20, close is not None and ma20 is not None),
            _price_condition("收盤價守在 MA20 上方", close, ma20),
        ),
        _strategy_check(
            "守穩 MA60",
            _pass_watch_fail(price_holds_ma60, close is not None and ma60 is not None),
            _price_condition("收盤價守在 MA60 上方", close, ma60),
        ),
        _strategy_check(
            "法人籌碼",
            "pass" if institutions_buying else "watch",
            f"法人 5 日 {_fmt(flow_5d, 0)}，20 日 {_fmt(flow_20d, 0)}。",
        ),
        _strategy_check(
            "融資下降",
            "pass" if margin_clean else "watch" if margin_improving else "fail",
            f"融資 5 日 {_fmt(margin_5d, 0)}，20 日 {_fmt(margin_20d, 0)}。",
        ),
        _strategy_check(
            "避免過熱",
            "fail" if overheat else "pass",
            f"RSI14 {_fmt(rsi14)}，量比 {_fmt(volume_ratio)}。",
        ),
    ]

    return {
        "stance": stance,
        "headline": headline,
        "action": action,
        "timing_score": timing_score,
        "chip_cleanliness": _chip_cleanliness(institutions_buying, margin_clean, margin_improving),
        "margin_trend": _margin_trend_label(margin_5d, margin_20d),
        "market_guard": "大盤風險可控" if market_pass else "大盤風險偏高，先降低進場慾望",
        "checks": checks,
        "entry_triggers": [
            "收盤價守住 MA20，且隔日不爆量跌破。",
            "法人 5 日或 20 日合計維持買超。",
            "融資餘額連續下降或至少不再增加。",
            "大盤綜合燈號維持黃燈以上。",
        ],
        "defensive_triggers": [
            "跌破 MA60 或 Market Risk Engine 轉紅。",
            "融資連續增加但股價不漲，代表籌碼變重。",
            "RSI 過熱後爆量長黑，避免追價。",
        ],
    }


def _strategy_check(label: str, status: str, detail: str) -> dict:
    return {"label": label, "status": status, "detail": detail}


def _pass_watch_fail(condition: bool, has_data: bool) -> str:
    if condition:
        return "pass"
    if has_data:
        return "fail"
    return "watch"


def _chip_cleanliness(institutions_buying: bool, margin_clean: bool, margin_improving: bool) -> str:
    if institutions_buying and margin_clean:
        return "籌碼乾淨度佳：法人偏買，融資同步下降。"
    if margin_clean or margin_improving:
        return "籌碼正在轉乾淨：融資下降，但仍需法人或價格確認。"
    if institutions_buying:
        return "法人支撐仍在，但融資尚未明顯下降。"
    return "籌碼仍偏重，先等融資或法人訊號改善。"


def _margin_trend_label(five_day_change: float, twenty_day_change: float) -> str:
    if five_day_change < 0 and twenty_day_change < 0:
        return f"融資 5 日減少 {abs(five_day_change):,.0f}，20 日減少 {abs(twenty_day_change):,.0f}。"
    if five_day_change < 0 or twenty_day_change < 0:
        return f"融資部分改善：5 日 {_fmt(five_day_change, 0)}，20 日 {_fmt(twenty_day_change, 0)}。"
    if five_day_change > 0 and twenty_day_change > 0:
        return f"融資增加：5 日 +{_fmt(five_day_change, 0)}，20 日 +{_fmt(twenty_day_change, 0)}。"
    return "融資變化中性，還沒有明顯下降訊號。"


def _ai_snapshot_prompt(
    *,
    symbol: str,
    name: str | None,
    adjusted_score: float,
    raw_score: float,
    recommendation: str,
    technical: dict,
    institutional: dict,
    sentiment: dict,
    risk_lights: dict,
    stop_loss: dict,
    trailing: dict,
    margin: dict,
    reasons: list[str],
    risks: list[str],
    data_quality: list[str],
) -> str:
    display_name = f"{symbol} {name}" if name else symbol
    lines = [
        "請用保守、可驗證、不可保證報酬的方式分析以下股票快照。",
        f"標的：{display_name}",
        f"總分：{round(adjusted_score, 1)} / 100，原始分數：{round(raw_score, 1)}，研究狀態：{recommendation}",
        (
            "風險燈號："
            f"大盤 {_light_label(risk_lights.get('market_trend'))}，"
            f"技術 {_light_label(risk_lights.get('technical'))}，"
            f"風險 {_light_label(risk_lights.get('risk_indicator'))}，"
            f"綜合 {_light_label(risk_lights.get('composite'))}"
        ),
        (
            "技術："
            f"收盤 {_fmt(technical.get('latest_close'))}，"
            f"MA20 {_fmt(technical.get('ma', {}).get('ma20'))}，"
            f"MA60 {_fmt(technical.get('ma', {}).get('ma60'))}，"
            f"RSI14 {_fmt(technical.get('rsi', {}).get('rsi14'))}"
        ),
        (
            "法人："
            f"5日 {_fmt(institutional.get('five_day_total'), 0)}，"
            f"20日 {_fmt(institutional.get('twenty_day_total'), 0)}，"
            f"60日 {_fmt(institutional.get('sixty_day_total'), 0)}"
        ),
        (
            "融資籌碼："
            f"5日變化 {_fmt(margin.get('five_day_change'), 0)}，"
            f"20日變化 {_fmt(margin.get('twenty_day_change'), 0)}，"
            f"券資比 {_fmt(margin.get('short_margin_ratio'))}%"
        ),
        (
            "停損停利："
            f"ATR停損 {_fmt(stop_loss.get('atr_stop'))}，"
            f"移動停利 {_fmt(trailing.get('current_take_profit_price'))}"
        ),
        f"新聞情緒：{sentiment.get('label')}，摘要：{sentiment.get('summary')}",
        f"主要理由：{'; '.join(reasons[:4])}",
        f"主要風險：{'; '.join(risks[:4]) if risks else '目前未列出重大單一風險'}",
        f"資料品質：{'; '.join(data_quality)}",
        "請輸出：1. 市場概況 2. 偏多/中性/偏空三情境 3. 進場條件 4. 不進場條件 5. 停損停利與重新檢查時間。",
    ]
    return "\n".join(lines)


def _price_condition(label: str, close: float | None, reference: float | None) -> str:
    if close is None or reference is None:
        return f"{label}，但目前資料不足需重新確認。"
    status = "成立" if close >= reference else "未成立"
    return f"{label}：{status}，收盤 {_fmt(close)}，參考價 {_fmt(reference)}。"


def _margin_condition(label: str, five_day_change: float, twenty_day_change: float) -> str:
    status = "成立" if five_day_change < 0 and twenty_day_change < 0 else "未完全成立"
    return f"{label}：{status}，5 日 {_fmt(five_day_change, 0)}，20 日 {_fmt(twenty_day_change, 0)}。"


def _margin_risk_condition(label: str, five_day_change: float, twenty_day_change: float) -> str:
    status = "成立" if five_day_change > 0 and twenty_day_change > 0 else "未成立"
    return f"{label}：{status}，5 日 {_fmt(five_day_change, 0)}，20 日 {_fmt(twenty_day_change, 0)}。"


def _break_condition(label: str, close: float | None, reference: float | None) -> str:
    if close is None or reference is None:
        return f"{label}，但目前資料不足需重新確認。"
    status = "成立" if close < reference else "未成立"
    return f"{label}：{status}，收盤 {_fmt(close)}，參考價 {_fmt(reference)}。"


def _stop_condition(label: str, close: float | None, reference: float | None) -> str:
    if close is None or reference is None:
        return f"{label}，但目前資料不足需重新確認。"
    status = "已觸發" if close <= reference else "未觸發"
    return f"{label}：{status}，收盤 {_fmt(close)}，觸發價 {_fmt(reference)}。"


def _risk_reward_condition(value: float | None) -> str:
    if value is None:
        return "風險報酬比尚未可用，輸入買進價後再確認。"
    status = "足夠" if value >= 1.5 else "不足"
    return f"風險報酬比至少 1.5，目前 {format(value, '.2f')}，{status}。"


def _light_label(light: object) -> str:
    return {"green": "綠燈", "yellow": "黃燈", "red": "紅燈"}.get(str(light), "未知")


def _fmt(value: object, digits: int = 2) -> str:
    numeric = _float_or_none(value)
    if numeric is None:
        return "-"
    return format(numeric, f".{digits}f")


def _stop_loss(entry_price: float, technical: dict, close: float) -> dict:
    atr = technical.get("atr14")
    ma20 = technical["ma"].get("ma20")
    ma60 = technical["ma"].get("ma60")
    notes = ["固定百分比、ATR、均線停損需依持倉週期擇一執行，避免任意移動停損。"]
    return {
        "fixed_5_percent": round(entry_price * 0.95, 2),
        "fixed_8_percent": round(entry_price * 0.92, 2),
        "fixed_10_percent": round(entry_price * 0.90, 2),
        "atr_stop": round(entry_price - 2 * atr, 2) if atr is not None else None,
        "ma20_stop_triggered": bool(ma20 is not None and close < ma20),
        "ma60_stop_triggered": bool(ma60 is not None and close < ma60),
        "notes": notes,
    }


def _trailing_take_profit(indicators, entry_price: float, highest_price: float | None, atr_multiplier: float) -> dict:
    latest = indicators.iloc[-1]
    atr = latest.get("atr14")
    estimated = highest_price is None
    latest_high = float(latest["high"])
    if highest_price is not None:
        high_used = max(float(highest_price), latest_high, entry_price)
    else:
        high_used = max(float(indicators.tail(60)["high"].max()), latest_high, entry_price)
    take_profit = round(high_used - atr_multiplier * float(atr), 2) if atr == atr else None
    estimated_return = (
        round((take_profit / entry_price - 1) * 100, 2)
        if take_profit is not None and entry_price
        else None
    )
    downside = entry_price - take_profit if take_profit is not None else None
    upside = high_used - entry_price
    risk_reward = round(upside / abs(downside), 2) if downside and downside != 0 else None
    return {
        "current_take_profit_price": take_profit,
        "atr_multiplier": atr_multiplier,
        "estimated_return_percent": estimated_return,
        "risk_reward_ratio": risk_reward,
        "highest_price_used": round(high_used, 2),
        "is_estimated_highest_price": estimated,
    }


def _float_or_none(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


async def _with_timeout(coro, fallback, timeout_seconds: float):
    try:
        return await asyncio.wait_for(coro, timeout=timeout_seconds)
    except Exception:
        return fallback


def _remaining_timeout(deadline: float) -> float:
    return max(0.03, deadline - monotonic())


def _source_timeout_seconds(data_budget: float, explicit_data_budget: bool) -> float:
    if not explicit_data_budget or data_budget <= 1.0:
        return max(0.15, min(0.45, data_budget * 0.7))
    return max(0.45, min(9.0, data_budget * 0.95))


def _fallback_stock_profile(symbol: str) -> dict[str, str | None]:
    name = sample_data.stock_name(symbol)
    return {"name": name, "industry": resolve_industry(symbol, name, None)}


def _fallback_prices(symbol: str) -> tuple[pd.DataFrame, str]:
    return sample_data.make_price_history(symbol, years=2), "sample"


def _fallback_market_risk() -> dict:
    return {
        "status": "市場資料逾時",
        "score": 50.0,
        "lights": {
            "market_trend": "yellow",
            "institutional_flow": "yellow",
            "technical": "yellow",
            "risk_indicator": "yellow",
            "composite": "yellow",
            "table": [
                {"item": "大盤趨勢", "status": "🟡"},
                {"item": "法人動向", "status": "🟡"},
                {"item": "技術面", "status": "🟡"},
                {"item": "風險指標", "status": "🟡"},
                {"item": "綜合評價", "status": "🟡"},
            ],
        },
        "indicators": {},
        "reasons": ["市場風險資料讀取逾時，本輪先用中性燈號，避免慢資料源卡住畫面。"],
        "generated_at": taipei_now(),
        "market_date": taipei_today(),
        "refresh": _fallback_refresh_info(),
    }


def _fallback_sentiment(news: list[dict]) -> dict:
    headlines = [str(item.get("title", "")) for item in news if item.get("title")]
    return {
        "score": 0.0,
        "label": "neutral",
        "summary": "新聞情緒分析逾時，本輪不納入情緒加減分。",
        "headlines": headlines[:5],
        "model": None,
        "error": "timeout",
    }


def _fallback_refresh_info() -> dict:
    refresh = market_refresh_clock()
    return {
        **refresh,
        "message": f"{refresh['message']} 市場風險資料本輪逾時，請稍後重整確認。",
    }
