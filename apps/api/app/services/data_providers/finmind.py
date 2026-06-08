from __future__ import annotations

import httpx
import pandas as pd

from app.services.data_providers.base import FundamentalData, ShareholdingData, normalize_price_frame


class FinMindProvider:
    base_url = "https://api.finmindtrade.com/api/v4"

    def __init__(self, token: str | None = None, timeout: float = 15) -> None:
        self.token = token
        self.timeout = timeout

    async def _data(self, dataset: str, **params: str) -> pd.DataFrame:
        query = {"dataset": dataset, **params}
        if self.token:
            query["token"] = self.token
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}/data", params=query)
            response.raise_for_status()
            payload = response.json()
        data = payload.get("data", [])
        return pd.DataFrame(data)

    async def daily_prices(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        df = await self._data(
            "TaiwanStockPrice", data_id=symbol, start_date=start_date, end_date=end_date
        )
        return normalize_price_frame(df)

    async def stock_name(self, symbol: str) -> str | None:
        df = await self._safe_data("TaiwanStockInfo")
        if df.empty:
            return None
        id_column = "stock_id" if "stock_id" in df.columns else "code" if "code" in df.columns else None
        name_column = "stock_name" if "stock_name" in df.columns else "name" if "name" in df.columns else None
        if not id_column or not name_column:
            return None
        matched = df[df[id_column].astype(str).str.strip() == symbol]
        if matched.empty:
            return None
        return str(matched.iloc[0][name_column])

    async def institutional_flows(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        df = await self._data(
            "TaiwanStockInstitutionalInvestorsBuySell",
            data_id=symbol,
            start_date=start_date,
            end_date=end_date,
        )
        if df.empty:
            return df
        df = df.rename(columns={"stock_id": "symbol"})
        for column in ["buy", "sell"]:
            df[column] = pd.to_numeric(df.get(column, 0), errors="coerce").fillna(0)
        df["net"] = df["buy"] - df["sell"]
        name_col = "name" if "name" in df.columns else "type"

        def pick(group: pd.DataFrame, keyword: str) -> float:
            mask = group[name_col].astype(str).str.contains(keyword, case=False, na=False)
            return float(group.loc[mask, "net"].sum())

        rows = []
        for trade_date, group in df.groupby("date"):
            foreign = pick(group, "Foreign|外資")
            trust = pick(group, "Investment|投信")
            dealer = pick(group, "Dealer|自營")
            rows.append(
                {
                    "date": pd.to_datetime(trade_date).date(),
                    "foreign_net": foreign,
                    "investment_trust_net": trust,
                    "dealer_net": dealer,
                    "total_net": foreign + trust + dealer,
                }
            )
        return pd.DataFrame(rows).sort_values("date").reset_index(drop=True)

    async def fundamentals(self, symbol: str) -> FundamentalData:
        per = await self._safe_data("TaiwanStockPER", data_id=symbol)
        revenue = await self._safe_data("TaiwanStockMonthRevenue", data_id=symbol)
        financial = await self._safe_data("TaiwanStockFinancialStatements", data_id=symbol)
        latest_per = per.tail(1).to_dict("records")[0] if not per.empty else {}
        latest_revenue = revenue.tail(1).to_dict("records")[0] if not revenue.empty else {}
        metrics = _extract_financial_metrics(financial)
        return FundamentalData(
            eps=_to_float(metrics.get("eps")),
            roe=_to_float(metrics.get("roe")),
            gross_margin=_to_float(metrics.get("gross_margin")),
            operating_margin=_to_float(metrics.get("operating_margin")),
            pe_ratio=_to_float(latest_per.get("PER") or latest_per.get("pe_ratio")),
            pb_ratio=_to_float(latest_per.get("PBR") or latest_per.get("pb_ratio")),
            revenue_yoy=_to_float(latest_revenue.get("revenue_year") or latest_revenue.get("revenue_yoy")),
            revenue_mom=_to_float(latest_revenue.get("revenue_month") or latest_revenue.get("revenue_mom")),
        )

    async def margin_balances(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        df = await self._safe_data(
            "TaiwanStockMarginPurchaseShortSale",
            data_id=symbol,
            start_date=start_date,
            end_date=end_date,
        )
        if df.empty:
            return df
        out = pd.DataFrame(
            {
                "date": pd.to_datetime(df["date"]).dt.date,
                "margin_purchase_balance": pd.to_numeric(
                    df.get("MarginPurchaseTodayBalance", df.get("margin_purchase_balance", 0)),
                    errors="coerce",
                ),
                "short_sale_balance": pd.to_numeric(
                    df.get("ShortSaleTodayBalance", df.get("short_sale_balance", 0)),
                    errors="coerce",
                ),
            }
        )
        out["short_margin_ratio"] = (
            out["short_sale_balance"] / out["margin_purchase_balance"].replace(0, pd.NA) * 100
        )
        return out.sort_values("date").reset_index(drop=True)

    async def shareholding(self, symbol: str) -> ShareholdingData:
        df = await self._safe_data("TaiwanStockHoldingSharesPer", data_id=symbol)
        if df.empty:
            return ShareholdingData()
        latest = df.tail(1).to_dict("records")[0]
        return ShareholdingData(
            large_holder_ratio=_to_float(
                latest.get("HoldingSharesLevel") or latest.get("holding_per") or latest.get("percent")
            ),
            shareholder_count=int(_to_float(latest.get("people")) or 0) or None,
        )

    async def news(self, symbol: str) -> list[dict]:
        df = await self._safe_data("TaiwanStockNews", data_id=symbol)
        if df.empty:
            return []
        rows = []
        for item in df.tail(10).to_dict("records"):
            rows.append(
                {
                    "published_at": str(item.get("date", "")),
                    "title": str(item.get("title", "")),
                    "source": "finmind",
                    "url": str(item.get("link", "")),
                }
            )
        return rows

    async def _safe_data(self, dataset: str, **params: str) -> pd.DataFrame:
        try:
            return await self._data(dataset, **params)
        except Exception:
            return pd.DataFrame()


def _to_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_financial_metrics(df: pd.DataFrame) -> dict[str, float | None]:
    if df.empty:
        return {}
    records = df.tail(80).to_dict("records")
    values: dict[str, float | None] = {}
    for item in records:
        key = str(item.get("type", item.get("name", ""))).lower()
        value = _to_float(item.get("value"))
        if value is None:
            continue
        if "eps" in key or "每股" in key:
            values["eps"] = value
        elif "roe" in key or "權益報酬" in key:
            values["roe"] = value
        elif "gross" in key or "毛利" in key:
            values["gross_margin"] = value
        elif "operating" in key or "營業利益率" in key:
            values["operating_margin"] = value
    return values
