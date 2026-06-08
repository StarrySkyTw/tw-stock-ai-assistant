from fastapi import APIRouter

from app.schemas import PdfReportResponse
from app.services.reports import ReportService

router = APIRouter(prefix="/reports", tags=["reports"])


@router.post("/{symbol}/pdf", response_model=PdfReportResponse)
async def generate_pdf(symbol: str) -> dict:
    return await ReportService().generate_pdf(symbol)

