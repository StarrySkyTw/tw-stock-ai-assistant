from fastapi import APIRouter, Query

from app.schemas import AnalysisResponse, ChartResponse
from app.services.analysis import AnalysisService

router = APIRouter(tags=["stocks"])


@router.get("/stocks/{symbol}/analysis", response_model=AnalysisResponse)
async def analyze_stock(
    symbol: str,
    entry_price: float | None = Query(default=None, gt=0),
    highest_price: float | None = Query(default=None, gt=0),
    atr_multiplier: float = Query(default=2.0, gt=0, le=5),
) -> dict:
    return await AnalysisService().analyze(symbol, entry_price, highest_price, atr_multiplier)


@router.get("/stocks/{symbol}/chart", response_model=ChartResponse)
async def stock_chart(symbol: str, range: str = Query(default="1y", pattern="^(1y|3y|5y)$")) -> dict:
    return await AnalysisService().chart(symbol, range)

