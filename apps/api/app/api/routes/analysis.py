import asyncio
from copy import deepcopy
from threading import Lock
from time import monotonic

from fastapi import APIRouter, Query

from app.core.config import get_settings
from app.schemas import AnalysisResponse, ChartResponse, IntradayResponse
from app.services import sample_data
from app.services.analysis import AnalysisService
from app.services.calendar import market_refresh_clock, taipei_now, taipei_today
from app.services.industry import resolve_industry
from app.services.source_quality import is_trusted_source

router = APIRouter(tags=["stocks"])
_CACHE_LOCK = Lock()
_ANALYSIS_CACHE: dict[str, tuple[float, dict]] = {}
_ANALYSIS_INFLIGHT: dict[tuple[int, str], asyncio.Task] = {}


@router.get("/stocks/{symbol}/analysis", response_model=AnalysisResponse)
async def analyze_stock(
    symbol: str,
    entry_price: float | None = Query(default=None, gt=0),
    highest_price: float | None = Query(default=None, gt=0),
    atr_multiplier: float = Query(default=2.0, gt=0, le=5),
    wait: bool = Query(default=False),
) -> dict:
    return await cached_analyze_stock(symbol, entry_price, highest_price, atr_multiplier, wait=wait)


@router.get("/stocks/{symbol}/chart", response_model=ChartResponse)
async def stock_chart(symbol: str, range: str = Query(default="1y", pattern="^(1y|3y|5y)$")) -> dict:
    return await AnalysisService().chart(symbol, range)


@router.get("/stocks/{symbol}/intraday", response_model=IntradayResponse)
async def stock_intraday(symbol: str) -> dict:
    return await AnalysisService().intraday(symbol)


async def cached_analyze_stock(
    symbol: str,
    entry_price: float | None = None,
    highest_price: float | None = None,
    atr_multiplier: float = 2.0,
    wait: bool = False,
) -> dict:
    settings = get_settings()
    ttl = max(0, settings.analysis_cache_ttl_seconds)
    if ttl <= 0:
        timeout = settings.analysis_wait_timeout_seconds if wait else settings.analysis_background_timeout_seconds
        return await AnalysisService().analyze(
            symbol,
            entry_price,
            highest_price,
            atr_multiplier,
            data_timeout_seconds=timeout if wait else None,
        )

    key = _analysis_cache_key(symbol, entry_price, highest_price, atr_multiplier)
    now = monotonic()
    with _CACHE_LOCK:
        cached = _ANALYSIS_CACHE.get(key)
        if cached is not None and now < cached[0]:
            cached_result = cached[1]
            if not wait or _analysis_has_core_sources(cached_result):
                return deepcopy(cached_result)

        loop = asyncio.get_running_loop()
        task_key = (id(loop), key)
        task = _ANALYSIS_INFLIGHT.get(task_key)
        if task is None or task.done():
            data_timeout_seconds = (
                settings.analysis_wait_timeout_seconds if wait else settings.analysis_background_timeout_seconds
            )
            task = loop.create_task(
                _analyze_and_cache(
                    key,
                    symbol,
                    entry_price,
                    highest_price,
                    atr_multiplier,
                    ttl,
                    data_timeout_seconds,
                )
            )
            _ANALYSIS_INFLIGHT[task_key] = task

    try:
        timeout = settings.analysis_wait_timeout_seconds if wait else settings.analysis_response_timeout_seconds
        result = await asyncio.wait_for(asyncio.shield(task), timeout=max(0.1, timeout))
        return deepcopy(result)
    except Exception:
        return _fast_pending_analysis(symbol, atr_multiplier)


async def warm_analysis_cache(symbols: tuple[str, ...] = ("2330", "2317", "2454")) -> None:
    await asyncio.gather(*(cached_analyze_stock(symbol) for symbol in symbols), return_exceptions=True)


def _analysis_cache_key(
    symbol: str,
    entry_price: float | None,
    highest_price: float | None,
    atr_multiplier: float,
) -> str:
    return "|".join(
        [
            symbol.upper().strip(),
            str(entry_price or ""),
            str(highest_price or ""),
            format(atr_multiplier, ".4f"),
        ]
    )


async def _analyze_and_cache(
    key: str,
    symbol: str,
    entry_price: float | None,
    highest_price: float | None,
    atr_multiplier: float,
    ttl: int,
    data_timeout_seconds: float,
) -> dict:
    task_key = (id(asyncio.get_running_loop()), key)
    try:
        result = await AnalysisService().analyze(
            symbol,
            entry_price,
            highest_price,
            atr_multiplier,
            data_timeout_seconds=data_timeout_seconds,
        )
        with _CACHE_LOCK:
            _ANALYSIS_CACHE[key] = (monotonic() + ttl, deepcopy(result))
        return result
    finally:
        with _CACHE_LOCK:
            if _ANALYSIS_INFLIGHT.get(task_key) is asyncio.current_task():
                _ANALYSIS_INFLIGHT.pop(task_key, None)

def _analysis_has_core_sources(result: dict) -> bool:
    sources = result.get("data_sources") or {}
    return all(
        is_trusted_source(sources.get(key), key)
        for key in ("price", "fundamental", "institutional", "margin")
    )


def _fast_pending_analysis(symbol: str, atr_multiplier: float) -> dict:
    normalized_symbol = symbol.upper().strip()
    name = sample_data.stock_name(normalized_symbol)
    industry = resolve_industry(normalized_symbol, name, None)
    refresh = market_refresh_clock()
    lights = {
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
    }
    data_sources = {
        "price": "unavailable",
        "institutional": "unavailable",
        "margin": "unavailable",
        "fundamental": "unavailable",
        "shareholding": "unavailable",
        "news": "unavailable",
    }
    return {
        "symbol": normalized_symbol,
        "name": name,
        "industry": industry,
        "analysis_date": taipei_today(),
        "generated_at": taipei_now(),
        "refresh": {
            **refresh,
            "message": f"{refresh['message']} 新股票資料仍在背景同步，畫面先回傳保守摘要。",
        },
        "data_sources": data_sources,
        "raw_score": 0.0,
        "adjusted_score": 0.0,
        "recommendation": "資料同步中",
        "reasons": ["新股票資料仍在背景同步，先回傳保守摘要以避免畫面卡住。"],
        "risks": ["資料尚未完成同步，不採用價格、基本面、籌碼或新聞做研究結論。"],
        "technical": {
            "latest_close": 0.0,
            "ma": {f"ma{window}": None for window in [5, 10, 20, 60, 120, 240]},
            "rsi": {"rsi6": None, "rsi14": None},
            "kd": {"k": None, "d": None},
            "macd": {"dif": None, "macd": None, "osc": None},
            "bollinger": {"upper": None, "middle": None, "lower": None, "width": None},
            "atr14": None,
            "volume_ratio": None,
            "trend": "insufficient_data",
            "signals": ["資料同步中"],
        },
        "institutional": {
            "five_day_total": 0.0,
            "twenty_day_total": 0.0,
            "sixty_day_total": 0.0,
            "foreign_trend": "unknown",
            "investment_trust_trend": "unknown",
            "dealer_trend": "unknown",
            "signals": ["籌碼資料同步中"],
        },
        "margin": {
            "latest_balance": None,
            "five_day_change": 0.0,
            "five_day_change_pct": None,
            "twenty_day_change": 0.0,
            "twenty_day_change_pct": None,
            "short_margin_ratio": None,
            "status": "unknown",
            "signals": ["信用交易資料同步中"],
        },
        "fundamental": {
            "eps": None,
            "roe": None,
            "gross_margin": None,
            "operating_margin": None,
            "pe_ratio": None,
            "pb_ratio": None,
            "revenue_yoy": None,
            "revenue_mom": None,
            "signals": ["基本面資料同步中"],
        },
        "sentiment": {
            "score": 0.0,
            "label": "neutral",
            "summary": "新聞資料同步中，本輪不納入情緒判斷。",
            "headlines": [],
            "model": None,
            "error": "pending",
        },
        "stop_loss": {
            "fixed_5_percent": None,
            "fixed_8_percent": None,
            "fixed_10_percent": None,
            "atr_stop": None,
            "ma20_stop_triggered": False,
            "ma60_stop_triggered": False,
            "notes": ["資料同步完成前不計算停損價。"],
        },
        "trailing_take_profit": {
            "current_take_profit_price": None,
            "atr_multiplier": atr_multiplier,
            "estimated_return_percent": None,
            "risk_reward_ratio": None,
            "highest_price_used": None,
            "is_estimated_highest_price": False,
        },
        "risk_lights": lights,
        "decision_plan": {
            "headline": "先等資料同步完成",
            "bias": "neutral",
            "action": "暫不做研究結論，等待背景資料同步後自動更新或手動重新整理。",
            "confidence": "低",
            "research_position_size": "0%，資料未完成前不建立研究部位。",
            "score_breakdown": {
                "technical": 0.0,
                "institutional": 0.0,
                "margin": 0.0,
                "fundamental": 0.0,
                "sentiment": 0.0,
                "market_risk_adjustment": 0.0,
            },
            "checklist": {
                "可以研究": [],
                "先等待": ["等待價格、基本面與籌碼資料同步完成。"],
                "排除條件": ["資料未完成同步前，不用這份摘要判斷買點。"],
            },
            "scenarios": [
                {
                    "name": "資料完成同步",
                    "condition": "背景分析寫入快取或重新整理後看到真實來源",
                    "action": "再看今天該做什麼、支撐壓力與失效條件",
                    "invalidation": "資料來源仍為未接入時維持觀察",
                }
            ],
            "next_review_triggers": ["1-2 秒後自動補抓或手動按重新整理。"],
            "data_quality": ["目前是快速保守摘要，真實資料尚未完成同步。"],
            "ai_snapshot_prompt": "資料同步中，暫不產生研究快照。",
        },
        "research_decision": {
            "stance": "watch",
            "horizon": "等待資料",
            "confidence": "低",
            "summary": "資料同步中，暫時不能判斷該觀察、等便宜或排除。",
            "next_action": "等待自動補抓完成，或稍後按重新整理。",
            "do_not_chase_reason": "資料尚未完成同步，不追價、不下研究結論。",
            "blockers": ["價格、基本面、籌碼與新聞尚未完成同步。"],
            "review_triggers": ["資料來源變成 TWSE、FinMind、Yahoo 或其他可信來源。"],
        },
        "fundamental_gate": {
            "status": "unknown",
            "grade": "等待資料",
            "passed": False,
            "failed_reasons": ["基本面同步中"],
            "metrics": {},
        },
        "valuation_gate": {
            "status": "unknown",
            "pe_ratio": None,
            "pe_band": "等待資料",
            "sector_band": "等待資料",
            "is_low_valuation": False,
            "warning": "估值資料同步中",
        },
        "timing_gate": {
            "status": "unknown",
            "trend": "等待資料",
            "support_zone": "等待資料",
            "no_chase_zone": "資料同步前不追價",
            "entry_conditions": ["等待真實價格資料"],
            "invalidation_price": None,
        },
        "price_plan": {
            "research_price": None,
            "watch_price": None,
            "invalidation_price": None,
            "position_size_hint": "0%，資料未完成前不建立研究部位。",
        },
        "strategy_judgement": {
            "stance": "wait",
            "headline": "等待資料同步",
            "action": "先不要做買賣判斷。",
            "timing_score": 0.0,
            "chip_cleanliness": "等待資料",
            "margin_trend": "等待資料",
            "market_guard": "等待資料",
            "checks": [
                {"label": "資料同步", "status": "watch", "detail": "背景分析尚未完成。"}
            ],
            "entry_triggers": ["等待資料同步完成"],
            "defensive_triggers": ["資料未完成前不追價"],
        },
        "breakout_potential": {
            "status": "data_limited",
            "label": "資料不足",
            "score": 0.0,
            "confidence": "低",
            "headline": "先補核心資料，不判斷爆發潛力",
            "thesis": "背景分析尚未完成，不把快速摘要當成爆發候選。",
            "leading_signals": ["等待資料同步完成後再判斷。"],
            "missing_confirmations": ["等待價格、基本面、籌碼與新聞同步完成。"],
            "trigger_conditions": ["資料來源變成可信來源後重新整理。"],
            "invalidation": "資料不足時不建立失效價。",
            "no_chase_warning": "資料同步前不追價、不判斷飆股。",
        },
        "kline_analysis": {
            "headline": "等待真實 K 線資料",
            "trend": "等待資料",
            "support_levels": ["等待資料"],
            "resistance_levels": ["等待資料"],
            "strategy_notes": ["資料同步完成前不畫支撐壓力。"],
            "invalidation": ["等待資料"],
        },
    }
