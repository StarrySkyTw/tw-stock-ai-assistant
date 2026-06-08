from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from app.core.config import get_settings
from app.services import sample_data
from app.services.data_providers.base import FundamentalData, ShareholdingData
from app.services.data_providers.finmind import FinMindProvider
from app.services.data_providers.twse import TwseProvider
from app.services.data_providers.yahoo import YahooProvider


class MarketDataService:
    def __init__(self) -> None:
        settings = get_settings()
        self.enable_live_data = settings.enable_live_data
        self.finmind = FinMindProvider(settings.finmind_token)
        self.twse = TwseProvider()
        self.yahoo = YahooProvider()

    async def prices(self, symbol: str, years: int = 2) -> tuple[pd.DataFrame, str]:
        end = date.today()
        start = end - timedelta(days=365 * years + 30)
        if self.enable_live_data:
            for source, fetcher in (
                ("finmind", self.finmind.daily_prices),
                ("yahoo", self.yahoo.daily_prices),
            ):
                try:
                    df = await fetcher(symbol, start.isoformat(), end.isoformat())
                    if len(df) >= 60:
                        return df, source
                except Exception:
                    continue
        return sample_data.make_price_history(symbol, years=years), "sample"

    async def stock_name(self, symbol: str) -> str | None:
        if self.enable_live_data:
            try:
                name = await self.finmind.stock_name(symbol)
                if name:
                    return name
            except Exception:
                pass
        return sample_data.stock_name(symbol)

    async def institutional_flows(self, symbol: str) -> tuple[pd.DataFrame, str]:
        end = date.today()
        start = end - timedelta(days=100)
        if self.enable_live_data:
            try:
                df = await self.finmind.institutional_flows(symbol, start.isoformat(), end.isoformat())
                if len(df) >= 20:
                    return df, "finmind"
            except Exception:
                pass
        return sample_data.make_institutional_flows(symbol), "sample"

    async def fundamentals(self, symbol: str) -> tuple[dict[str, float | None], str]:
        if self.enable_live_data:
            try:
                data = await self.finmind.fundamentals(symbol)
                values = data.to_dict()
                if any(value is not None for value in values.values()):
                    return values, "finmind"
            except Exception:
                pass
        return FundamentalData(**sample_data.make_fundamental(symbol)).to_dict(), "sample"

    async def margin_balances(self, symbol: str) -> tuple[pd.DataFrame, str]:
        end = date.today()
        start = end - timedelta(days=100)
        if self.enable_live_data:
            try:
                df = await self.finmind.margin_balances(symbol, start.isoformat(), end.isoformat())
                if not df.empty:
                    return df, "finmind"
            except Exception:
                pass
        return sample_data.make_margin(symbol), "sample"

    async def shareholding(self, symbol: str) -> tuple[dict[str, float | int | None], str]:
        if self.enable_live_data:
            try:
                data = await self.finmind.shareholding(symbol)
                values = data.to_dict()
                if any(value is not None for value in values.values()):
                    return values, "finmind"
            except Exception:
                pass
        return ShareholdingData(**sample_data.make_shareholding(symbol)).to_dict(), "sample"

    async def news(self, symbol: str) -> tuple[list[dict], str]:
        if self.enable_live_data:
            try:
                rows = await self.finmind.news(symbol)
                if rows:
                    return rows, "finmind"
            except Exception:
                pass
        return sample_data.make_news(symbol), "sample"
