import pandas as pd
from fastapi.testclient import TestClient


def test_normalize_price_frame_flattens_yahoo_multiindex():
    from app.services.data_providers.base import normalize_price_frame

    frame = pd.DataFrame(
        {
            ("Date", ""): ["2026-06-01", "2026-06-02"],
            ("Open", "2330.TW"): [100, 101],
            ("High", "2330.TW"): [103, 104],
            ("Low", "2330.TW"): [99, 100],
            ("Close", "2330.TW"): [102, 103],
            ("Volume", "2330.TW"): [1000, 1200],
        }
    )

    normalized = normalize_price_frame(frame)

    assert list(normalized.columns) == ["date", "open", "high", "low", "close", "volume"]
    assert normalized["close"].tolist() == [102, 103]


def test_merge_realtime_quote_replaces_or_appends_latest_row():
    from app.services.data_providers.composite import merge_realtime_quote

    history = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-06-08", "2026-06-09"]).date,
            "open": [100, 101],
            "high": [104, 105],
            "low": [99, 100],
            "close": [103, 102],
            "volume": [1000, 1200],
        }
    )
    same_day_quote = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-06-09"]).date,
            "open": [101],
            "high": [108],
            "low": [100],
            "close": [107],
            "volume": [3000],
        }
    )
    next_day_quote = same_day_quote.assign(date=pd.to_datetime(["2026-06-10"]).date, close=[109])
    stale_quote = same_day_quote.assign(date=pd.to_datetime(["2026-06-07"]).date, close=[98])

    replaced = merge_realtime_quote(history, same_day_quote)
    appended = merge_realtime_quote(history, next_day_quote)
    stale = merge_realtime_quote(history, stale_quote)

    assert len(replaced) == 2
    assert replaced.iloc[-1]["close"] == 107
    assert len(appended) == 3
    assert appended.iloc[-1]["close"] == 109
    assert stale.equals(history)


def test_health_endpoint():
    from app.main import app

    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_analysis_endpoint_smoke():
    from app.main import app

    client = TestClient(app)
    response = client.get("/api/v1/stocks/2330/analysis")

    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "2330"
    assert "recommendation" in body
    assert body["generated_at"]
    assert body["refresh"]["timezone"] == "Asia/Taipei"
    assert body["refresh"]["refresh_interval_seconds"] > 0
    assert body["data_sources"]["price"] == "sample"
    assert body["data_sources"]["news"] == "sample"
    assert body["margin"]["signals"]
    assert body["strategy_judgement"]["checks"]
    assert body["strategy_judgement"]["timing_score"] >= 0
    assert body["decision_plan"]["checklist"]["進場條件"]
    assert body["decision_plan"]["scenarios"]


def test_ai_picks_endpoint_smoke():
    from app.main import app

    client = TestClient(app)
    response = client.get("/api/v1/market/ai-picks?universe=2330,2454&limit=1&min_score=0")

    assert response.status_code == 200
    body = response.json()
    assert body["market_snapshot"]["status"]
    assert body["market_snapshot"]["market_date"]
    assert body["refresh"]["timezone"] == "Asia/Taipei"
    assert body["market_snapshot"]["refresh"]["refresh_interval_seconds"] > 0
    assert body["selection_logic"]
    assert body["top_picks"]
    assert body["top_picks"][0]["rank"] == 1
    assert body["top_picks"][0]["bullish_factors"]
    assert body["top_picks"][0]["strategy_judgement"]["headline"]


def test_ai_picks_endpoint_uses_default_universe():
    from app.main import app

    client = TestClient(app)
    response = client.get("/api/v1/market/ai-picks?limit=3&min_score=0")

    assert response.status_code == 200
    body = response.json()
    assert len(body["universe"]) > 8
    assert len(body["top_picks"]) == 3


def test_watchlist_create_is_idempotent():
    from app.main import app

    with TestClient(app) as client:
        first = client.post("/api/v1/watchlist", json={"symbol": "2330"})
        second = client.post("/api/v1/watchlist", json={"symbol": "2330"})
        response = client.get("/api/v1/watchlist")

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["id"] == second.json()["id"]
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_positions_crud_and_idempotent_open_position():
    from app.main import app

    with TestClient(app) as client:
        first = client.post(
            "/api/v1/positions",
            json={"symbol": "2454", "entry_price": 800, "quantity": 10, "highest_price": 920},
        )
        second = client.post(
            "/api/v1/positions",
            json={"symbol": "2454", "entry_price": 810, "quantity": 12, "highest_price": 930},
        )
        listed = client.get("/api/v1/positions")

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    with TestClient(app) as client:
        closed = client.delete(f"/api/v1/positions/{first.json()['id']}")

    assert first.json()["id"] == second.json()["id"]
    assert second.json()["entry_price"] == 810
    assert listed.status_code == 200
    assert any(item["symbol"] == "2454" and item["status"] == "open" for item in listed.json())
    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"


def test_daily_job_includes_open_position_alerts():
    from app.main import app

    with TestClient(app) as client:
        created = client.post(
            "/api/v1/positions",
            json={"symbol": "2317", "entry_price": 120, "quantity": 5, "highest_price": 150},
        )
        response = client.post("/api/v1/jobs/daily-after-close")

    assert created.status_code == 200
    assert response.status_code == 200
    body = response.json()
    assert body["position_alerts"]
    assert any(alert["symbol"] == "2317" for alert in body["position_alerts"])


def test_daily_job_includes_watchlist_price_alerts():
    from app.main import app

    with TestClient(app) as client:
        created = client.post(
            "/api/v1/watchlist",
            json={"symbol": "2330", "target_price": 1, "stop_price": 0.5},
        )
        response = client.post("/api/v1/jobs/daily-after-close")

    assert created.status_code == 200, created.text
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["watchlist_alerts"]
    alert = next(item for item in body["watchlist_alerts"] if item["symbol"] == "2330")
    assert "目標價觸及" in alert["triggered"]
    assert "不會自動下單" in alert["summary"]
