from __future__ import annotations

import asyncio
from typing import Any

from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import MarketScanResult
from app.services.ai_picker import DEFAULT_AI_UNIVERSE, build_candidate_from_analysis
from app.services.analysis import AnalysisService
from app.services.calendar import taipei_now
from app.services.data_providers.finmind import FinMindProvider
from app.services.future_outlook import build_candidate_fallback_future_outlook
from app.services.market_risk import MarketRiskEngine
from app.services.source_quality import is_trusted_source

STATUS_PRIORITY = {
    "qualified_research": 4,
    "wait_price": 3,
    "watch_only": 2,
    "reject": 1,
}


class MarketScanService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.analysis = AnalysisService()
        self.risk_engine = MarketRiskEngine()

    async def run_scan(
        self,
        *,
        universe: list[str] | None = None,
        limit: int = 50,
        max_symbols: int | None = None,
    ) -> dict[str, Any]:
        settings = get_settings()
        symbol_limit = max_symbols or settings.market_scan_max_symbols
        symbols, universe_source, is_full_market = await self._resolve_universe(universe, symbol_limit)
        market = await self.risk_engine.evaluate()
        analyses, failed = await self._analyze_symbols(
            symbols,
            settings.market_scan_concurrency,
            market,
            settings.analysis_background_timeout_seconds,
        )
        candidates = [build_candidate_from_analysis(item, market) for item in analyses]
        candidates.sort(
            key=lambda item: (
                STATUS_PRIORITY.get(item["candidate_status"], 0),
                _breakout_score(item),
                item["selection_score"],
            ),
            reverse=True,
        )
        for index, item in enumerate(candidates, start=1):
            item["rank"] = index

        generated_at = taipei_now()
        response = {
            "scan_id": 0,
            "generated_at": generated_at,
            "universe_count": len(symbols),
            "completed_count": len(analyses),
            "failed_count": len(failed),
            "universe_source": universe_source,
            "is_full_market": is_full_market,
            "data_quality_summary": _data_quality_summary(candidates),
            "top_candidates": candidates[:limit],
            "failed_symbols": failed,
        }
        row = MarketScanResult(
            generated_at=generated_at,
            universe_count=response["universe_count"],
            completed_count=response["completed_count"],
            failed_count=response["failed_count"],
            payload=jsonable_encoder(response),
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        payload = dict(row.payload)
        payload["scan_id"] = row.id
        row.payload = payload
        self.db.commit()
        return payload

    def latest_scan(self) -> dict[str, Any] | None:
        row = (
            self.db.query(MarketScanResult)
            .order_by(MarketScanResult.generated_at.desc(), MarketScanResult.id.desc())
            .first()
        )
        if not row:
            return None
        payload = _normalize_payload(dict(row.payload))
        payload["scan_id"] = row.id
        return payload

    def get_scan(self, scan_id: int) -> dict[str, Any] | None:
        row = self.db.get(MarketScanResult, scan_id)
        if not row:
            return None
        payload = _normalize_payload(dict(row.payload))
        payload["scan_id"] = row.id
        return payload

    async def _resolve_universe(self, universe: list[str] | None, max_symbols: int) -> tuple[list[str], str, bool]:
        if universe:
            return _normalize_universe(universe, max_symbols), "custom", False

        settings = get_settings()
        if settings.enable_live_data and settings.finmind_token:
            provider = FinMindProvider(settings.finmind_token)
            frame = await provider._safe_data("TaiwanStockInfo")
            if not frame.empty:
                id_column = "stock_id" if "stock_id" in frame.columns else "code" if "code" in frame.columns else None
                if id_column:
                    symbols = [
                        str(value)
                        for value in frame[id_column].dropna().tolist()
                        if str(value).strip().isdigit() and len(str(value).strip()) == 4
                    ]
                    normalized = _normalize_universe(symbols, max_symbols)
                    if normalized:
                        is_full_market = len(normalized) >= 500 and len(normalized) < max_symbols
                        source = "finmind_twse_otc" if is_full_market else "finmind_limited"
                        return normalized, source, is_full_market
        return _normalize_universe(DEFAULT_AI_UNIVERSE, max_symbols), "default_watchlist", False

    async def _analyze_symbols(
        self,
        symbols: list[str],
        concurrency: int,
        market_risk: dict[str, Any],
        data_timeout_seconds: float | None = None,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        semaphore = asyncio.Semaphore(max(1, concurrency))

        async def analyze_one(symbol: str) -> tuple[str, dict[str, Any] | None]:
            try:
                async with semaphore:
                    return symbol, await self.analysis.analyze(
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


def _normalize_universe(values: list[str], limit: int) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        symbol = "".join(ch for ch in value.upper().strip() if ch.isalnum() or ch in {".", "^", "-"})
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        output.append(symbol)
        if len(output) >= limit:
            break
    return output


def _normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    payload.setdefault("universe_source", "unknown")
    payload.setdefault("is_full_market", False)
    for candidate in payload.get("top_candidates", []):
        sources = candidate.get("data_sources", {})
        candidate.setdefault("data_quality_score", _candidate_quality_from_sources(sources))
        candidate.setdefault("score_cap_reason", None)
        candidate.setdefault("breakout_potential", _fallback_breakout_potential(sources))
        _normalize_candidate_data_quality(candidate)
        if not candidate.get("future_outlook") or _has_core_data_limit(sources):
            candidate["future_outlook"] = _fallback_candidate_future_outlook(candidate)
    payload["data_quality_summary"] = _data_quality_summary(payload.get("top_candidates", []))
    return payload


def _normalize_candidate_data_quality(candidate: dict[str, Any]) -> None:
    sources = candidate.get("data_sources", {})
    blockers = candidate.setdefault("blockers", [])
    if not is_trusted_source(sources.get("fundamental"), "fundamental"):
        candidate["fundamental_gate"] = _untrusted_fundamental_gate()
        candidate["valuation_gate"] = _untrusted_valuation_gate()
        candidate["breakout_potential"] = _untrusted_breakout_potential()
        candidate["score_cap_reason"] = candidate.get("score_cap_reason") or "基本面不是真實可驗證資料，排序分數上限為 49。"
        _cap_candidate_scores(candidate, 49.0)
        _append_unique(blockers, "基本面資料不是可驗證真實來源，不採用 EPS、PE、ROE 或營收做結論。")
    if _is_sample_source(sources.get("price")):
        candidate["timing_gate"] = _untrusted_timing_gate()
        candidate["price_plan"] = _untrusted_price_plan()
        candidate["breakout_potential"] = _untrusted_breakout_potential()
        _append_unique(blockers, "價格資料不是可驗證歷史日 K，不採用均線、支撐、壓力或失效價。")
    if not is_trusted_source(sources.get("fundamental"), "fundamental") or _is_sample_source(sources.get("price")):
        if candidate.get("candidate_status") in {"qualified_research", "wait_price"}:
            candidate["candidate_status"] = "watch_only"
        candidate["data_quality_score"] = min(
            float(candidate.get("data_quality_score") or _candidate_quality_from_sources(sources)),
            _candidate_quality_from_sources(sources),
        )


def _cap_candidate_scores(candidate: dict[str, Any], cap: float) -> None:
    for key in ("adjusted_score", "selection_score"):
        value = _float_or_none(candidate.get(key))
        if value is not None and value > cap:
            candidate[key] = cap


def _untrusted_fundamental_gate() -> dict[str, Any]:
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


def _untrusted_valuation_gate() -> dict[str, Any]:
    return {
        "status": "unknown",
        "pe_ratio": None,
        "pe_band": "資料不足",
        "sector_band": "等待真實基本面",
        "is_low_valuation": False,
        "warning": "基本面不是可驗證真實來源，不採用 PE、PB 或產業估值區間。",
    }


def _untrusted_timing_gate() -> dict[str, Any]:
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


def _untrusted_price_plan() -> dict[str, Any]:
    return {
        "research_price": None,
        "watch_price": None,
        "invalidation_price": None,
        "position_size_hint": "0%，價格資料不是可驗證歷史日 K；等真實日 K 後再建立研究價與失效價。",
    }


def _fallback_breakout_potential(sources: dict[str, str]) -> dict[str, Any]:
    if _has_core_data_limit(sources):
        return _untrusted_breakout_potential()
    return {
        "status": "wait_confirmation",
        "label": "等待確認",
        "score": 50.0,
        "confidence": "低",
        "headline": "舊掃描缺少爆發潛力欄位，建議重新掃描",
        "thesis": "這筆快取是在新欄位上線前產生，只能先視為等待確認。",
        "leading_signals": ["重新掃描後會補上基本面、估值、K 線與籌碼共振判斷。"],
        "missing_confirmations": ["請重新執行市場掃描，取得最新爆發潛力判斷。"],
        "trigger_conditions": ["重新掃描並確認資料來源可信。"],
        "invalidation": "舊快取不建立爆發失效條件。",
        "no_chase_warning": "舊快取不追高，先重新掃描。",
    }


def _untrusted_breakout_potential() -> dict[str, Any]:
    return {
        "status": "data_limited",
        "label": "資料不足",
        "score": 8.0,
        "confidence": "低",
        "headline": "先補核心資料，不判斷爆發潛力",
        "thesis": "基本面或價格不是可驗證來源時，只能列為觀察，不能當成飆股或高潛力候選。",
        "leading_signals": ["資料未可信前，不採用爆發潛力排序。"],
        "missing_confirmations": [
            "補上官方或 FinMind 基本面。",
            "接上可驗證日 K 後重算支撐、壓力與失效價。",
        ],
        "trigger_conditions": [
            "基本面來源變成可驗證資料。",
            "價格來源變成可驗證日 K。",
            "重新掃描後再比較候選。",
        ],
        "invalidation": "資料不足時不建立失效價，先避免把觀察當成進場依據。",
        "no_chase_warning": "資料不足時不追高，也不把候選清單視為飆股清單。",
    }


def _fallback_candidate_future_outlook(candidate: dict[str, Any]) -> dict[str, Any]:
    sources = candidate.get("data_sources", {})
    if _has_core_data_limit(sources):
        return build_candidate_fallback_future_outlook(data_limited=True)
    return build_candidate_fallback_future_outlook(reason="舊掃描待重算")


def _data_quality_summary(candidates: list[dict[str, Any]]) -> dict[str, int]:
    summary = {
        "qualified_research": 0,
        "wait_price": 0,
        "watch_only": 0,
        "reject": 0,
        "breakout_ready_setup": 0,
        "breakout_wait_confirmation": 0,
        "breakout_wait_pullback": 0,
        "breakout_too_extended": 0,
        "breakout_not_ready": 0,
        "breakout_data_limited": 0,
        "trusted_fundamental": 0,
        "finmind_fundamental": 0,
        "missing_fundamental": 0,
        "sample_limited": 0,
        "optional_unavailable": 0,
        "average_data_quality_score": 0,
    }
    quality_total = 0.0
    for item in candidates:
        status = item.get("candidate_status", "watch_only")
        if status in summary:
            summary[status] += 1
        breakout_status = item.get("breakout_potential", {}).get("status")
        breakout_key = f"breakout_{breakout_status}"
        if breakout_key in summary:
            summary[breakout_key] += 1
        sources = item.get("data_sources", {})
        fundamental_source = str(sources.get("fundamental") or "").lower()
        if is_trusted_source(fundamental_source, "fundamental"):
            summary["trusted_fundamental"] += 1
            if fundamental_source == "finmind":
                summary["finmind_fundamental"] += 1
        else:
            summary["missing_fundamental"] += 1
        if _has_core_data_limit(sources):
            summary["sample_limited"] += 1
        if _has_optional_data_gap(sources):
            summary["optional_unavailable"] += 1
        quality_total += float(item.get("data_quality_score") or 0)
    if candidates:
        summary["average_data_quality_score"] = round(quality_total / len(candidates))
    return summary


def _candidate_quality_from_sources(sources: dict[str, str]) -> float:
    if not sources:
        return 0.0
    score = 0
    if is_trusted_source(sources.get("fundamental"), "fundamental"):
        score += 40
    price_source = str(sources.get("price", "")).lower()
    if "sample" not in price_source and any(provider in price_source for provider in ("finmind", "twse", "yahoo")):
        score += 20
    for key, weight in {"institutional": 12, "margin": 10, "news": 10, "shareholding": 8}.items():
        if is_trusted_source(sources.get(key), key):
            score += weight
    return float(score)


def _breakout_score(item: dict[str, Any]) -> float:
    return _float_or_none(item.get("breakout_potential", {}).get("score")) or 0.0


def _is_sample_source(source: Any) -> bool:
    return not source or "sample" in str(source).lower()


def _has_core_data_limit(sources: dict[str, str]) -> bool:
    return not is_trusted_source(sources.get("fundamental"), "fundamental") or _is_sample_source(sources.get("price"))


def _has_optional_data_gap(sources: dict[str, str]) -> bool:
    for key in ("institutional", "margin", "shareholding", "news"):
        source = str(sources.get(key, "")).lower()
        if not source or source == "unavailable" or "sample" in source:
            return True
    return False


def _float_or_none(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return number


def _append_unique(items: list[str], value: str) -> None:
    if value not in items:
        items.append(value)
