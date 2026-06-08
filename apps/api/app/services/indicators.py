from __future__ import annotations

import numpy as np
import pandas as pd

MA_WINDOWS = [5, 10, 20, 60, 120, 240]


def calculate_indicators(prices: pd.DataFrame) -> pd.DataFrame:
    df = prices.copy().sort_values("date").reset_index(drop=True)
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    for window in MA_WINDOWS:
        df[f"ma{window}"] = df["close"].rolling(window).mean()

    df["rsi6"] = _rsi(df["close"], 6)
    df["rsi14"] = _rsi(df["close"], 14)

    low9 = df["low"].rolling(9).min()
    high9 = df["high"].rolling(9).max()
    rsv = (df["close"] - low9) / (high9 - low9) * 100
    df["k"] = rsv.ewm(alpha=1 / 3, adjust=False).mean()
    df["d"] = df["k"].ewm(alpha=1 / 3, adjust=False).mean()

    ema12 = df["close"].ewm(span=12, adjust=False).mean()
    ema26 = df["close"].ewm(span=26, adjust=False).mean()
    df["dif"] = ema12 - ema26
    df["macd"] = df["dif"].ewm(span=9, adjust=False).mean()
    df["osc"] = df["dif"] - df["macd"]

    mid = df["close"].rolling(20).mean()
    std = df["close"].rolling(20).std()
    df["bb_mid"] = mid
    df["bb_upper"] = mid + 2 * std
    df["bb_lower"] = mid - 2 * std
    df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / mid

    prev_close = df["close"].shift(1)
    true_range = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    df["atr14"] = true_range.rolling(14).mean()
    df["volume_ma20"] = df["volume"].rolling(20).mean()
    df["volume_ratio"] = df["volume"] / df["volume_ma20"]
    return df


def _rsi(series: pd.Series, window: int) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def latest_number(row: pd.Series, key: str) -> float | None:
    value = row.get(key)
    if value is None or pd.isna(value):
        return None
    return round(float(value), 4)


def detect_cross(df: pd.DataFrame, fast: str, slow: str) -> str | None:
    if len(df) < 2:
        return None
    prev = df.iloc[-2]
    latest = df.iloc[-1]
    if pd.isna(prev[fast]) or pd.isna(prev[slow]) or pd.isna(latest[fast]) or pd.isna(latest[slow]):
        return None
    if prev[fast] <= prev[slow] and latest[fast] > latest[slow]:
        return "golden_cross"
    if prev[fast] >= prev[slow] and latest[fast] < latest[slow]:
        return "death_cross"
    return None


def summarize_technical(indicator_df: pd.DataFrame) -> dict:
    latest = indicator_df.iloc[-1]
    signals: list[str] = []
    ma_values = {f"ma{w}": latest_number(latest, f"ma{w}") for w in MA_WINDOWS}
    ordered = [ma_values[f"ma{w}"] for w in [5, 10, 20, 60]]
    if all(value is not None for value in ordered):
        if ordered == sorted(ordered, reverse=True):
            signals.append("均線多頭排列")
            trend = "bullish"
        elif ordered == sorted(ordered):
            signals.append("均線空頭排列")
            trend = "bearish"
        else:
            trend = "sideways"
    else:
        trend = "insufficient_data"

    ma_cross = detect_cross(indicator_df, "ma5", "ma20")
    if ma_cross == "golden_cross":
        signals.append("MA5 上穿 MA20 黃金交叉")
    elif ma_cross == "death_cross":
        signals.append("MA5 下穿 MA20 死亡交叉")

    kd_cross = detect_cross(indicator_df, "k", "d")
    if kd_cross == "golden_cross":
        signals.append("KD 黃金交叉")
    elif kd_cross == "death_cross":
        signals.append("KD 死亡交叉")

    if latest_number(latest, "rsi14") is not None:
        if latest["rsi14"] >= 70:
            signals.append("RSI14 超買")
        elif latest["rsi14"] <= 30:
            signals.append("RSI14 超賣")

    if latest_number(latest, "osc") is not None:
        signals.append("MACD 柱狀體轉強" if latest["osc"] > 0 else "MACD 柱狀體偏弱")

    if latest_number(latest, "bb_upper") is not None and latest["close"] > latest["bb_upper"]:
        signals.append("價格突破布林上軌")
    if latest_number(latest, "bb_lower") is not None and latest["close"] < latest["bb_lower"]:
        signals.append("價格跌破布林下軌")
    if latest_number(latest, "bb_width") is not None and latest["bb_width"] < 0.08:
        signals.append("布林通道壓縮")
    if latest_number(latest, "volume_ratio") is not None and latest["volume_ratio"] >= 1.8:
        signals.append("成交量放大")

    return {
        "latest_close": float(latest["close"]),
        "ma": ma_values,
        "rsi": {"rsi6": latest_number(latest, "rsi6"), "rsi14": latest_number(latest, "rsi14")},
        "kd": {"k": latest_number(latest, "k"), "d": latest_number(latest, "d")},
        "macd": {
            "dif": latest_number(latest, "dif"),
            "macd": latest_number(latest, "macd"),
            "osc": latest_number(latest, "osc"),
        },
        "bollinger": {
            "upper": latest_number(latest, "bb_upper"),
            "middle": latest_number(latest, "bb_mid"),
            "lower": latest_number(latest, "bb_lower"),
            "width": latest_number(latest, "bb_width"),
        },
        "atr14": latest_number(latest, "atr14"),
        "volume_ratio": latest_number(latest, "volume_ratio"),
        "trend": trend,
        "signals": signals,
    }
