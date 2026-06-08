import pytest

from app.services.reports import ReportService


@pytest.mark.asyncio
async def test_pdf_report_generates_file():
    result = await ReportService().generate_pdf("2330")

    assert result["symbol"] == "2330"
    assert result["file_path"].endswith(".pdf")

