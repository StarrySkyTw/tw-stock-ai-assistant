import pandas as pd
import pytest

from app.services.data_providers.finmind import FinMindProvider, _extract_financial_metrics


def test_finmind_financial_statement_metrics_parse_type_and_origin_name():
    rows = []
    for date_text, eps, net_income in [
        ("2025-03-31", 1.0, 100.0),
        ("2025-06-30", 1.2, 120.0),
        ("2025-09-30", 1.4, 140.0),
        ("2025-12-31", 1.6, 160.0),
    ]:
        rows.extend(
            [
                {"date": date_text, "type": "EPS", "origin_name": "基本每股盈餘", "value": eps},
                {"date": date_text, "type": "IncomeAfterTaxes", "origin_name": "本期淨利", "value": net_income},
            ]
        )
    rows.extend(
        [
            {"date": "2025-12-31", "type": "Revenue", "origin_name": "營業收入", "value": 1000.0},
            {"date": "2025-12-31", "type": "GrossProfit", "origin_name": "營業毛利", "value": 450.0},
            {"date": "2025-12-31", "type": "OperatingIncome", "origin_name": "營業利益", "value": 260.0},
            {
                "date": "2025-12-31",
                "type": "EquityAttributableToOwnersOfParent",
                "origin_name": "權益總計",
                "value": 2000.0,
            },
        ]
    )

    metrics = _extract_financial_metrics(pd.DataFrame(rows))

    assert metrics["eps"] == 5.2
    assert metrics["roe"] == 26.0
    assert metrics["gross_margin"] == 45.0
    assert metrics["operating_margin"] == 26.0


async def test_finmind_fundamentals_query_fundamental_datasets_with_date_ranges():
    provider = CapturingFinMindProvider()

    data = await provider.fundamentals("2330")

    assert data.pe_ratio == 18
    assert data.pb_ratio == 2.4
    assert data.revenue_yoy == 12.5
    assert data.revenue_mom == 3.1
    for dataset in ["TaiwanStockPER", "TaiwanStockMonthRevenue", "TaiwanStockFinancialStatements"]:
        params = provider.calls[dataset]
        assert params["data_id"] == "2330"
        assert params["start_date"]
        assert params["end_date"]


@pytest.mark.asyncio
async def test_finmind_stock_profile_reads_industry_category():
    provider = StockInfoFinMindProvider()

    profile = await provider.stock_profile("6451")

    assert provider.calls["TaiwanStockInfo"] == {}
    assert profile == {"name": "訊芯-KY", "industry": "半導體業"}


class CapturingFinMindProvider(FinMindProvider):
    def __init__(self) -> None:
        super().__init__(token=None)
        self.calls: dict[str, dict[str, str]] = {}

    async def _safe_data(self, dataset: str, **params: str) -> pd.DataFrame:
        self.calls[dataset] = params
        if dataset == "TaiwanStockPER":
            return pd.DataFrame([{"date": "2026-06-01", "PER": 18, "PBR": 2.4}])
        if dataset == "TaiwanStockMonthRevenue":
            return pd.DataFrame([{"date": "2026-05-01", "revenue_year": 12.5, "revenue_month": 3.1}])
        if dataset == "TaiwanStockFinancialStatements":
            return pd.DataFrame(
                [
                    {"date": "2026-03-31", "type": "EPS", "origin_name": "基本每股盈餘", "value": 2.1},
                    {"date": "2026-03-31", "type": "Revenue", "origin_name": "營業收入", "value": 1000},
                    {"date": "2026-03-31", "type": "GrossProfit", "origin_name": "營業毛利", "value": 420},
                    {"date": "2026-03-31", "type": "OperatingIncome", "origin_name": "營業利益", "value": 240},
                    {"date": "2026-03-31", "type": "IncomeAfterTaxes", "origin_name": "本期淨利", "value": 190},
                    {"date": "2026-03-31", "type": "Equity", "origin_name": "權益總計", "value": 1800},
                ]
            )
        return pd.DataFrame()


class StockInfoFinMindProvider(FinMindProvider):
    def __init__(self) -> None:
        super().__init__(token=None)
        self.calls: dict[str, dict[str, str]] = {}

    async def _safe_data(self, dataset: str, **params: str) -> pd.DataFrame:
        self.calls[dataset] = params
        if dataset == "TaiwanStockInfo":
            return pd.DataFrame(
                [
                    {
                        "stock_id": "6451",
                        "stock_name": "訊芯-KY",
                        "industry_category": "半導體業",
                    }
                ]
            )
        return pd.DataFrame()
