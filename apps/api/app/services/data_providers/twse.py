from __future__ import annotations

import httpx
import pandas as pd

from app.services.data_providers.base import normalize_price_frame


class TwseProvider:
    base_url = "https://openapi.twse.com.tw/v1"

    async def daily_prices(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        # TWSE OpenAPI is primarily a daily snapshot source; it is used as fallback/cross-check.
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(f"{self.base_url}/exchangeReport/STOCK_DAY_ALL")
            response.raise_for_status()
            rows = response.json()
        df = pd.DataFrame(rows)
        if df.empty:
            return df
        id_col = "Code" if "Code" in df.columns else "證券代號"
        matched = df[df[id_col].astype(str).str.strip() == symbol].copy()
        if matched.empty:
            return matched
        date_value = pd.to_datetime(end_date).date()
        out = pd.DataFrame(
            {
                "date": [date_value],
                "open": [matched.iloc[0].get("OpeningPrice", matched.iloc[0].get("開盤價"))],
                "high": [matched.iloc[0].get("HighestPrice", matched.iloc[0].get("最高價"))],
                "low": [matched.iloc[0].get("LowestPrice", matched.iloc[0].get("最低價"))],
                "close": [matched.iloc[0].get("ClosingPrice", matched.iloc[0].get("收盤價"))],
                "volume": [matched.iloc[0].get("TradeVolume", matched.iloc[0].get("成交股數"))],
            }
        )
        for column in ["open", "high", "low", "close", "volume"]:
            out[column] = pd.to_numeric(out[column].astype(str).str.replace(",", ""), errors="coerce")
        return normalize_price_frame(out)

