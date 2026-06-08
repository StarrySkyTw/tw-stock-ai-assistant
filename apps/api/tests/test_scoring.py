from app.services.sample_data import make_institutional_flows
from app.services.scoring import recommendation_from_score, score_fundamental, summarize_institutional


def test_recommendation_boundaries():
    assert recommendation_from_score(95) == "強力買進"
    assert recommendation_from_score(80) == "買進"
    assert recommendation_from_score(65) == "觀察"
    assert recommendation_from_score(45) == "減碼"
    assert recommendation_from_score(20) == "賣出"


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

