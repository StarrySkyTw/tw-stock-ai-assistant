from fastapi import APIRouter, HTTPException

from app.schemas import RadarResponse
from app.services.analysis import AnalysisService

router = APIRouter(prefix="/radar", tags=["radar"])

SUPPORTED = {"strong", "weak", "breakout", "breakdown", "institutional"}
DEFAULT_UNIVERSE = ["2330", "2317", "2454", "2308", "2412", "2603", "2881", "3008"]


@router.get("/{kind}", response_model=RadarResponse)
async def radar(kind: str) -> dict:
    if kind not in SUPPORTED:
        raise HTTPException(status_code=404, detail="Unsupported radar kind.")
    service = AnalysisService()
    items = []
    for symbol in DEFAULT_UNIVERSE:
        analysis = await service.analyze(symbol)
        technical = analysis["technical"]
        institutional = analysis["institutional"]
        include = (
            (kind == "strong" and analysis["adjusted_score"] >= 75)
            or (kind == "weak" and analysis["adjusted_score"] < 60)
            or (kind == "breakout" and "價格突破布林上軌" in technical["signals"])
            or (kind == "breakdown" and "價格跌破布林下軌" in technical["signals"])
            or (kind == "institutional" and institutional["five_day_total"] > 0)
        )
        if include:
            items.append(
                {
                    "symbol": symbol,
                    "name": None,
                    "score": analysis["adjusted_score"],
                    "reason": analysis["reasons"][0] if analysis["reasons"] else analysis["recommendation"],
                    "latest_close": technical["latest_close"],
                }
            )
    items.sort(key=lambda item: item["score"], reverse=kind != "weak")
    return {"kind": kind, "items": items[:20]}

