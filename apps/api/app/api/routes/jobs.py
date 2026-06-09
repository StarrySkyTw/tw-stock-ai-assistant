from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Instrument, Position, WatchlistItem
from app.services.jobs import DailyJobService

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("/daily-after-close")
async def run_daily_after_close(
    symbols: list[str] | None = Body(default=None),
    db: Session = Depends(get_db),
) -> dict:
    open_positions = (
        db.query(Position, Instrument)
        .join(Instrument, Position.instrument_id == Instrument.id)
        .filter(Position.status == "open")
        .all()
    )
    position_payloads = [
        {
            "symbol": instrument.symbol,
            "entry_price": position.entry_price,
            "quantity": position.quantity,
            "highest_price": position.highest_price,
        }
        for position, instrument in open_positions
    ]
    if not symbols:
        watchlist_symbols = [
            item.symbol
            for item in db.query(WatchlistItem).order_by(WatchlistItem.created_at.asc()).all()
        ]
        position_symbols = [item["symbol"] for item in position_payloads]
        symbols = [*watchlist_symbols, *position_symbols]
    return await DailyJobService().run_after_close(symbols, positions=position_payloads)
