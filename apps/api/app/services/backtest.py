from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.services.data_providers import MarketDataService
from app.services.indicators import calculate_indicators


@dataclass
class BacktestResult:
    symbol: str
    years: int
    strategy: str
    win_rate: float
    max_drawdown: float
    annualized_return: float
    sharpe_ratio: float
    trades: list[dict]
    equity_curve: list[dict]

    def to_dict(self) -> dict:
        return self.__dict__.copy()


class BacktestService:
    def __init__(self) -> None:
        self.data = MarketDataService()

    async def run(
        self,
        symbol: str,
        years: int = 1,
        strategy: str = "score_ma_atr",
        initial_capital: float = 100000,
    ) -> BacktestResult:
        prices, _ = await self.data.prices(symbol.upper(), years=years)
        df = calculate_indicators(prices).dropna(subset=["ma20", "ma60", "atr14"]).reset_index(drop=True)
        cash = initial_capital
        shares = 0.0
        entry_price = 0.0
        high_since_entry = 0.0
        trades: list[dict] = []
        equity_curve: list[dict] = []

        for _, row in df.iterrows():
            close = float(row["close"])
            buy_signal = close > row["ma20"] > row["ma60"] and row["rsi14"] < 72 and row["osc"] > 0
            trailing_stop = high_since_entry - 2 * float(row["atr14"]) if shares else None
            sell_signal = bool(
                shares
                and (
                    close < row["ma20"]
                    or row["rsi14"] > 80
                    or (trailing_stop is not None and close < trailing_stop)
                )
            )

            if shares == 0 and buy_signal:
                shares = cash / close
                entry_price = close
                high_since_entry = close
                cash = 0
                trades.append({"date": str(row["date"]), "side": "buy", "price": round(close, 2)})
            elif shares:
                high_since_entry = max(high_since_entry, float(row["high"]))
                if sell_signal:
                    cash = shares * close
                    profit_pct = close / entry_price - 1
                    trades.append(
                        {
                            "date": str(row["date"]),
                            "side": "sell",
                            "price": round(close, 2),
                            "profit_percent": round(profit_pct * 100, 2),
                        }
                    )
                    shares = 0
                    entry_price = 0
                    high_since_entry = 0
            equity = cash + shares * close
            equity_curve.append({"date": str(row["date"]), "equity": round(equity, 2)})

        if shares and len(df):
            close = float(df.iloc[-1]["close"])
            cash = shares * close
            trades.append(
                {
                    "date": str(df.iloc[-1]["date"]),
                    "side": "sell",
                    "price": round(close, 2),
                    "profit_percent": round((close / entry_price - 1) * 100, 2),
                    "reason": "end_of_backtest",
                }
            )
            shares = 0

        metrics = _metrics(equity_curve, trades, initial_capital, years)
        return BacktestResult(
            symbol=symbol.upper(),
            years=years,
            strategy=strategy,
            trades=trades,
            equity_curve=equity_curve,
            **metrics,
        )


def _metrics(equity_curve: list[dict], trades: list[dict], initial_capital: float, years: int) -> dict:
    if not equity_curve:
        return {"win_rate": 0, "max_drawdown": 0, "annualized_return": 0, "sharpe_ratio": 0}
    equity = pd.Series([item["equity"] for item in equity_curve], dtype=float)
    returns = equity.pct_change().fillna(0)
    final = float(equity.iloc[-1])
    annualized = (final / initial_capital) ** (1 / max(years, 1)) - 1
    running_max = equity.cummax()
    drawdown = equity / running_max - 1
    closed = [trade for trade in trades if trade["side"] == "sell" and "profit_percent" in trade]
    wins = [trade for trade in closed if trade["profit_percent"] > 0]
    sharpe = 0.0
    if returns.std() > 0:
        sharpe = float(np.sqrt(252) * returns.mean() / returns.std())
    return {
        "win_rate": round(len(wins) / len(closed) * 100, 2) if closed else 0,
        "max_drawdown": round(float(drawdown.min()) * 100, 2),
        "annualized_return": round(annualized * 100, 2),
        "sharpe_ratio": round(sharpe, 2),
    }

