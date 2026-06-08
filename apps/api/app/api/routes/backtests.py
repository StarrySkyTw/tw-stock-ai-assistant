from fastapi import APIRouter

from app.schemas import BacktestRequest, BacktestResponse
from app.services.backtest import BacktestService

router = APIRouter(tags=["backtests"])


@router.post("/backtests", response_model=BacktestResponse)
async def run_backtest(request: BacktestRequest) -> dict:
    result = await BacktestService().run(
        request.symbol, request.years, request.strategy, request.initial_capital
    )
    return result.to_dict()

