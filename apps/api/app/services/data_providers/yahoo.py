from __future__ import annotations

import pandas as pd

from app.services.data_providers.base import normalize_price_frame


class YahooProvider:
    async def daily_prices(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        try:
            import yfinance as yf
        except Exception:
            return pd.DataFrame()
        yahoo_symbol = symbol if "." in symbol or symbol.startswith("^") else f"{symbol}.TW"
        df = yf.download(yahoo_symbol, start=start_date, end=end_date, progress=False, auto_adjust=False)
        if df.empty:
            yahoo_symbol = f"{symbol}.TWO"
            df = yf.download(yahoo_symbol, start=start_date, end=end_date, progress=False, auto_adjust=False)
        if df.empty:
            return df
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

