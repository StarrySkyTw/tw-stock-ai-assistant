from fastapi import APIRouter

from app.schemas.analysis import MarketOverviewResponse, MarketRiskResponse
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

