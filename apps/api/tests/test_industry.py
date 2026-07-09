from app.services.industry import OTHER_INDUSTRY, resolve_industry


def test_resolve_industry_uses_static_symbol_over_generic_source():
    assert resolve_industry("3693", "營邦", "其他業") == "電腦及週邊設備"
    assert resolve_industry("3706", "神達", "其他電子業") == "電腦及週邊設備"
    assert resolve_industry("6451", "訊芯-KY", "半導體業") == "半導體封測"


def test_resolve_industry_uses_source_industry_for_future_stocks():
    assert resolve_industry("9999", "未收錄公司", "電腦及週邊設備業") == "電腦及週邊設備"
    assert resolve_industry("9999", "未收錄公司", "半導體業") == "半導體"
    assert resolve_industry("9999", "未收錄公司", "其他電子業") == "其他電子"
    assert resolve_industry("9999", "未收錄公司", "其他產業") == "其他產業"


def test_resolve_industry_never_returns_old_placeholder():
    assert resolve_industry("9999", None, None) == OTHER_INDUSTRY
    assert resolve_industry("9999", None, None) != "產業資料待補"
