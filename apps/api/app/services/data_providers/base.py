from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import pandas as pd


@dataclass
class FundamentalData:
    eps: float | None = None
    roe: float | None = None
    gross_margin: float | None = None
    operating_margin: float | None = None
    pe_ratio: float | None = None
    pb_ratio: float | None = None
    revenue_yoy: float | None = None
    revenue_mom: float | None = None

    def to_dict(self) -> dict[str, float | None]:
        return self.__dict__.copy()


@dataclass
class ShareholdingData:
    large_holder_ratio: float | None = None
    shareholder_count: int | None = None

    def to_dict(self) -> dict[str, float | int | None]:
        return self.__dict__.copy()


class MarketDataProvider(Protocol):
    async def daily_prices(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        ...

    async def institutional_flows(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        ...

    async def fundamentals(self, symbol: str) -> FundamentalData:
        ...

    async def margin_balances(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        ...

    async def shareholding(self, symbol: str) -> ShareholdingData:
        ...

    async def news(self, symbol: str) -> list[dict]:
        ...


def normalize_price_frame(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    normalized = df.copy()
    if isinstance(normalized.columns, pd.MultiIndex):
        normalized.columns = [
            next((str(part) for part in column if str(part) and str(part) != "nan"), "")
            for column in normalized.columns
        ]
    normalized = normalized.loc[:, ~normalized.columns.duplicated()]

    renamed = normalized.rename(
        columns={
            "max": "high",
            "min": "low",
            "Date": "date",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
            "Trading_Volume": "volume",
            "Trading_money": "trading_value",
            "stock_id": "symbol",
        }
    )
    required = ["date", "open", "high", "low", "close", "volume"]
    missing = [column for column in required if column not in renamed.columns]
    if missing:
        raise ValueError(f"Price dataframe missing columns: {missing}")
    out = renamed[required].copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.date
    for column in ["open", "high", "low", "close", "volume"]:
        values = out[column]
        if isinstance(values, pd.DataFrame):
            values = values.iloc[:, 0]
        out[column] = pd.to_numeric(values, errors="coerce")
    out = out.dropna(subset=["date", "open", "high", "low", "close"])
    out["volume"] = out["volume"].fillna(0)
    return out.sort_values("date").reset_index(drop=True)
