from __future__ import annotations

from datetime import timedelta

import pandas as pd

from app.core.config import get_settings
from app.services import sample_data
from app.services.calendar import taipei_today
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
        end = taipei_today()
        start = end - timedelta(days=365 * years + 30)
        if self.enable_live_data:
            for source, fetcher in (
                ("finmind", self.finmind.daily_prices),
                ("yahoo", self.yahoo.daily_prices),
            ):
                try:
                    df = await fetcher(symbol, start.isoformat(), end.isoformat())
                    if len(df) >= 60:
                        return await self._with_realtime_quote(symbol, df, source)
                except Exception:
                    continue
            try:
                quote = await self.twse.realtime_quote(symbol)
                if not quote.empty:
                    history = sample_data.make_price_history(symbol, years=years)
                    return merge_realtime_quote(history, quote), "sample+twse-realtime"
            except Exception:
                pass
        return sample_data.make_price_history(symbol, years=years), "sample"

    async def _with_realtime_quote(self, symbol: str, history: pd.DataFrame, source: str) -> tuple[pd.DataFrame, str]:
        try:
            quote = await self.twse.realtime_quote(symbol)
        except Exception:
            return history, source
        if quote.empty:
            return history, source
        merged = merge_realtime_quote(history, quote)
        if merged.equals(history):
            return history, source
        return merged, f"{source}+twse-realtime"

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
        end = taipei_today()
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
        end = taipei_today()
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


def merge_realtime_quote(history: pd.DataFrame, quote: pd.DataFrame) -> pd.DataFrame:
    if history.empty or quote.empty:
        return history

    quote_row = quote.tail(1).copy()
    quote_date = pd.to_datetime(quote_row.iloc[0]["date"]).date()
    normalized = history.copy()
    normalized["date"] = pd.to_datetime(normalized["date"]).dt.date
    latest_history_date = normalized["date"].max()

    if quote_date < latest_history_date:
        return history

    merged = pd.concat([normalized[normalized["date"] != quote_date], quote_row], ignore_index=True)
    return merged.sort_values("date").reset_index(drop=True)
