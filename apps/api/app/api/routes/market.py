import asyncio

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.schemas.analysis import (
    AiStockPicksResponse,
    MarketOverviewResponse,
    MarketRiskResponse,
    MarketScanRequest,
    MarketScanResponse,
)
from app.services.ai_picker import AiStockPickerService
from app.services.calendar import taipei_now
from app.services.data_providers.twse import TwseProvider
from app.services.market_scan import MarketScanService
from app.services.market_risk import MarketRiskEngine
from app.services.sample_data import make_price_history

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/risk", response_model=MarketRiskResponse)
async def market_risk() -> dict:
    return await MarketRiskEngine().evaluate()


@router.get("/overview", response_model=MarketOverviewResponse)
async def market_overview() -> dict:
    risk_task = asyncio.create_task(MarketRiskEngine().evaluate())
    quote_task = asyncio.create_task(_load_taiex_quote())
    risk, taiex_quote = await asyncio.gather(risk_task, quote_task)
    taiex_change = risk["indicators"].get("taiex_change_20d") or 0
    return {
        "taiex_state": "偏多" if taiex_change > 2 else "整理",
        "otc_state": "整理",
        "market_status": risk["status"],
        "heavyweight_impact": {"2330": 0.42, "2454": 0.09, "2317": 0.08},
        "taiex_quote": taiex_quote,
        "risk": risk,
    }


@router.get("/ai-picks", response_model=AiStockPicksResponse)
async def ai_stock_picks(
    universe: str | None = Query(default=None, description="Comma separated stock symbols."),
    limit: int = Query(default=5, ge=1, le=10),
    min_score: float = Query(default=60, ge=0, le=100),
) -> dict:
    symbols = universe.split(",") if universe else None
    return await AiStockPickerService().scan(symbols, limit=limit, min_score=min_score)


@router.post("/scans", response_model=MarketScanResponse)
async def create_market_scan(
    payload: MarketScanRequest | None = Body(default=None),
    db: Session = Depends(get_db),
) -> dict:
    request = payload or MarketScanRequest()
    return await MarketScanService(db).run_scan(
        universe=request.universe,
        limit=request.limit,
        max_symbols=request.max_symbols,
    )


@router.get("/scans/latest", response_model=MarketScanResponse)
async def latest_market_scan(db: Session = Depends(get_db)) -> dict:
    scan = MarketScanService(db).latest_scan()
    if not scan:
        raise HTTPException(status_code=404, detail="Market scan has not been created yet.")
    return scan


@router.get("/scans/{scan_id}", response_model=MarketScanResponse)
async def get_market_scan(scan_id: int, db: Session = Depends(get_db)) -> dict:
    scan = MarketScanService(db).get_scan(scan_id)
    if not scan:
        raise HTTPException(status_code=404, detail="Market scan not found.")
    return scan


async def _load_taiex_quote() -> dict | None:
    if get_settings().enable_live_data:
        try:
            live_quote = await TwseProvider().realtime_snapshot("TAIEX")
            quote = _quote_from_realtime_snapshot(live_quote, "twse-realtime")
            if quote is not None:
                return quote
        except Exception:
            pass

    return _quote_from_history(make_price_history("TAIEX", years=1).tail(2), "sample")


def _quote_from_realtime_snapshot(snapshot: dict | None, source: str) -> dict | None:
    if not snapshot:
        return None

    value = _as_float(snapshot.get("close"))
    previous_value = _as_float(snapshot.get("previous_close"))
    if value is None or previous_value is None:
        return None

    change = value - previous_value
    change_percent = (change / previous_value * 100) if previous_value else 0.0
    return {
        "symbol": "TAIEX",
        "name": str(snapshot.get("name") or "加權指數"),
        "value": round(value, 2),
        "change": round(change, 2),
        "change_percent": round(change_percent, 2),
        "volume": _as_float(snapshot.get("volume")),
        "source": source,
        "updated_at": taipei_now(),
    }


def _quote_from_history(history, source: str) -> dict | None:
    if history is None or history.empty:
        return None

    latest = history.iloc[-1]
    previous = history.iloc[-2] if len(history) >= 2 else latest
    value = _as_float(latest.get("close"))
    previous_value = _as_float(previous.get("close")) or value
    if value is None or previous_value is None:
        return None

    change = value - previous_value
    change_percent = (change / previous_value * 100) if previous_value else 0.0
    return {
        "symbol": "TAIEX",
        "name": "加權指數",
        "value": round(value, 2),
        "change": round(change, 2),
        "change_percent": round(change_percent, 2),
        "volume": _as_float(latest.get("volume")),
        "source": source,
        "updated_at": taipei_now(),
    }


def _as_float(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return number
