from __future__ import annotations

import asyncio
from typing import Any

from app.services.analysis import AnalysisService
from app.services.calendar import taipei_now
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

SECTOR_MAP = {
    "0050": "台股大型權值 ETF",
    "0056": "台股高股息 ETF",
    "00878": "台股 ESG 高股息 ETF",
    "2330": "半導體晶圓代工",
    "2317": "電子代工與 AI 伺服器",
    "2454": "IC 設計",
    "2308": "電源管理與工業自動化",
    "2382": "AI 伺服器與電子代工",
    "2412": "電信服務",
    "3711": "半導體封測控股",
    "2603": "航運",
    "2609": "航運",
    "2615": "航運",
    "2881": "金融控股",
    "2882": "金融控股",
    "2891": "金融控股",
    "3008": "光學鏡頭",
    "3034": "高速傳輸與網通晶片",
    "3443": "ASIC 與 AI 晶片",
    "3661": "半導體 IP",
    "2357": "品牌電腦與伺服器",
    "2379": "IC 設計與高速傳輸",
    "3231": "AI 伺服器與雲端設備",
    "5871": "租賃金融",
    "1216": "食品與內需",
    "1303": "塑化",
    "2002": "鋼鐵",
    "1101": "水泥",
}

SECTOR_THEMES = {
    "台股大型權值 ETF": "跟隨台股大型權值股與大盤資金風向。",
    "台股高股息 ETF": "重視配息穩定度、成分股品質與利率環境。",
    "台股 ESG 高股息 ETF": "重視配息穩定度、成分股品質與大型電子金融權重。",
    "半導體晶圓代工": "受 AI、高效能運算、先進製程與費半情緒牽動。",
    "電子代工與 AI 伺服器": "受 AI 伺服器、雲端資本支出與美元匯率影響。",
    "IC 設計": "受手機、AI 邊緣運算與消費電子週期影響。",
    "AI 伺服器與電子代工": "受 AI 伺服器、雲端資本支出與美元匯率影響。",
    "電源管理與工業自動化": "受 AI 電力、電動車、工控與能源效率需求牽動。",
    "半導體封測控股": "受先進封裝、測試需求與半導體庫存循環影響。",
    "電信服務": "防禦性較高，重點在現金流、股利與用戶成長。",
    "航運": "景氣循環強，重點在運價、供需與油價成本。",
    "金融控股": "受殖利率、信用循環、股債市表現與淨值評價影響。",
    "光學鏡頭": "受手機規格升級、車用鏡頭與客戶拉貨節奏影響。",
    "高速傳輸與網通晶片": "受 AI 伺服器、交換器、光通訊與高速傳輸規格升級牽動。",
    "ASIC 與 AI 晶片": "受客製化 AI 晶片、先進製程與雲端需求影響。",
    "半導體 IP": "受先進製程設計案、授權金與半導體投片循環影響。",
    "品牌電腦與伺服器": "受 PC 週期、AI PC、伺服器與通路庫存影響。",
    "IC 設計與高速傳輸": "受 PC、伺服器、USB/PCIe 規格升級與庫存循環影響。",
    "AI 伺服器與雲端設備": "受 AI 伺服器建置、雲端資本支出與供應鏈拉貨節奏影響。",
    "租賃金融": "受利率、企業投資循環與信用風險影響。",
    "食品與內需": "受內需消費、原物料成本與通路價格影響。",
    "塑化": "受油價、利差、需求復甦與中國供給影響。",
    "鋼鐵": "受景氣循環、原料成本、基建與需求復甦影響。",
    "水泥": "受基建需求、能源成本與區域價格影響。",
}

TECH_SECTORS = {
    "半導體晶圓代工",
    "電子代工與 AI 伺服器",
    "IC 設計",
    "AI 伺服器與電子代工",
    "電源管理與工業自動化",
    "半導體封測控股",
    "高速傳輸與網通晶片",
    "ASIC 與 AI 晶片",
    "半導體 IP",
    "品牌電腦與伺服器",
    "IC 設計與高速傳輸",
    "AI 伺服器與雲端設備",
    "光學鏡頭",
}


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
        market = await self.risk_engine.evaluate()
        analyses, failed = await self._analyze_universe(symbols)
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
                "先以單檔綜合分數為基底，納入技術、法人、基本面與新聞情緒。",
                "再用當日市場風險燈號、Nasdaq/費半方向與產業屬性做加減分。",
                "同步檢查是否守穩 MA20/MA60、法人籌碼是否轉買、融資是否下降，避免新聞熱了才追價。",
                "最後只保留分數達標或排序較高的研究候選股，並列出利多因素、進場時機與風險。",
            ],
            "watch_notes": notes,
            "disclaimer": "AI 盤勢選股僅供研究與篩選，不構成投資建議、保證獲利或下單指令。",
        }

    async def _analyze_universe(self, symbols: list[str]) -> tuple[list[dict[str, Any]], list[str]]:
        semaphore = asyncio.Semaphore(4)

        async def analyze_one(symbol: str) -> tuple[str, dict[str, Any] | None]:
            try:
                async with semaphore:
                    return symbol, await self.analysis_service.analyze(symbol)
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
    industry = SECTOR_MAP.get(symbol, "未分類產業")
    positive_factors: list[dict[str, str]] = []
    risk_factors: list[dict[str, str]] = []

    score = float(analysis["adjusted_score"])
    score += _collect_market_factors(market, industry, positive_factors, risk_factors)
    score += _collect_technical_factors(analysis["technical"], positive_factors, risk_factors)
    score += _collect_institutional_factors(analysis["institutional"], positive_factors, risk_factors)
    score += _collect_strategy_factors(analysis["strategy_judgement"], positive_factors, risk_factors)
    score += _collect_fundamental_factors(analysis["fundamental"], industry, positive_factors, risk_factors)
    score += _collect_sentiment_factors(analysis["sentiment"], positive_factors, risk_factors)
    score = round(max(0, min(100, score)), 2)

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
        "recommendation": analysis["recommendation"],
        "selection_score": score,
        "adjusted_score": analysis["adjusted_score"],
        "bias": analysis["decision_plan"]["bias"],
        "confidence": analysis["decision_plan"]["confidence"],
        "strategy_judgement": analysis["strategy_judgement"],
        "thesis": _thesis(symbol, analysis.get("name"), industry, score, positive_factors, market),
        "bullish_factors": positive_factors[:8],
        "risk_factors": risk_factors[:6],
        "score_breakdown": analysis["decision_plan"]["score_breakdown"],
        "data_quality": analysis["decision_plan"]["data_quality"],
        "source_notes": analysis["decision_plan"]["next_review_triggers"][:4],
    }


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
        positive.append(_factor("market", "盤勢", f"大盤狀態為{market['status']}，適合以條件篩選而非全面追價。", "neutral"))

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
        positive.append(_factor("institutional", "法人", f"三大法人 5 日與 20 日合計偏買超，20 日合計約 {flow_20d:,.0f}。"))
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
    if industry == "未分類產業":
        risks.append(_factor("industry", "產業", "尚未建立產業對照，產業面需人工補充確認。", "neutral"))
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
