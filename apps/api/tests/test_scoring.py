from app.services.sample_data import make_institutional_flows
from app.services.ai_picker import classify_candidate_status
from app.services.scoring import (
    build_price_plan,
    build_research_decision,
    evaluate_breakout_potential,
    evaluate_fundamental_gate,
    evaluate_timing_gate,
    evaluate_valuation_gate,
    recommendation_from_score,
    score_fundamental,
    summarize_institutional,
)


def test_recommendation_boundaries():
    assert recommendation_from_score(95) == "優先研究"
    assert recommendation_from_score(80) == "可研究"
    assert recommendation_from_score(65) == "觀察"
    assert recommendation_from_score(45) == "降低風險"
    assert recommendation_from_score(20) == "暫避"


def test_fundamental_score_caps_at_25():
    score, reasons, risks = score_fundamental(
        {
            "eps": 10,
            "roe": 30,
            "gross_margin": 55,
            "operating_margin": 30,
            "pe_ratio": 18,
            "pb_ratio": 2,
            "revenue_yoy": 25,
            "revenue_mom": 5,
        }
    )
    assert score <= 25
    assert reasons
    assert not risks


def test_institutional_summary_windows():
    flows = make_institutional_flows("2330", days=80)
    summary = summarize_institutional(flows)

    assert "five_day_total" in summary
    assert "twenty_day_total" in summary
    assert "sixty_day_total" in summary


def test_low_pe_does_not_override_negative_eps():
    fundamental = {
        "eps": -1.2,
        "roe": 18,
        "gross_margin": 42,
        "operating_margin": 15,
        "pe_ratio": 8,
        "revenue_yoy": 12,
        "revenue_mom": 1,
    }

    fundamental_gate = evaluate_fundamental_gate(fundamental)
    valuation_gate = evaluate_valuation_gate("2330", fundamental)

    assert valuation_gate["status"] == "pass"
    assert fundamental_gate["passed"] is False
    assert fundamental_gate["status"] == "fail"
    assert any("EPS" in item for item in fundamental_gate["failed_reasons"])


def test_high_quality_expensive_stock_waits_for_better_price():
    fundamental = {
        "eps": 12,
        "roe": 28,
        "gross_margin": 55,
        "operating_margin": 30,
        "pe_ratio": 45,
        "revenue_yoy": 25,
        "revenue_mom": 4,
    }
    technical = _technical(close=100, ma20=98, ma60=92, ma120=88, ma240=80, rsi14=55, volume_ratio=1.1)

    fundamental_gate = evaluate_fundamental_gate(fundamental)
    valuation_gate = evaluate_valuation_gate("2330", fundamental)
    timing_gate = evaluate_timing_gate(technical)
    price_plan = build_price_plan(technical, timing_gate, valuation_gate)
    decision = build_research_decision(
        fundamental_gate=fundamental_gate,
        valuation_gate=valuation_gate,
        timing_gate=timing_gate,
        price_plan=price_plan,
        risk_lights={"composite": "yellow"},
        data_sources={"price": "finmind", "fundamental": "finmind", "news": "finmind"},
    )

    assert fundamental_gate["passed"] is True
    assert valuation_gate["status"] == "fail"
    assert decision["stance"] == "wait_better_price"


def test_sample_fundamental_research_decision_stays_watch_only():
    fundamental = {
        "eps": 12,
        "roe": 28,
        "gross_margin": 55,
        "operating_margin": 30,
        "pe_ratio": 18,
        "revenue_yoy": 25,
        "revenue_mom": 4,
    }
    technical = _technical(close=100, ma20=98, ma60=92, ma120=88, ma240=80, rsi14=55, volume_ratio=1.1)
    fundamental_gate = evaluate_fundamental_gate(fundamental)
    valuation_gate = evaluate_valuation_gate("2330", fundamental)
    timing_gate = evaluate_timing_gate(technical)

    decision = build_research_decision(
        fundamental_gate=fundamental_gate,
        valuation_gate=valuation_gate,
        timing_gate=timing_gate,
        price_plan=build_price_plan(technical, timing_gate, valuation_gate),
        risk_lights={"composite": "green"},
        data_sources={"price": "finmind", "fundamental": "sample", "news": "sample"},
    )

    assert decision["stance"] == "watch"
    assert decision["confidence"] == "低"
    assert any("不採用 EPS、PE、ROE" in item for item in decision["blockers"])


def test_sample_price_research_decision_waits_for_real_kline():
    fundamental = {
        "eps": 12,
        "roe": 28,
        "gross_margin": 55,
        "operating_margin": 30,
        "pe_ratio": 18,
        "revenue_yoy": 25,
        "revenue_mom": 4,
    }
    technical = _technical(close=100, ma20=98, ma60=92, ma120=88, ma240=80, rsi14=55, volume_ratio=1.1)
    fundamental_gate = evaluate_fundamental_gate(fundamental)
    valuation_gate = evaluate_valuation_gate("2330", fundamental)
    timing_gate = evaluate_timing_gate(technical)

    decision = build_research_decision(
        fundamental_gate=fundamental_gate,
        valuation_gate=valuation_gate,
        timing_gate=timing_gate,
        price_plan=build_price_plan(technical, timing_gate, valuation_gate),
        risk_lights={"composite": "green"},
        data_sources={"price": "sample", "fundamental": "finmind", "news": "finmind"},
    )

    assert decision["stance"] == "watch"
    assert "真實日 K" in decision["next_action"]
    assert any("不採用均線" in item for item in decision["blockers"])


def test_etf_valuation_gate_is_not_applicable():
    gate = evaluate_valuation_gate("0050", {"pe_ratio": 99})

    assert gate["status"] == "not_applicable"
    assert gate["pe_band"] == "不適用"


def test_timing_gate_blocks_overheated_chase():
    technical = _technical(close=120, ma20=100, ma60=95, ma120=90, ma240=85, rsi14=74, volume_ratio=2.4)
    gate = evaluate_timing_gate(technical)

    assert gate["status"] == "watch"
    assert "RSI14" in gate["no_chase_zone"]
    assert "量比" in gate["no_chase_zone"]


def test_sample_fundamentals_cannot_be_qualified_research():
    status, blockers = classify_candidate_status(
        _candidate_analysis(
            fundamental_source="sample",
            valuation_status="fail",
            valuation_warning="本益比偏高，等便宜價。",
            no_chase_reason="本益比還沒便宜，不追價。",
        ),
        _market(light="green"),
    )

    assert status == "watch_only"
    assert any("可驗證真實來源" in item for item in blockers)
    assert any("PE、PB、ROE" in item for item in blockers)
    assert all("本益比" not in item for item in blockers)


def test_official_exchange_fundamentals_can_be_qualified_research():
    status, blockers = classify_candidate_status(
        _candidate_analysis(fundamental_source="twse-openapi"),
        _market(light="green"),
    )

    assert status == "qualified_research"
    assert blockers == []


def test_expensive_high_quality_candidate_waits_for_price():
    status, blockers = classify_candidate_status(
        _candidate_analysis(valuation_status="fail", valuation_warning="本益比偏高，等便宜價。"),
        _market(light="green"),
    )

    assert status == "wait_price"
    assert "本益比偏高" in blockers[0]


def test_overheated_candidate_has_no_chase_blocker():
    status, blockers = classify_candidate_status(
        _candidate_analysis(timing_status="watch", no_chase_reason="RSI14 與量比過熱，禁止追高。"),
        _market(light="green"),
    )

    assert status == "watch_only"
    assert any("禁止追高" in item for item in blockers)


def test_timing_gate_fails_when_price_breaks_long_moving_averages():
    technical = _technical(close=80, ma20=90, ma60=95, ma120=100, ma240=105, rsi14=45, volume_ratio=1.0)
    gate = evaluate_timing_gate(technical)

    assert gate["status"] == "fail"
    assert gate["invalidation_price"] == 95


def test_breakout_potential_requires_real_data_and_clean_setup():
    fundamental = {
        "eps": 12,
        "roe": 28,
        "gross_margin": 55,
        "operating_margin": 30,
        "pe_ratio": 18,
        "revenue_yoy": 25,
        "revenue_mom": 4,
    }
    technical = _technical(close=100, ma20=96, ma60=90, ma120=82, ma240=75, rsi14=58, volume_ratio=1.5)
    fundamental_gate = evaluate_fundamental_gate(fundamental)
    valuation_gate = evaluate_valuation_gate("2330", fundamental)
    timing_gate = evaluate_timing_gate(technical)

    breakout = evaluate_breakout_potential(
        fundamental_gate=fundamental_gate,
        valuation_gate=valuation_gate,
        timing_gate=timing_gate,
        price_plan=build_price_plan(technical, timing_gate, valuation_gate),
        technical=technical,
        institutional={
            "five_day_total": 1000,
            "twenty_day_total": 5000,
            "foreign_trend": "accumulating",
            "investment_trust_trend": "accumulating",
        },
        margin={"status": "cleaning"},
        sentiment={"score": 0.5},
        risk_lights={"composite": "green"},
        data_sources=_trusted_sources(),
    )

    assert breakout["status"] == "ready_setup"
    assert breakout["score"] >= 78
    assert breakout["label"] == "高潛力準備"
    assert breakout["leading_signals"]
    assert "不追急漲" in breakout["no_chase_warning"]


def test_breakout_potential_stays_data_limited_for_sample_sources():
    technical = _technical(close=100, ma20=96, ma60=90, ma120=82, ma240=75, rsi14=58, volume_ratio=1.5)
    fundamental_gate = evaluate_fundamental_gate(
        {"eps": 12, "roe": 28, "gross_margin": 55, "operating_margin": 30, "pe_ratio": 18, "revenue_yoy": 25}
    )
    valuation_gate = evaluate_valuation_gate("2330", {"pe_ratio": 18})
    timing_gate = evaluate_timing_gate(technical)

    breakout = evaluate_breakout_potential(
        fundamental_gate=fundamental_gate,
        valuation_gate=valuation_gate,
        timing_gate=timing_gate,
        price_plan=build_price_plan(technical, timing_gate, valuation_gate),
        technical=technical,
        institutional={},
        margin={},
        sentiment={"score": 0.5},
        risk_lights={"composite": "green"},
        data_sources={"price": "sample", "fundamental": "sample", "news": "sample"},
    )

    assert breakout["status"] == "data_limited"
    assert breakout["confidence"] == "低"
    assert breakout["score"] <= 18
    assert any("基本面" in item for item in breakout["missing_confirmations"])


def test_breakout_potential_blocks_overheated_chase():
    fundamental = {
        "eps": 12,
        "roe": 28,
        "gross_margin": 55,
        "operating_margin": 30,
        "pe_ratio": 18,
        "revenue_yoy": 25,
        "revenue_mom": 4,
    }
    technical = _technical(close=120, ma20=100, ma60=95, ma120=90, ma240=85, rsi14=74, volume_ratio=2.5)
    fundamental_gate = evaluate_fundamental_gate(fundamental)
    valuation_gate = evaluate_valuation_gate("2330", fundamental)
    timing_gate = evaluate_timing_gate(technical)

    breakout = evaluate_breakout_potential(
        fundamental_gate=fundamental_gate,
        valuation_gate=valuation_gate,
        timing_gate=timing_gate,
        price_plan=build_price_plan(technical, timing_gate, valuation_gate),
        technical=technical,
        institutional={"five_day_total": 1000, "twenty_day_total": 5000},
        margin={"status": "improving"},
        sentiment={"score": 0.5},
        risk_lights={"composite": "green"},
        data_sources=_trusted_sources(),
    )

    assert breakout["status"] == "too_extended"
    assert "禁止追高" in breakout["no_chase_warning"]
    assert any("過熱" in item or "追價" in item for item in breakout["missing_confirmations"])


def _technical(
    *,
    close: float,
    ma20: float,
    ma60: float,
    ma120: float,
    ma240: float,
    rsi14: float,
    volume_ratio: float,
) -> dict:
    return {
        "latest_close": close,
        "ma": {"ma20": ma20, "ma60": ma60, "ma120": ma120, "ma240": ma240},
        "rsi": {"rsi14": rsi14},
        "macd": {"osc": 1},
        "atr14": 5,
        "volume_ratio": volume_ratio,
        "trend": "bullish",
        "signals": [],
    }


def _candidate_analysis(
    *,
    fundamental_source: str = "finmind",
    fundamental_status: str = "pass",
    valuation_status: str = "pass",
    valuation_warning: str | None = None,
    timing_status: str = "pass",
    no_chase_reason: str | None = None,
) -> dict:
    return {
        "data_sources": {
            "price": "finmind",
            "institutional": "finmind",
            "margin": "finmind",
            "fundamental": fundamental_source,
            "news": "finmind",
        },
        "research_decision": {
            "blockers": [],
            "do_not_chase_reason": no_chase_reason,
        },
        "fundamental_gate": {
            "status": fundamental_status,
            "passed": fundamental_status == "pass",
        },
        "valuation_gate": {
            "status": valuation_status,
            "warning": valuation_warning,
        },
        "timing_gate": {
            "status": timing_status,
        },
    }


def _market(*, light: str = "yellow") -> dict:
    return {"lights": {"composite": light}}


def _trusted_sources() -> dict:
    return {
        "price": "yahoo",
        "institutional": "finmind",
        "margin": "finmind",
        "fundamental": "finmind",
        "news": "finmind",
    }
