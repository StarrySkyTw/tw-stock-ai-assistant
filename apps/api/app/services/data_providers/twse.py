from __future__ import annotations

from datetime import date, datetime

import httpx
import pandas as pd

from app.services.data_providers.base import normalize_price_frame


class TwseProvider:
    base_url = "https://openapi.twse.com.tw/v1"
    realtime_url = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp"

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

    async def realtime_quote(self, symbol: str) -> pd.DataFrame:
        normalized_symbol = symbol.upper().strip()
        if not normalized_symbol.isdigit():
            return pd.DataFrame()

        async with httpx.AsyncClient(timeout=8, headers={"User-Agent": "stockai/0.1"}) as client:
            for exchange in ("tse", "otc"):
                response = await client.get(
                    self.realtime_url,
                    params={
                        "ex_ch": f"{exchange}_{normalized_symbol}.tw",
                        "json": "1",
                        "delay": "0",
                        "_": str(int(datetime.now().timestamp() * 1000)),
                    },
                )
                response.raise_for_status()
                quote = _extract_quote(response.json())
                if quote is not None:
                    return normalize_price_frame(pd.DataFrame([quote]))
        return pd.DataFrame()


def _extract_quote(payload: dict) -> dict | None:
    rows = payload.get("msgArray") or []
    if not rows:
        return None

    row = rows[0]
    close = _to_float(row.get("z")) or _to_float(row.get("pz")) or _to_float(row.get("y"))
    quote_date = _parse_market_date(row.get("d") or row.get("^"))
    if close is None or quote_date is None:
        return None

    open_price = _to_float(row.get("o")) or close
    high_price = _to_float(row.get("h")) or max(open_price, close)
    low_price = _to_float(row.get("l")) or min(open_price, close)
    volume = _to_float(row.get("v")) or 0.0

    return {
        "date": quote_date,
        "open": open_price,
        "high": max(high_price, open_price, close),
        "low": min(low_price, open_price, close),
        "close": close,
        "volume": volume * 1000,
    }


def _parse_market_date(value: object) -> date | None:
    text = str(value or "").strip()
    try:
        if len(text) == 8:
            return date(int(text[:4]), int(text[4:6]), int(text[6:8]))
        if len(text) == 7:
            return date(int(text[:3]) + 1911, int(text[3:5]), int(text[5:7]))
    except ValueError:
        return None
    return None


def _to_float(value: object) -> float | None:
    text = str(value or "").strip().replace(",", "")
    if text in {"", "-", "--"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None
