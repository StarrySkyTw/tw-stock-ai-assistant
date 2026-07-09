from __future__ import annotations

from datetime import date, timedelta

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

    async def stock_profile(self, symbol: str) -> dict[str, str | None]:
        df = await self._safe_data("TaiwanStockInfo")
        if df.empty:
            return {"name": None, "industry": None}
        id_column = "stock_id" if "stock_id" in df.columns else "code" if "code" in df.columns else None
        if not id_column:
            return {"name": None, "industry": None}
        matched = df[df[id_column].astype(str).str.strip() == symbol]
        if matched.empty:
            return {"name": None, "industry": None}
        row = matched.iloc[0]
        return {
            "name": _first_text(row, ("stock_name", "name")),
            "industry": _first_text(
                row,
                (
                    "industry_category",
                    "industry",
                    "industry_name",
                    "category",
                    "sector",
                ),
            ),
        }

    async def stock_name(self, symbol: str) -> str | None:
        profile = await self.stock_profile(symbol)
        return profile["name"]

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
        end = date.today()
        per = await self._safe_data(
            "TaiwanStockPER",
            data_id=symbol,
            start_date=(end - timedelta(days=400)).isoformat(),
            end_date=end.isoformat(),
        )
        revenue = await self._safe_data(
            "TaiwanStockMonthRevenue",
            data_id=symbol,
            start_date=(end - timedelta(days=560)).isoformat(),
            end_date=end.isoformat(),
        )
        financial = await self._safe_data(
            "TaiwanStockFinancialStatements",
            data_id=symbol,
            start_date=(end - timedelta(days=1100)).isoformat(),
            end_date=end.isoformat(),
        )
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

    frame = df.copy()
    if "date" not in frame.columns or "value" not in frame.columns:
        return {}
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame = frame.dropna(subset=["date"]).sort_values("date")
    if frame.empty:
        return {}

    period_metrics: dict[pd.Timestamp, dict[str, float]] = {}
    for item in frame.to_dict("records"):
        metric = _financial_metric_key(item)
        value = _to_float(item.get("value"))
        period = item.get("date")
        if metric is None or value is None or not isinstance(period, pd.Timestamp):
            continue
        period_metrics.setdefault(period, {})[metric] = value

    if not period_metrics:
        return {}

    periods = sorted(period_metrics)
    latest = period_metrics[periods[-1]]
    last_four = [period_metrics[period] for period in periods[-4:]]
    eps_ttm = _sum_metric(last_four, "eps")
    net_income_ttm = _sum_metric(last_four, "net_income")
    latest_equity = _latest_metric(period_metrics, periods, "equity")
    revenue = latest.get("revenue")
    gross_profit = latest.get("gross_profit")
    operating_income = latest.get("operating_income")

    return {
        "eps": eps_ttm,
        "roe": _ratio_percent(net_income_ttm, latest_equity),
        "gross_margin": _ratio_percent(gross_profit, revenue),
        "operating_margin": _ratio_percent(operating_income, revenue),
    }


def _financial_metric_key(item: dict) -> str | None:
    labels = " ".join(
        str(item.get(column, ""))
        for column in ("type", "name", "origin_name")
        if item.get(column) is not None
    ).lower()
    compact = labels.replace(" ", "").replace("_", "")
    if "eps" in compact or "基本每股盈餘" in labels or "每股盈餘" in labels:
        return "eps"
    if "grossprofit" in compact or "營業毛利" in labels or "毛利" in labels:
        return "gross_profit"
    if "operatingincome" in compact or "營業利益" in labels:
        return "operating_income"
    if (
        "incomeaftertaxes" in compact
        or "totalconsolidatedprofitfortheperiod" in compact
        or "本期淨利" in labels
        or "母公司業主" in labels
    ):
        return "net_income"
    if "equityattributabletoownersofparent" in compact or "權益總計" in labels or "權益" in labels:
        return "equity"
    if "revenue" in compact or "營業收入" in labels:
        return "revenue"
    return None


def _first_text(row: pd.Series, columns: tuple[str, ...]) -> str | None:
    for column in columns:
        if column not in row.index:
            continue
        value = row[column]
        if pd.isna(value):
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _sum_metric(rows: list[dict[str, float]], metric: str) -> float | None:
    values = [row[metric] for row in rows if metric in row]
    if not values:
        return None
    return sum(values)


def _latest_metric(
    period_metrics: dict[pd.Timestamp, dict[str, float]],
    periods: list[pd.Timestamp],
    metric: str,
) -> float | None:
    for period in reversed(periods):
        value = period_metrics[period].get(metric)
        if value is None:
            continue
        return value
    return None


def _ratio_percent(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return round(numerator / denominator * 100, 2)
