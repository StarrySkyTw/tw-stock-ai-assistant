from __future__ import annotations

import asyncio
from datetime import datetime

import httpx
import pandas as pd

from app.services.calendar import TAIPEI_TZ
from app.services.data_providers.base import normalize_price_frame


class YahooProvider:
    chart_url = "https://query2.finance.yahoo.com/v8/finance/chart/{symbol}"

    async def daily_prices(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        for yahoo_symbol in _yahoo_symbols(symbol):
            try:
                async with httpx.AsyncClient(timeout=12, headers={"User-Agent": "stockai/0.1"}) as client:
                    response = await client.get(
                        self.chart_url.format(symbol=yahoo_symbol),
                        params={
                            "period1": _unix_timestamp(start_date),
                            "period2": _unix_timestamp(end_date, include_end=True),
                            "interval": "1d",
                            "events": "history",
                        },
                    )
                    if response.status_code == 404:
                        continue
                    response.raise_for_status()
                frame = parse_yahoo_daily_chart(response.json())
                if len(frame) >= 60:
                    return frame
            except Exception:
                continue
        return await asyncio.to_thread(_download_yfinance_daily_prices, symbol, start_date, end_date)

    async def intraday_prices(self, symbol: str) -> tuple[pd.DataFrame, dict]:
        for yahoo_symbol in _yahoo_symbols(symbol):
            async with httpx.AsyncClient(timeout=15, headers={"User-Agent": "stockai/0.1"}) as client:
                response = await client.get(
                    self.chart_url.format(symbol=yahoo_symbol),
                    params={"range": "1d", "interval": "1m", "includePrePost": "false"},
                )
                if response.status_code == 404:
                    continue
                response.raise_for_status()
            frame, metadata = parse_yahoo_intraday_chart(response.json())
            if not frame.empty:
                return frame, {**metadata, "yahoo_symbol": yahoo_symbol}
        return pd.DataFrame(), {}


def _download_yfinance_daily_prices(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    try:
        import yfinance as yf
    except Exception:
        return pd.DataFrame()
    for yahoo_symbol in _yahoo_symbols(symbol):
        try:
            df = yf.download(yahoo_symbol, start=start_date, end=end_date, progress=False, auto_adjust=False)
        except Exception:
            continue
        if df.empty:
            continue
        df = df.reset_index().rename(
            columns={
                "Date": "date",
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume",
            }
        )
        return normalize_price_frame(df)
    return pd.DataFrame()


def parse_yahoo_daily_chart(payload: dict) -> pd.DataFrame:
    result = ((payload.get("chart") or {}).get("result") or [None])[0]
    if not result:
        return pd.DataFrame()

    timestamps = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    rows = []
    for index, timestamp in enumerate(timestamps):
        close = _series_value(quote.get("close"), index)
        open_price = _series_value(quote.get("open"), index) or close
        high = _series_value(quote.get("high"), index) or close
        low = _series_value(quote.get("low"), index) or close
        if close is None or open_price is None or high is None or low is None:
            continue
        rows.append(
            {
                "date": datetime.fromtimestamp(int(timestamp), tz=TAIPEI_TZ).date(),
                "open": open_price,
                "high": high,
                "low": low,
                "close": close,
                "volume": _series_value(quote.get("volume"), index) or 0,
            }
        )

    return normalize_price_frame(pd.DataFrame(rows))


def parse_yahoo_intraday_chart(payload: dict) -> tuple[pd.DataFrame, dict]:
    result = ((payload.get("chart") or {}).get("result") or [None])[0]
    if not result:
        return pd.DataFrame(), {}

    meta = result.get("meta") or {}
    timestamps = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    rows = []
    for index, timestamp in enumerate(timestamps):
        close = _series_value(quote.get("close"), index)
        open_price = _series_value(quote.get("open"), index) or close
        high = _series_value(quote.get("high"), index) or close
        low = _series_value(quote.get("low"), index) or close
        if close is None or open_price is None or high is None or low is None:
            continue
        rows.append(
            {
                "time": datetime.fromtimestamp(int(timestamp), tz=TAIPEI_TZ),
                "open": open_price,
                "high": high,
                "low": low,
                "close": close,
                "volume": _series_value(quote.get("volume"), index) or 0,
            }
        )

    frame = pd.DataFrame(rows)
    if not frame.empty:
        frame = frame.sort_values("time").reset_index(drop=True)

    metadata = {
        "currency": meta.get("currency"),
        "exchange": meta.get("exchangeName"),
        "regular_market_price": _to_float(meta.get("regularMarketPrice")),
        "previous_close": _to_float(meta.get("chartPreviousClose") or meta.get("previousClose")),
        "regular_market_volume": _to_float(meta.get("regularMarketVolume")),
        "regular_market_time": (
            datetime.fromtimestamp(int(meta["regularMarketTime"]), tz=TAIPEI_TZ)
            if meta.get("regularMarketTime")
            else None
        ),
    }
    return frame, metadata


def _yahoo_symbols(symbol: str) -> list[str]:
    normalized = symbol.upper().strip()
    if "." in normalized or normalized.startswith("^"):
        return [normalized]
    return [f"{normalized}.TW", f"{normalized}.TWO"]


def _unix_timestamp(value: str, *, include_end: bool = False) -> int:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TAIPEI_TZ)
    if include_end:
        parsed = parsed.replace(hour=23, minute=59, second=59)
    return int(parsed.timestamp())


def _series_value(values: object, index: int) -> float | None:
    if not isinstance(values, list) or index >= len(values):
        return None
    return _to_float(values[index])


def _to_float(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return number
