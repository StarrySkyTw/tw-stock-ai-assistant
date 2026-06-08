from fastapi import APIRouter

from app.services.jobs import DailyJobService

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("/daily-after-close")
async def run_daily_after_close(symbols: list[str] | None = None) -> dict:
    return await DailyJobService().run_after_close(symbols)

