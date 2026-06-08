from __future__ import annotations

from datetime import UTC, datetime

import numpy as np

from app.services.sample_data import make_price_history


class MarketRiskEngine:
    async def evaluate(self) -> dict:
        indicators = await self._load_indicators()
        score = 50.0
        reasons: list[str] = []

        if indicators["vix"] is not None:
            if indicators["vix"] >= 28:
                score -= 20
                reasons.append("VIX 高於 28，市場恐慌升溫。")
            elif indicators["vix"] <= 16:
                score += 8
                reasons.append("VIX 偏低，外部風險較平穩。")
        if indicators["us10y"] is not None:
            if indicators["us10y"] >= 4.6:
                score -= 10
                reasons.append("美國 10 年債殖利率偏高，評價壓力增加。")
            elif indicators["us10y"] <= 3.8:
                score += 4
        if indicators["nasdaq_change_5d"] is not None:
            if indicators["nasdaq_change_5d"] > 1:
                score += 8
                reasons.append("Nasdaq 近 5 日偏強，有利科技股情緒。")
            elif indicators["nasdaq_change_5d"] < -2:
                score -= 10
                reasons.append("Nasdaq 近 5 日轉弱，科技股風險升高。")
        if indicators["sox_change_5d"] is not None:
            if indicators["sox_change_5d"] > 1:
                score += 8
                reasons.append("費半指數偏強，半導體族群情緒正向。")
            elif indicators["sox_change_5d"] < -2:
                score -= 12
                reasons.append("費半指數轉弱，台股權值電子需保守。")
        if indicators["usd_twd_change_5d"] is not None and indicators["usd_twd_change_5d"] > 0.8:
            score -= 6
            reasons.append("美元兌台幣短線升值，外資匯出壓力增加。")

        score = max(0, min(100, score))
        risk_light = "red" if score < 40 else "yellow" if score < 65 else "green"
        market_light = "green" if indicators.get("taiex_change_20d", 0) > 2 else "yellow"
        technical_light = "green" if indicators.get("taiex_change_20d", 0) > 0 else "yellow"
        composite = _composite([market_light, "yellow", technical_light, risk_light])
        status = _status_from_score(score)
        if not reasons:
            reasons.append("主要風險指標維持中性。")

        lights = {
            "market_trend": market_light,
            "institutional_flow": "yellow",
            "technical": technical_light,
            "risk_indicator": risk_light,
            "composite": composite,
            "table": [
                {"item": "大盤趨勢", "status": _emoji(market_light)},
                {"item": "法人動向", "status": _emoji("yellow")},
                {"item": "技術面", "status": _emoji(technical_light)},
                {"item": "風險指標", "status": _emoji(risk_light)},
                {"item": "綜合評價", "status": _emoji(composite)},
            ],
        }
        return {
            "status": status,
            "score": round(score, 2),
            "lights": lights,
            "indicators": indicators,
            "reasons": reasons,
            "generated_at": datetime.now(UTC),
        }

    async def _load_indicators(self) -> dict[str, float | None]:
        # Live macro/index APIs vary by account and market. The deterministic fallback keeps the
        # engine available for local development and tests while preserving the final interface.
        taiex = make_price_history("TAIEX", years=1)
        sox = make_price_history("SOX", years=1)
        nasdaq = make_price_history("NASDAQ", years=1)

        return {
            "usd_twd": 32.25,
            "usd_twd_change_5d": 0.35,
            "us10y": 4.18,
            "vix": 18.6,
            "sox_change_5d": _pct_change(sox["close"].tail(6)),
            "nasdaq_change_5d": _pct_change(nasdaq["close"].tail(6)),
            "sp500_change_5d": 0.55,
            "us_futures_change": 0.15,
            "taiex_change_20d": _pct_change(taiex["close"].tail(21)),
        }


def _pct_change(values) -> float:
    if len(values) < 2:
        return 0.0
    return round((float(values.iloc[-1]) / float(values.iloc[0]) - 1) * 100, 2)


def _status_from_score(score: float) -> str:
    if score >= 80:
        return "極度樂觀"
    if score >= 65:
        return "偏多"
    if score >= 45:
        return "中性"
    if score >= 25:
        return "偏空"
    return "極度悲觀"


def _composite(lights: list[str]) -> str:
    values = {"green": 1, "yellow": 0, "red": -1}
    avg = np.mean([values[item] for item in lights])
    if avg > 0.35:
        return "green"
    if avg < -0.35:
        return "red"
    return "yellow"


def _emoji(light: str) -> str:
    return {"green": "🟢", "yellow": "🟡", "red": "🔴"}[light]
