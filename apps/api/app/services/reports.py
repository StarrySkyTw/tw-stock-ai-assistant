from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from app.core.config import get_settings
from app.services.analysis import AnalysisService


class ReportService:
    def __init__(self) -> None:
        self.analysis = AnalysisService()
        self.settings = get_settings()

    async def generate_pdf(self, symbol: str) -> dict:
        analysis = await self.analysis.analyze(symbol)
        output_dir = self.settings.reports_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now(UTC)
        path = output_dir / f"{symbol.upper()}-{now.strftime('%Y%m%d%H%M%S')}.pdf"
        _write_pdf(path, analysis)
        return {"symbol": symbol.upper(), "file_path": str(path), "generated_at": now}


def _write_pdf(path: Path, analysis: dict) -> None:
    font_name = _register_font()
    pdf = canvas.Canvas(str(path), pagesize=A4)
    width, height = A4
    y = height - 48
    pdf.setFont(font_name, 18)
    pdf.drawString(48, y, f"{analysis['symbol']} AI 投資研究報告")
    y -= 34
    pdf.setFont(font_name, 12)
    lines = [
        f"日期：{analysis['analysis_date']}",
        f"總分：{analysis['adjusted_score']} / 100（原始分數 {analysis['raw_score']}）",
        f"建議：{analysis['recommendation']}",
        f"停利價：{analysis['trailing_take_profit']['current_take_profit_price']}",
        f"ATR 停損：{analysis['stop_loss']['atr_stop']}",
        "理由：",
        *[f"- {item}" for item in analysis["reasons"][:8]],
        "風險：",
        *[f"- {item}" for item in analysis["risks"][:8]],
        "風險聲明：本報告僅供研究與紀律化決策輔助，不構成投資建議。",
    ]
    for line in lines:
        for chunk in _wrap(line, 46):
            if y < 54:
                pdf.showPage()
                pdf.setFont(font_name, 12)
                y = height - 48
            pdf.drawString(48, y, chunk)
            y -= 18
    pdf.save()


def _register_font() -> str:
    candidates = [
        Path("C:/Windows/Fonts/msjh.ttc"),
        Path("C:/Windows/Fonts/mingliu.ttc"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            try:
                pdfmetrics.registerFont(TTFont("ReportFont", str(candidate)))
                return "ReportFont"
            except Exception:
                continue
    return "Helvetica"


def _wrap(text: str, width: int) -> list[str]:
    return [text[index : index + width] for index in range(0, len(text), width)] or [""]
