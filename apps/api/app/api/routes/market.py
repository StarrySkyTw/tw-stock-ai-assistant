from fastapi import APIRouter, Query

from app.schemas.analysis import AiStockPicksResponse, MarketOverviewResponse, MarketRiskResponse
from app.services.ai_picker import AiStockPickerService
from app.services.market_risk import MarketRiskEngine

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/risk", response_model=MarketRiskResponse)
async def market_risk() -> dict:
    return await MarketRiskEngine().evaluate()


@router.get("/overview", response_model=MarketOverviewResponse)
async def market_overview() -> dict:
    risk = await MarketRiskEngine().evaluate()
    return {
        "taiex_state": "多頭" if risk["indicators"].get("taiex_change_20d", 0) > 2 else "震盪",
        "otc_state": "震盪",
        "market_status": risk["status"],
        "heavyweight_impact": {"2330": 0.42, "2454": 0.09, "2317": 0.08},
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
