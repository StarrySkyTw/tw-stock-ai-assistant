import pytest

from app.services.backtest import BacktestService


@pytest.mark.asyncio
async def test_backtest_returns_metrics():
    result = await BacktestService().run("2330", years=1)

    assert result.symbol == "2330"
    assert result.years == 1
    assert result.equity_curve
    assert isinstance(result.sharpe_ratio, float)

