import pandas as pd
import pytest


@pytest.mark.asyncio
async def test_market_data_prices_cache_returns_copy(monkeypatch):
    from app.core.config import get_settings
    from app.services.data_providers.composite import MarketDataService, clear_market_data_cache

    monkeypatch.setenv("ENABLE_LIVE_DATA", "true")
    monkeypatch.setenv("MARKET_DATA_CACHE_TTL_SECONDS", "30")
    get_settings.cache_clear()
    clear_market_data_cache()

    calls = 0

    class FakeFinMind:
        token = "fake-token"

        async def daily_prices(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
            nonlocal calls
            calls += 1
            dates = pd.date_range("2026-01-01", periods=90, freq="D")
            return pd.DataFrame(
                {
                    "date": dates.date,
                    "open": range(90),
                    "high": range(1, 91),
                    "low": range(90),
                    "close": range(2, 92),
                    "volume": [1000] * 90,
                }
            )

    class FakeYahoo:
        async def daily_prices(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
            return pd.DataFrame()

    class FakeTwse:
        async def realtime_quote(self, symbol: str) -> pd.DataFrame:
            return pd.DataFrame()

    service = MarketDataService()
    service.finmind = FakeFinMind()
    service.yahoo = FakeYahoo()
    service.twse = FakeTwse()

    first, first_source = await service.prices("2330", years=1)
    first.loc[first.index[-1], "close"] = 0
    second, second_source = await service.prices("2330", years=1)

    assert first_source == "finmind"
    assert second_source == "finmind"
    assert calls == 1
    assert second.iloc[-1]["close"] == 91


@pytest.mark.asyncio
async def test_market_data_stock_profile_resolves_live_industry(monkeypatch):
    from app.core.config import get_settings
    from app.services.data_providers.composite import MarketDataService, clear_market_data_cache

    monkeypatch.setenv("ENABLE_LIVE_DATA", "true")
    monkeypatch.setenv("MARKET_DATA_CACHE_TTL_SECONDS", "30")
    get_settings.cache_clear()
    clear_market_data_cache()

    calls = 0

    class FakeFinMind:
        token = None

        async def stock_profile(self, symbol: str) -> dict[str, str | None]:
            nonlocal calls
            calls += 1
            return {"name": "未收錄公司", "industry": "電腦及週邊設備業"}

    service = MarketDataService()
    service.finmind = FakeFinMind()

    first = await service.stock_profile("9999")
    second = await service.stock_profile("9999")

    assert first == {"name": "未收錄公司", "industry": "電腦及週邊設備"}
    assert second == {"name": "未收錄公司", "industry": "電腦及週邊設備"}
    assert calls == 1


@pytest.mark.asyncio
async def test_market_data_stock_profile_falls_back_to_twse_profile(monkeypatch):
    from app.core.config import get_settings
    from app.services.data_providers.composite import MarketDataService, clear_market_data_cache

    monkeypatch.setenv("ENABLE_LIVE_DATA", "true")
    monkeypatch.setenv("MARKET_DATA_CACHE_TTL_SECONDS", "30")
    get_settings.cache_clear()
    clear_market_data_cache()

    class FakeFinMind:
        token = None

        async def stock_profile(self, symbol: str) -> dict[str, str | None]:
            return {"name": None, "industry": None}

    class FakeTwse:
        async def stock_profile(self, symbol: str) -> dict[str, str | None]:
            return {"name": "營邦", "industry": "電腦及週邊設備業"}

    service = MarketDataService()
    service.finmind = FakeFinMind()
    service.twse = FakeTwse()

    assert await service.stock_profile("3693") == {"name": "營邦", "industry": "電腦及週邊設備"}


@pytest.mark.asyncio
async def test_market_data_live_optional_sources_do_not_return_sample(monkeypatch):
    from app.core.config import get_settings
    from app.services.data_providers.base import FundamentalData, ShareholdingData
    from app.services.data_providers.composite import MarketDataService, clear_market_data_cache

    monkeypatch.setenv("ENABLE_LIVE_DATA", "true")
    monkeypatch.setenv("MARKET_DATA_CACHE_TTL_SECONDS", "30")
    get_settings.cache_clear()
    clear_market_data_cache()

    class FakeFinMind:
        token = None

        async def institutional_flows(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
            return pd.DataFrame()

        async def fundamentals(self, symbol: str) -> FundamentalData:
            return FundamentalData()

        async def margin_balances(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
            return pd.DataFrame()

        async def shareholding(self, symbol: str) -> ShareholdingData:
            return ShareholdingData()

        async def news(self, symbol: str) -> list[dict]:
            return []

    class FakeTwse:
        async def institutional_flows_with_source(self, symbol: str, start_date: str, end_date: str) -> tuple[pd.DataFrame, str]:
            return pd.DataFrame(), "unavailable"

        async def fundamentals_with_source(self, symbol: str) -> tuple[FundamentalData, str]:
            return FundamentalData(), "unavailable"

        async def margin_balances_with_source(self, symbol: str, start_date: str, end_date: str) -> tuple[pd.DataFrame, str]:
            return pd.DataFrame(), "unavailable"

    service = MarketDataService()
    service.finmind = FakeFinMind()
    service.twse = FakeTwse()

    _, institutional_source = await service.institutional_flows("9999")
    fundamentals, fundamental_source = await service.fundamentals("9999")
    _, margin_source = await service.margin_balances("9999")
    shareholding, shareholding_source = await service.shareholding("9999")
    news, news_source = await service.news("9999")

    assert institutional_source == "unavailable"
    assert fundamental_source == "unavailable"
    assert fundamentals["eps"] is None
    assert margin_source == "unavailable"
    assert shareholding_source == "unavailable"
    assert shareholding["large_holder_ratio"] is None
    assert news_source == "unavailable"
    assert news == []


@pytest.mark.asyncio
async def test_market_data_live_uses_official_sources_when_finmind_is_empty(monkeypatch):
    from app.core.config import get_settings
    from app.services.data_providers.base import FundamentalData
    from app.services.data_providers.composite import MarketDataService, clear_market_data_cache

    monkeypatch.setenv("ENABLE_LIVE_DATA", "true")
    monkeypatch.setenv("MARKET_DATA_CACHE_TTL_SECONDS", "30")
    get_settings.cache_clear()
    clear_market_data_cache()

    class FakeFinMind:
        token = None

        async def institutional_flows(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
            return pd.DataFrame()

        async def fundamentals(self, symbol: str) -> FundamentalData:
            return FundamentalData()

        async def margin_balances(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
            return pd.DataFrame()

    class FakeTwse:
        async def institutional_flows_with_source(self, symbol: str, start_date: str, end_date: str) -> tuple[pd.DataFrame, str]:
            dates = pd.date_range("2026-01-01", periods=5, freq="B")
            return (
                pd.DataFrame(
                    {
                        "date": dates.date,
                        "foreign_net": [1000] * 5,
                        "investment_trust_net": [100] * 5,
                        "dealer_net": [50] * 5,
                        "total_net": [1150] * 5,
                    }
                ),
                "twse-t86",
            )

        async def fundamentals_with_source(self, symbol: str) -> tuple[FundamentalData, str]:
            return (
                FundamentalData(eps=2.1, roe=12.0, operating_margin=18.5, pe_ratio=16.0, pb_ratio=1.9, revenue_yoy=11.2),
                "twse-openapi",
            )

        async def margin_balances_with_source(self, symbol: str, start_date: str, end_date: str) -> tuple[pd.DataFrame, str]:
            dates = pd.date_range("2026-01-01", periods=5, freq="B")
            return (
                pd.DataFrame(
                    {
                        "date": dates.date,
                        "margin_purchase_balance": [1000, 990, 980, 970, 960],
                        "short_sale_balance": [30, 30, 25, 24, 20],
                        "short_margin_ratio": [3.0, 3.03, 2.55, 2.47, 2.08],
                    }
                ),
                "twse-margin",
            )

    service = MarketDataService()
    service.finmind = FakeFinMind()
    service.twse = FakeTwse()

    _, institutional_source = await service.institutional_flows("2330")
    fundamentals, fundamental_source = await service.fundamentals("2330")
    _, margin_source = await service.margin_balances("2330")

    assert institutional_source == "twse-t86"
    assert fundamental_source == "twse-openapi"
    assert fundamentals["revenue_yoy"] == 11.2
    assert margin_source == "twse-margin"


@pytest.mark.asyncio
async def test_market_data_live_uses_official_shareholding_and_events_when_finmind_is_empty(monkeypatch):
    from app.core.config import get_settings
    from app.services.data_providers.base import ShareholdingData
    from app.services.data_providers.composite import MarketDataService, clear_market_data_cache

    monkeypatch.setenv("ENABLE_LIVE_DATA", "true")
    monkeypatch.setenv("MARKET_DATA_CACHE_TTL_SECONDS", "30")
    get_settings.cache_clear()
    clear_market_data_cache()

    class FakeFinMind:
        token = None

        async def shareholding(self, symbol: str) -> ShareholdingData:
            return ShareholdingData()

        async def news(self, symbol: str) -> list[dict]:
            return []

    class FakeTwse:
        async def shareholding_with_source(self, symbol: str) -> tuple[ShareholdingData, str]:
            return ShareholdingData(large_holder_ratio=62.4, shareholder_count=930000), "tdcc"

        async def material_events_with_source(self, symbol: str) -> tuple[list[dict], str]:
            return (
                [
                    {
                        "published_at": "2026-06-29",
                        "title": "公告本公司重大訊息",
                        "source": "twse-material",
                        "url": "https://mops.twse.com.tw/mops/web/t05st02",
                    }
                ],
                "twse-material",
            )

    service = MarketDataService()
    service.finmind = FakeFinMind()
    service.twse = FakeTwse()

    shareholding, shareholding_source = await service.shareholding("2330")
    news, news_source = await service.news("2330")

    assert shareholding_source == "tdcc"
    assert shareholding["large_holder_ratio"] == 62.4
    assert shareholding["shareholder_count"] == 930000
    assert news_source == "twse-material"
    assert news[0]["title"] == "公告本公司重大訊息"


@pytest.mark.asyncio
async def test_market_data_live_prefers_official_fundamentals_over_public_finmind(monkeypatch):
    from app.core.config import get_settings
    from app.services.data_providers.base import FundamentalData
    from app.services.data_providers.composite import MarketDataService, clear_market_data_cache

    monkeypatch.setenv("ENABLE_LIVE_DATA", "true")
    monkeypatch.setenv("MARKET_DATA_CACHE_TTL_SECONDS", "30")
    get_settings.cache_clear()
    clear_market_data_cache()

    class FakeFinMind:
        token = None

        async def fundamentals(self, symbol: str) -> FundamentalData:
            return FundamentalData(eps=99, roe=9999, pe_ratio=1, revenue_yoy=2026)

    class FakeTwse:
        async def fundamentals_with_source(self, symbol: str) -> tuple[FundamentalData, str]:
            return (
                FundamentalData(eps=2.1, roe=12.0, operating_margin=18.5, pe_ratio=16.0, pb_ratio=1.9, revenue_yoy=11.2),
                "twse-openapi",
            )

    service = MarketDataService()
    service.finmind = FakeFinMind()
    service.twse = FakeTwse()

    fundamentals, source = await service.fundamentals("2330")

    assert source == "twse-openapi"
    assert fundamentals["eps"] == 2.1
    assert fundamentals["revenue_yoy"] == 11.2
