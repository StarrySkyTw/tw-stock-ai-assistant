from app.services.indicators import calculate_indicators, summarize_technical
from app.services.sample_data import make_price_history


def test_calculate_indicators_contains_required_columns():
    prices = make_price_history("2330", years=2)
    df = calculate_indicators(prices)

    for column in ["ma5", "ma20", "ma60", "rsi14", "k", "d", "dif", "macd", "osc", "atr14"]:
        assert column in df.columns
    assert df["ma20"].notna().sum() > 0
    assert df["atr14"].dropna().iloc[-1] > 0


def test_summarize_technical_returns_signals():
    prices = make_price_history("2330", years=2)
    summary = summarize_technical(calculate_indicators(prices))

    assert summary["latest_close"] > 0
    assert "ma20" in summary["ma"]
    assert isinstance(summary["signals"], list)

