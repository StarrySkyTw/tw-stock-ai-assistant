from __future__ import annotations

from datetime import timedelta

import pandas as pd

from app.core.config import get_settings
from app.services import sample_data
from app.services.calendar import taipei_today
from app.services.data_providers.base import FundamentalData, ShareholdingData
from app.services.data_providers.cache import cached_provider_call, clear_provider_cache
from app.services.data_providers.finmind import FinMindProvider
from app.services.data_providers.twse import TwseProvider
from app.services.data_providers.yahoo import YahooProvider
from app.services.industry import resolve_industry

MARKET_DATA_CACHE_PREFIX = "market-data:"


def clear_market_data_cache() -> None:
    clear_provider_cache(MARKET_DATA_CACHE_PREFIX)


class MarketDataService:
    def __init__(self) -> None:
        settings = get_settings()
        self.enable_live_data = settings.enable_live_data
        self.finmind = FinMindProvider(settings.finmind_token)
        self.twse = TwseProvider()
        self.yahoo = YahooProvider()

    async def prices(self, symbol: str, years: int = 2) -> tuple[pd.DataFrame, str]:
        key = self._cache_key("prices", symbol, years, taipei_today().isoformat())
        return await cached_provider_call(key, self._cache_ttl(), lambda: self._prices_uncached(symbol, years))

    async def _prices_uncached(self, symbol: str, years: int = 2) -> tuple[pd.DataFrame, str]:
        end = taipei_today()
        start = end - timedelta(days=365 * years + 30)
        if self.enable_live_data:
            price_fetchers = (
                (("finmind", self.finmind.daily_prices), ("yahoo", self.yahoo.daily_prices))
                if self.finmind.token
                else (("yahoo", self.yahoo.daily_prices),)
            )
            for source, fetcher in price_fetchers:
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

    async def intraday_prices(self, symbol: str) -> tuple[pd.DataFrame, dict]:
        if self.enable_live_data:
            try:
                df, metadata = await self.yahoo.intraday_prices(symbol)
                if len(df) >= 2:
                    return df, {**metadata, "source": "yahoo-1m"}
            except Exception:
                pass
        return pd.DataFrame(), {"source": "unavailable"}

    async def stock_name(self, symbol: str) -> str | None:
        profile = await self.stock_profile(symbol)
        return profile["name"]

    async def stock_profile(self, symbol: str) -> dict[str, str | None]:
        key = self._cache_key("stock-profile", symbol)
        return await cached_provider_call(key, self._cache_ttl(), lambda: self._stock_profile_uncached(symbol))

    async def _stock_profile_uncached(self, symbol: str) -> dict[str, str | None]:
        profiles: list[dict[str, str | None]] = []
        if self.enable_live_data:
            for fetcher in (self.finmind.stock_profile, self.twse.stock_profile):
                try:
                    profile = await fetcher(symbol)
                except Exception:
                    continue
                if _profile_value(profile, "name") or _profile_value(profile, "industry"):
                    profiles.append(profile)
                if _profile_value(profile, "name") and _profile_value(profile, "industry"):
                    break
        name = _first_profile_value(profiles, "name") or sample_data.stock_name(symbol)
        source_industry = _first_profile_value(profiles, "industry")
        return {"name": name, "industry": resolve_industry(symbol, name, source_industry)}

    async def institutional_flows(self, symbol: str) -> tuple[pd.DataFrame, str]:
        key = self._cache_key("institutional", symbol, taipei_today().isoformat())
        return await cached_provider_call(
            key,
            self._cache_ttl(),
            lambda: self._institutional_flows_uncached(symbol),
        )

    async def _institutional_flows_uncached(self, symbol: str) -> tuple[pd.DataFrame, str]:
        end = taipei_today()
        start = end - timedelta(days=100)
        if self.enable_live_data:
            try:
                df, source = await self.twse.institutional_flows_with_source(symbol, start.isoformat(), end.isoformat())
                if not df.empty:
                    return df, source
            except Exception:
                pass
            try:
                df = await self.finmind.institutional_flows(symbol, start.isoformat(), end.isoformat())
                if len(df) >= 20:
                    return df, "finmind"
            except Exception:
                pass
            return _empty_institutional_flows(), "unavailable"
        return sample_data.make_institutional_flows(symbol), "sample"

    async def fundamentals(self, symbol: str) -> tuple[dict[str, float | None], str]:
        key = self._cache_key("fundamentals", symbol, taipei_today().isoformat())
        return await cached_provider_call(key, self._cache_ttl(), lambda: self._fundamentals_uncached(symbol))

    async def _fundamentals_uncached(self, symbol: str) -> tuple[dict[str, float | None], str]:
        if self.enable_live_data:
            try:
                data, source = await self.twse.fundamentals_with_source(symbol)
                values = data.to_dict()
                if any(value is not None for value in values.values()):
                    return values, source
            except Exception:
                pass
            try:
                data = await self.finmind.fundamentals(symbol)
                values = data.to_dict()
                if any(value is not None for value in values.values()):
                    return values, "finmind"
            except Exception:
                pass
            return FundamentalData().to_dict(), "unavailable"
        return FundamentalData(**sample_data.make_fundamental(symbol)).to_dict(), "sample"

    async def margin_balances(self, symbol: str) -> tuple[pd.DataFrame, str]:
        key = self._cache_key("margin", symbol, taipei_today().isoformat())
        return await cached_provider_call(key, self._cache_ttl(), lambda: self._margin_balances_uncached(symbol))

    async def _margin_balances_uncached(self, symbol: str) -> tuple[pd.DataFrame, str]:
        end = taipei_today()
        start = end - timedelta(days=100)
        if self.enable_live_data:
            try:
                df, source = await self.twse.margin_balances_with_source(symbol, start.isoformat(), end.isoformat())
                if not df.empty:
                    return df, source
            except Exception:
                pass
            try:
                df = await self.finmind.margin_balances(symbol, start.isoformat(), end.isoformat())
                if not df.empty:
                    return df, "finmind"
            except Exception:
                pass
            return _empty_margin_balances(), "unavailable"
        return sample_data.make_margin(symbol), "sample"

    async def shareholding(self, symbol: str) -> tuple[dict[str, float | int | None], str]:
        key = self._cache_key("shareholding", symbol, taipei_today().isoformat())
        return await cached_provider_call(key, self._cache_ttl(), lambda: self._shareholding_uncached(symbol))

    async def _shareholding_uncached(self, symbol: str) -> tuple[dict[str, float | int | None], str]:
        if self.enable_live_data:
            try:
                data = await self.finmind.shareholding(symbol)
                values = data.to_dict()
                if any(value is not None for value in values.values()):
                    return values, "finmind"
            except Exception:
                pass
            try:
                data, source = await self.twse.shareholding_with_source(symbol)
                values = data.to_dict()
                if any(value is not None for value in values.values()):
                    return values, source
            except Exception:
                pass
            return ShareholdingData().to_dict(), "unavailable"
        return ShareholdingData(**sample_data.make_shareholding(symbol)).to_dict(), "sample"

    async def news(self, symbol: str) -> tuple[list[dict], str]:
        key = self._cache_key("news", symbol, taipei_today().isoformat())
        return await cached_provider_call(key, self._cache_ttl(), lambda: self._news_uncached(symbol))

    async def _news_uncached(self, symbol: str) -> tuple[list[dict], str]:
        if self.enable_live_data:
            try:
                rows = await self.finmind.news(symbol)
                if rows:
                    return rows, "finmind"
            except Exception:
                pass
            try:
                rows, source = await self.twse.material_events_with_source(symbol)
                if source != "unavailable":
                    return rows, source
            except Exception:
                pass
            return [], "unavailable"
        return sample_data.make_news(symbol), "sample"

    def _cache_key(self, kind: str, symbol: str, *parts: object) -> str:
        token_state = "token" if self.finmind.token else "no-token"
        normalized = symbol.upper().strip()
        suffix = ":".join(str(part) for part in parts)
        return f"{MARKET_DATA_CACHE_PREFIX}{kind}:{self.enable_live_data}:{token_state}:{normalized}:{suffix}"

    @staticmethod
    def _cache_ttl() -> int:
        return get_settings().market_data_cache_ttl_seconds


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


def _first_profile_value(profiles: list[dict[str, str | None]], key: str) -> str | None:
    for profile in profiles:
        value = _profile_value(profile, key)
        if value:
            return value
    return None


def _profile_value(profile: dict[str, str | None], key: str) -> str | None:
    text = str(profile.get(key) or "").strip()
    return text or None


def _empty_institutional_flows() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["date", "foreign_net", "investment_trust_net", "dealer_net", "total_net"]
    )


def _empty_margin_balances() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["date", "margin_purchase_balance", "short_sale_balance", "short_margin_ratio"]
    )
