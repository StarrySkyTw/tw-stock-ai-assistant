from datetime import date

from app.services.data_providers.twse import (
    _extract_company_profile,
    _extract_material_events,
    _extract_realtime_profile,
    _extract_tdcc_shareholding,
    _fundamental_from_official_rows,
    _margin_row,
)


def test_extract_company_profile_reads_tpex_company_rows():
    payload = [
        {
            "SecuritiesCompanyCode": "3693",
            "CompanyName": "營邦企業股份有限公司",
            "CompanyAbbreviation": "營邦",
            "SecuritiesIndustryCode": "25",
        }
    ]

    assert _extract_company_profile(payload, "3693") == {
        "name": "營邦",
        "industry": "電腦及週邊設備業",
    }


def test_extract_realtime_profile_uses_quote_short_name():
    payload = {"msgArray": [{"c": "3693", "n": "營邦", "nf": "營邦企業股份有限公司"}]}

    assert _extract_realtime_profile(payload) == {"name": "營邦", "industry": None}


def test_fundamental_from_official_rows_combines_exchange_metrics():
    data = _fundamental_from_official_rows(
        {"Code": "2330", "PEratio": "16.00", "PBratio": "2.40"},
        {
            "公司代號": "2330",
            "營業收入-上月比較增減(%)": "1.52",
            "營業收入-去年同月增減(%)": "30.09",
        },
        {
            "公司代號": "2330",
            "基本每股盈餘(元)": "22.08",
            "營業收入": "1134103440.00",
            "營業利益": "658966142.00",
        },
    )

    assert data.eps == 22.08
    assert data.pe_ratio == 16.0
    assert data.pb_ratio == 2.4
    assert data.roe == 15.0
    assert data.revenue_yoy == 30.09
    assert data.revenue_mom == 1.52
    assert data.operating_margin == 58.1


def test_margin_row_derives_short_margin_ratio():
    row = _margin_row(date(2026, 6, 26), 4314, 7)

    assert row["margin_purchase_balance"] == 4314
    assert row["short_sale_balance"] == 7
    assert row["short_margin_ratio"] == 0.16


def test_extract_tdcc_shareholding_sums_large_holder_bucket():
    csv_text = "\ufeff資料日期,證券代號,持股分級,人數,股數,占集保庫存數比例%\n20260619,2330,1,50,100000,0.10\n20260619,2330,15,5,8000000,10.00\n20260619,2330,17,55,8100000,100.00\n20260626,2330,1,100,100000,0.10\n20260626,2330,15,8,8000000,12.50\n20260626,2330,16,2,9000000,15.25\n20260626,2330,17,110,17100000,100.00\n20260626,2317,15,1,1000000,1.00\n"

    data = _extract_tdcc_shareholding(csv_text, "2330")

    assert data.shareholder_count == 110
    assert data.large_holder_ratio == 27.75


def test_extract_material_events_reads_twse_and_tpex_rows():
    rows = [
        {
            "發言日期": "1150629",
            "公司代號": "2330",
            "公司名稱": "台積電",
            "主旨 ": "公告本公司董事會重要決議\r\n第二行",
            "說明": "1.事實發生日：民國115年06月29日\r\n2.說明：測試",
        },
        {"SecuritiesCompanyCode": "2317", "CompanyName": "鴻海", "主旨": "其他公司公告"},
    ]

    events = _extract_material_events(rows, "2330", "twse-material")

    assert events == [
        {
            "published_at": "2026-06-29",
            "title": "公告本公司董事會重要決議 第二行",
            "source": "twse-material",
            "url": "https://mops.twse.com.tw/mops/web/t05st02",
            "summary": "1.事實發生日：民國115年06月29日 2.說明：測試",
        }
    ]
