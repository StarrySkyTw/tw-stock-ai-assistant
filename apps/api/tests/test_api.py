import asyncio

import pandas as pd
import pytest
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


def test_normalize_price_frame_drops_invalid_price_rows():
    from app.services.data_providers.base import normalize_price_frame

    frame = pd.DataFrame(
        {
            "date": ["2026-06-01", "2026-06-02", "not-a-date"],
            "open": [100, None, 103],
            "high": [104, 105, 106],
            "low": [99, 100, 101],
            "close": [103, float("nan"), 105],
            "volume": [1000, None, 1200],
        }
    )

    normalized = normalize_price_frame(frame)

    assert len(normalized) == 1
    assert normalized.iloc[0]["close"] == 103


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


def test_sample_stock_name_knows_kyec():
    from app.services.sample_data import stock_name

    assert stock_name("2449") == "京元電子"
    assert stock_name("2313") == "華通"
    assert stock_name("3653") == "健策"
    assert stock_name("3665") == "貿聯-KY"
    assert stock_name("3693") == "營邦"
    assert stock_name("3706") == "神達"
    assert stock_name("6285") == "啟碁"
    assert stock_name("6451") == "訊芯-KY"


def test_taiex_realtime_snapshot_uses_previous_close_for_change():
    from app.api.routes.market import _quote_from_realtime_snapshot

    quote = _quote_from_realtime_snapshot(
        {
          "close": 47741.51,
          "previous_close": 46465.20,
          "volume": 15524158000,
          "name": "發行量加權股價指數",
        },
        "twse-realtime",
    )

    assert quote is not None
    assert quote["change"] == 1276.31
    assert quote["change_percent"] == 2.75


def test_twse_index_snapshot_reads_market_volume_field():
    from app.services.data_providers.twse import _extract_quote

    quote = _extract_quote(
        {
            "msgArray": [
                {
                    "@": "t00.tw",
                    "d": "20260622",
                    "h": "47871.19",
                    "l": "46679.57",
                    "m": "15524158",
                    "n": "發行量加權股價指數",
                    "o": "46679.57",
                    "y": "46465.20",
                    "z": "47741.51",
                }
            ]
        }
    )

    assert quote is not None
    assert quote["volume"] == 15524158000


def test_yahoo_intraday_chart_parser_returns_minute_rows():
    from app.services.data_providers.yahoo import parse_yahoo_intraday_chart

    payload = {
        "chart": {
            "result": [
                {
                    "meta": {
                        "chartPreviousClose": 2410,
                        "regularMarketPrice": 2510,
                        "regularMarketVolume": 43209389,
                        "regularMarketTime": 1782106200,
                    },
                    "timestamp": [1782090000, 1782090060],
                    "indicators": {
                        "quote": [
                            {
                                "open": [2455, 2460],
                                "high": [2460, 2470],
                                "low": [2455, 2460],
                                "close": [2460, 2470],
                                "volume": [100, 200],
                            }
                        ]
                    },
                }
            ]
        }
    }

    frame, metadata = parse_yahoo_intraday_chart(payload)

    assert len(frame) == 2
    assert frame.iloc[-1]["close"] == 2470
    assert metadata["previous_close"] == 2410
    assert metadata["regular_market_volume"] == 43209389


def test_yahoo_daily_chart_parser_returns_daily_rows():
    from app.services.data_providers.yahoo import parse_yahoo_daily_chart

    payload = {
        "chart": {
            "result": [
                {
                    "timestamp": [1782000000, 1782086400],
                    "indicators": {
                        "quote": [
                            {
                                "open": [2400, 2440],
                                "high": [2460, 2480],
                                "low": [2390, 2430],
                                "close": [2450, 2470],
                                "volume": [32000, 45000],
                            }
                        ]
                    },
                }
            ]
        }
    }

    frame = parse_yahoo_daily_chart(payload)

    assert len(frame) == 2
    assert list(frame.columns) == ["date", "open", "high", "low", "close", "volume"]
    assert frame.iloc[-1]["close"] == 2470
    assert frame.iloc[-1]["volume"] == 45000


def test_health_endpoint():
    from app.main import app

    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_static_web_mount_serves_exported_index(monkeypatch, tmp_path):
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "index.html").write_text("<html><body>StockAI static app</body></html>", encoding="utf-8")

    monkeypatch.setenv("STATIC_WEB_DIR", str(out_dir))

    from app.core.config import get_settings
    from app.main import create_app

    get_settings.cache_clear()
    client = TestClient(create_app())
    response = client.get("/")
    get_settings.cache_clear()

    assert response.status_code == 200
    assert "StockAI static app" in response.text
    assert response.headers["Cache-Control"] == "no-store, no-cache, must-revalidate, max-age=0"


def test_watchlist_returns_resolved_stock_name(monkeypatch):
    from app.main import app
    from app.services.data_providers.composite import MarketDataService

    async def fake_stock_profile(self, symbol: str) -> dict[str, str | None]:
        return {"name": "華通" if symbol == "2313" else None, "industry": None}

    monkeypatch.setattr(MarketDataService, "stock_profile", fake_stock_profile)
    with TestClient(app) as client:
        created = client.post("/api/v1/watchlist", json={"symbol": "2313"})
        listed = client.get("/api/v1/watchlist")

    assert created.status_code == 200, created.text
    assert created.json()["name"] == "華通"
    assert created.json()["lookup_status"] == "verified"
    assert listed.status_code == 200, listed.text
    assert listed.json()[0]["name"] == "華通"
    assert listed.json()[0]["lookup_status"] == "verified"


def test_watchlist_marks_unknown_symbol(monkeypatch):
    from app.main import app
    from app.services.data_providers.composite import MarketDataService

    async def fake_stock_profile(self, symbol: str) -> dict[str, str | None]:
        return {"name": None, "industry": None}

    monkeypatch.setattr(MarketDataService, "stock_profile", fake_stock_profile)
    with TestClient(app) as client:
        response = client.post("/api/v1/watchlist", json={"symbol": "9999"})

    assert response.status_code == 200, response.text
    assert response.json()["name"] is None
    assert response.json()["lookup_status"] == "unknown_symbol"


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
    assert body["data_sources"]["fundamental"] == "sample"
    assert body["data_sources"]["news"] == "sample"
    assert body["recommendation"] == "只觀察"
    assert body["adjusted_score"] <= 49
    assert body["research_decision"]["stance"] in {"watch", "reduce_risk"}
    assert body["fundamental_gate"]["status"] == "unknown"
    assert body["fundamental_gate"]["passed"] is False
    assert body["fundamental"]["eps"] is None
    assert body["fundamental"]["pe_ratio"] is None
    assert body["valuation_gate"]["status"] == "unknown"
    assert body["valuation_gate"]["pe_ratio"] is None
    assert body["timing_gate"]["status"] == "unknown"
    assert body["timing_gate"]["support_zone"] == "等待真實日 K"
    assert body["price_plan"]["research_price"] is None
    assert body["price_plan"]["watch_price"] is None
    assert body["price_plan"]["invalidation_price"] is None
    assert body["breakout_potential"]["status"] == "data_limited"
    assert body["breakout_potential"]["score"] <= 18
    assert "不判斷爆發潛力" in body["breakout_potential"]["headline"]
    assert body["stop_loss"]["atr_stop"] is None
    assert body["trailing_take_profit"]["current_take_profit_price"] is None
    assert body["trailing_take_profit"]["risk_reward_ratio"] is None
    assert body["kline_analysis"]["headline"] == "價格來源不足，K 線數字暫不採用"
    assert body["margin"]["signals"]
    assert body["strategy_judgement"]["checks"]
    assert body["strategy_judgement"]["timing_score"] >= 0
    assert body["decision_plan"]["checklist"]["進場條件"]
    assert body["decision_plan"]["scenarios"]
    assert body["research_decision"]["horizon"] == "3個月-2年"
    assert body["timing_gate"]["support_zone"]
    assert "position_size_hint" in body["price_plan"]


def test_chart_endpoint_returns_compact_candle_payload():
    from app.main import app

    client = TestClient(app)
    response = client.get("/api/v1/stocks/2330/chart?range=1y")

    assert response.status_code == 200, response.text
    body = response.json()
    traces = body["figure"]["data"]
    assert body["symbol"] == "2330"
    assert len(traces) == 2
    assert traces[0]["type"] == "candlestick"
    assert traces[1]["type"] == "bar"
    assert len(traces[0]["x"]) == len(traces[0]["close"])
    assert len(traces[0]["close"]) >= 240


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
    assert body["top_picks"][0]["research_decision"]["stance"]
    assert body["top_picks"][0]["fundamental_gate"]["grade"]
    assert body["top_picks"][0]["breakout_potential"]["status"] == "data_limited"


def test_ai_picks_endpoint_classifies_kyec():
    from app.main import app

    client = TestClient(app)
    response = client.get("/api/v1/market/ai-picks?universe=2449&limit=1&min_score=0")

    assert response.status_code == 200
    pick = response.json()["top_picks"][0]
    assert pick["symbol"] == "2449"
    assert pick["name"] == "京元電子"
    assert pick["industry"] == "半導體測試服務"
    assert "未分類" not in pick["thesis"]
    assert pick["recommendation"] == "只觀察"


def test_ai_picks_endpoint_classifies_mitac_and_shunshin():
    from app.main import app

    client = TestClient(app)
    response = client.get("/api/v1/market/ai-picks?universe=3706,6451&limit=2&min_score=0")

    assert response.status_code == 200
    picks = response.json()["top_picks"]
    industries = {pick["symbol"]: pick["industry"] for pick in picks}
    names = {pick["symbol"]: pick["name"] for pick in picks}

    assert industries["3706"] == "電腦及週邊設備"
    assert industries["6451"] == "半導體封測"
    assert names["3706"] == "神達"
    assert names["6451"] == "訊芯-KY"
    assert all(pick["industry"] != "產業資料待補" for pick in picks)
    assert "產業資料待補" not in response.text
    assert all(pick["recommendation"] == "只觀察" for pick in picks)


def test_ai_picks_endpoint_uses_default_universe():
    from app.main import app

    client = TestClient(app)
    response = client.get("/api/v1/market/ai-picks?limit=3&min_score=0")

    assert response.status_code == 200
    body = response.json()
    assert len(body["universe"]) > 8
    assert len(body["top_picks"]) == 3


def test_market_scan_endpoints_cache_ranked_candidates():
    from app.main import app

    with TestClient(app) as client:
        created = client.post(
            "/api/v1/market/scans",
            json={"universe": ["2330", "2454"], "limit": 2, "max_symbols": 2},
        )
        latest = client.get("/api/v1/market/scans/latest")

    assert created.status_code == 200, created.text
    body = created.json()
    assert body["scan_id"] > 0
    assert body["universe_count"] == 2
    assert body["completed_count"] == 2
    assert body["failed_count"] == 0
    assert body["universe_source"] == "custom"
    assert body["is_full_market"] is False
    assert body["data_quality_summary"]["sample_limited"] >= 1
    assert body["data_quality_summary"]["missing_fundamental"] == 2
    assert len(body["top_candidates"]) == 2
    assert all(item["candidate_status"] != "qualified_research" for item in body["top_candidates"])
    assert all(item["data_sources"]["fundamental"] == "sample" for item in body["top_candidates"])
    assert all(item["selection_score"] <= 49 for item in body["top_candidates"])
    assert all(item["data_quality_score"] < 50 for item in body["top_candidates"])
    assert all(item["fundamental_gate"]["status"] == "unknown" for item in body["top_candidates"])
    assert all(item["valuation_gate"]["status"] == "unknown" for item in body["top_candidates"])
    assert all(item["timing_gate"]["status"] == "unknown" for item in body["top_candidates"])
    assert all(item["price_plan"]["watch_price"] is None for item in body["top_candidates"])
    assert all(item["breakout_potential"]["status"] == "data_limited" for item in body["top_candidates"])
    assert all(item["score_cap_reason"] for item in body["top_candidates"])
    assert all("本益比" not in " ".join(item["blockers"]) for item in body["top_candidates"])
    assert all("本益比" not in " ".join(item["why_ranked"]) for item in body["top_candidates"])
    assert all("基本面 A" not in " ".join(item["why_ranked"]) for item in body["top_candidates"])
    assert all("本益比" not in str(item.get("no_chase_reason") or "") for item in body["top_candidates"])
    assert all(item["future_outlook"]["label"] == "資料不足，不列入未來劇本" for item in body["top_candidates"])
    assert all(item["future_outlook"]["scenarios"][0]["probability"] == 100 for item in body["top_candidates"])
    assert all(
        "0%" in item["future_outlook"]["swing_plan"]["position_size_hint"]
        for item in body["top_candidates"]
    )

    assert latest.status_code == 200, latest.text
    latest_body = latest.json()
    assert latest_body["scan_id"] == body["scan_id"]
    assert all(item["fundamental_gate"]["status"] == "unknown" for item in latest_body["top_candidates"])
    assert all(item["future_outlook"]["label"] == "資料不足，不列入未來劇本" for item in latest_body["top_candidates"])


def test_market_scan_normalizes_stale_sample_gate_payloads():
    from app.services.market_scan import _normalize_payload

    payload = {
        "top_candidates": [
            {
                "symbol": "9999",
                "candidate_status": "qualified_research",
                "selection_score": 88,
                "adjusted_score": 91,
                "data_sources": {"price": "sample", "fundamental": "sample", "news": "sample"},
                "fundamental_gate": {"status": "pass", "grade": "A", "passed": True, "failed_reasons": [], "metrics": {"eps": 9}},
                "valuation_gate": {
                    "status": "pass",
                    "pe_ratio": 12,
                    "pe_band": "便宜",
                    "sector_band": "測試",
                    "is_low_valuation": True,
                    "warning": None,
                },
                "timing_gate": {
                    "status": "pass",
                    "trend": "中長期趨勢可觀察",
                    "support_zone": "90-100",
                    "no_chase_zone": "未觸發禁追條件",
                    "entry_conditions": [],
                    "invalidation_price": 90,
                },
                "price_plan": {
                    "research_price": 100,
                    "watch_price": 95,
                    "invalidation_price": 90,
                    "position_size_hint": "10-25%",
                },
                "blockers": [],
            }
        ]
    }

    normalized = _normalize_payload(payload)
    candidate = normalized["top_candidates"][0]

    assert candidate["candidate_status"] == "watch_only"
    assert candidate["selection_score"] == 49
    assert candidate["adjusted_score"] == 49
    assert candidate["fundamental_gate"]["status"] == "unknown"
    assert candidate["valuation_gate"]["status"] == "unknown"
    assert candidate["timing_gate"]["status"] == "unknown"
    assert candidate["price_plan"]["watch_price"] is None
    assert candidate["breakout_potential"]["status"] == "data_limited"
    assert candidate["future_outlook"]["label"] == "資料不足，不列入未來劇本"
    assert candidate["future_outlook"]["swing_plan"]["position_size_hint"].startswith("0%")
    assert normalized["data_quality_summary"]["sample_limited"] == 1
    assert normalized["data_quality_summary"]["breakout_data_limited"] == 1


def test_market_scan_summary_does_not_treat_optional_gaps_as_core_sample_limit():
    from app.services.market_scan import _data_quality_summary

    summary = _data_quality_summary(
        [
            {
                "candidate_status": "qualified_research",
                "data_quality_score": 82,
                "data_sources": {
                    "price": "finmind+twse-realtime",
                    "fundamental": "finmind",
                    "institutional": "finmind",
                    "margin": "finmind",
                    "shareholding": "unavailable",
                    "news": "unavailable",
                },
            }
        ]
    )

    assert summary["sample_limited"] == 0
    assert summary["optional_unavailable"] == 1
    assert summary["trusted_fundamental"] == 1


def test_market_scan_summary_trusts_official_exchange_fundamentals():
    from app.services.market_scan import _data_quality_summary

    summary = _data_quality_summary(
        [
            {
                "candidate_status": "qualified_research",
                "data_quality_score": 74,
                "data_sources": {
                    "price": "yahoo+twse-realtime",
                    "fundamental": "twse-openapi",
                    "institutional": "twse-t86",
                    "margin": "twse-margin",
                    "shareholding": "unavailable",
                    "news": "unavailable",
                },
            }
        ]
    )

    assert summary["trusted_fundamental"] == 1
    assert summary["finmind_fundamental"] == 0
    assert summary["missing_fundamental"] == 0
    assert summary["sample_limited"] == 0


@pytest.mark.asyncio
async def test_scan_services_reuse_market_risk_snapshot():
    from app.services.ai_picker import AiStockPickerService
    from app.services.market_scan import MarketScanService

    market = {"lights": {"composite": "yellow"}}

    class FakeAnalysis:
        def __init__(self) -> None:
            self.calls = []

        async def analyze(self, symbol, market_risk=None, data_timeout_seconds=None):
            self.calls.append((symbol, market_risk, data_timeout_seconds))
            return {"symbol": symbol}

    scan_analysis = FakeAnalysis()
    scan_service = object.__new__(MarketScanService)
    scan_service.analysis = scan_analysis

    analyses, failed = await scan_service._analyze_symbols(["2330", "2454"], 2, market, 8.0)

    assert failed == []
    assert [item["symbol"] for item in analyses] == ["2330", "2454"]
    assert scan_analysis.calls == [("2330", market, 8.0), ("2454", market, 8.0)]

    picker_analysis = FakeAnalysis()
    picker_service = object.__new__(AiStockPickerService)
    picker_service.analysis_service = picker_analysis

    analyses, failed = await picker_service._analyze_universe(["2330", "2454"], market, 8.0)

    assert failed == []
    assert [item["symbol"] for item in analyses] == ["2330", "2454"]
    assert picker_analysis.calls == [("2330", market, 8.0), ("2454", market, 8.0)]


@pytest.mark.asyncio
async def test_market_risk_engine_reuses_concurrent_snapshot(monkeypatch):
    from app.services.market_risk import MarketRiskEngine

    calls = 0

    async def fake_indicators(self):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        return {
            "usd_twd": 32.25,
            "usd_twd_change_5d": 0.35,
            "us10y": 4.18,
            "vix": 18.6,
            "sox_change_5d": 1.2,
            "nasdaq_change_5d": 1.1,
            "sp500_change_5d": 0.55,
            "us_futures_change": 0.15,
            "taiex_change_20d": 1.8,
        }

    monkeypatch.setattr(MarketRiskEngine, "_load_indicators", fake_indicators)
    MarketRiskEngine.clear_cache()

    first, second = await asyncio.gather(MarketRiskEngine().evaluate(), MarketRiskEngine().evaluate())

    assert calls == 1
    assert first == second

    first["reasons"].append("mutated by caller")
    cached = await MarketRiskEngine().evaluate()

    assert calls == 1
    assert "mutated by caller" not in cached["reasons"]


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


def test_position_decision_prioritizes_event_and_revenue_risk(monkeypatch):
    from app.main import app
    from app.services.analysis import AnalysisService

    async def fake_analyze(self, symbol, entry_price=None, highest_price=None, atr_multiplier=2.0, market_risk=None, data_timeout_seconds=None):
        return {
            "data_sources": {
                "price": "yahoo",
                "fundamental": "twse-openapi",
                "news": "twse-material",
                "institutional": "twse-t86",
                "margin": "twse-margin",
            },
            "technical": {"latest_close": 92.0},
            "sentiment": {
                "score": -0.7,
                "label": "negative",
                "summary": "政策與出口管制風險升高。",
                "headlines": ["美中政策與出口管制影響接單展望"],
            },
            "fundamental_gate": {
                "status": "watch",
                "metrics": {"revenue_yoy": -12.5, "revenue_mom": -4.0},
            },
            "risk_lights": {"composite": "yellow"},
            "research_decision": {
                "stance": "watch",
                "confidence": "中",
                "next_action": "先降低部位並等待營收修復。",
                "do_not_chase_reason": None,
                "review_triggers": ["下一次月營收公布後重新檢查。"],
            },
            "timing_gate": {"status": "watch", "invalidation_price": 88.0},
            "stop_loss": {"ma60_stop_triggered": False, "ma20_stop_triggered": False},
            "reasons": ["價格仍守在短線支撐。"],
            "risks": ["重大消息與營收轉弱。"],
        }

    monkeypatch.setattr(AnalysisService, "analyze", fake_analyze)

    with TestClient(app) as client:
        created = client.post(
            "/api/v1/positions",
            json={"symbol": "2330", "entry_price": 100, "quantity": 10, "highest_price": 118},
        )
        response = client.get("/api/v1/positions/decisions")

    assert created.status_code == 200, created.text
    assert response.status_code == 200, response.text
    body = response.json()
    assert body[0]["action"] in {"reduce", "sell"}
    assert body[0]["priority_factors"][0]["kind"] == "event"
    assert body[0]["priority_factors"][0]["tone"] == "risk"
    assert body[0]["priority_factors"][1]["kind"] == "revenue"
    assert body[0]["priority_factors"][1]["tone"] == "risk"
    assert body[0]["unrealized_pnl_percent"] == -8.0


def test_market_context_flags_cpi_and_tsmc_event_window():
    from datetime import date

    from app.services.future_outlook import build_future_outlook
    from app.services.market_context import build_market_context

    analysis = {
        "data_sources": {"price": "yahoo", "fundamental": "twse-openapi"},
        "sentiment": {"label": "neutral", "error": "no_news"},
        "fundamental_gate": {"status": "pass", "metrics": {"revenue_yoy": 5.0}},
        "valuation_gate": {"status": "watch"},
        "timing_gate": {
            "status": "watch",
            "support_zone": "MA20 95 / MA60 90",
            "no_chase_zone": "站上高檔急拉不追",
            "invalidation_price": 88.0,
        },
        "technical": {
            "latest_close": 100,
            "ma": {"ma20": 95, "ma60": 90},
            "volume_ratio": 0.8,
        },
        "margin": {"five_day_change": -120, "twenty_day_change": 500},
        "institutional": {"five_day_total": -1000, "twenty_day_total": -2000},
        "research_decision": {"do_not_chase_reason": "等回測"},
    }
    context = build_market_context(
        analysis,
        "2330",
        today=date(2026, 7, 8),
    )

    assert context["event_window"] is True
    assert any("CPI" in item["label"] for item in context["catalysts"])
    assert any("台積電" in item["label"] for item in context["catalysts"])
    assert any(signal["kind"] == "chip_context" and "籌碼清洗" in signal["detail"] for signal in context["signals"])
    assert any(signal["kind"] == "discipline" and "安全邊際" in signal["detail"] for signal in context["signals"])

    outlook = build_future_outlook(
        position=type("PositionLike", (), {"entry_price": 100.0})(),
        analysis=analysis,
        market_context=context,
        priority_factors=context["signals"],
        latest_close=100.0,
        action="hold",
        unrealized_pnl_percent=0.0,
    )
    assert sum(item["probability"] for item in outlook["scenarios"]) == 100
    assert any(item["name"] == "震盪換手" for item in outlook["scenarios"])
    assert "預期差" in outlook["expectation_gap"]
    assert outlook["swing_plan"]["stance"] == "事件前守倉"


def test_position_decision_holds_through_event_window_without_real_bullish(monkeypatch):
    from datetime import date

    from app.main import app
    from app.services.analysis import AnalysisService
    import app.services.market_context as market_context

    async def fake_analyze(self, symbol, entry_price=None, highest_price=None, atr_multiplier=2.0, market_risk=None, data_timeout_seconds=None):
        return {
            "data_sources": {
                "price": "yahoo",
                "fundamental": "twse-openapi",
                "news": "twse-material",
                "institutional": "twse-t86",
                "margin": "twse-margin",
            },
            "technical": {
                "latest_close": 102.0,
                "ma": {"ma20": 98.0, "ma60": 91.0},
                "volume_ratio": 0.75,
            },
            "sentiment": {
                "score": 0.0,
                "label": "neutral",
                "summary": "目前沒有可用新聞。",
                "headlines": [],
                "error": "no_news",
            },
            "fundamental_gate": {
                "status": "pass",
                "metrics": {"revenue_yoy": 5.0, "revenue_mom": 1.0},
            },
            "valuation_gate": {"status": "watch"},
            "risk_lights": {"composite": "green"},
            "research_decision": {
                "stance": "reduce_risk",
                "confidence": "中",
                "next_action": "等 CPI 與法說後重新確認。",
                "do_not_chase_reason": "估值不便宜，不追價。",
                "review_triggers": ["法說後重新檢查。"],
            },
            "timing_gate": {"status": "watch", "invalidation_price": 88.0},
            "stop_loss": {"ma60_stop_triggered": False, "ma20_stop_triggered": False},
            "margin": {"five_day_change": -120, "twenty_day_change": 500},
            "institutional": {"five_day_total": -1000, "twenty_day_total": -2000},
            "reasons": ["價格仍守支撐。"],
            "risks": ["事件前缺少實質利多。"],
        }

    monkeypatch.setattr(AnalysisService, "analyze", fake_analyze)
    monkeypatch.setattr(market_context, "taipei_today", lambda: date(2026, 7, 8))

    with TestClient(app) as client:
        created = client.post(
            "/api/v1/positions",
            json={"symbol": "2330", "entry_price": 100, "quantity": 10, "highest_price": 118},
        )
        response = client.get("/api/v1/positions/decisions")

    assert created.status_code == 200, created.text
    assert response.status_code == 200, response.text
    decision = next(item for item in response.json() if item["position"]["symbol"] == "2330")
    assert decision["action"] == "hold"
    assert "事件前震盪" in decision["headline"]
    assert any(signal["kind"] == "catalyst" and "CPI" in signal["detail"] for signal in decision["priority_factors"])
    assert any(signal["kind"] == "chip_context" and "籌碼清洗" in signal["detail"] for signal in decision["priority_factors"])
    assert decision["future_outlook"]["label"] == "事件前震盪"
    assert sum(item["probability"] for item in decision["future_outlook"]["scenarios"]) == 100
    assert decision["future_outlook"]["swing_plan"]["stance"] == "事件前守倉"
    assert "不追" in decision["future_outlook"]["swing_plan"]["trim_rule"]


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
