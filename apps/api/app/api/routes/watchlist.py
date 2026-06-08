from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import WatchlistItem as WatchlistModel
from app.schemas import WatchlistCreate, WatchlistItem

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


@router.get("", response_model=list[WatchlistItem])
async def list_watchlist(db: Session = Depends(get_db)) -> list[WatchlistModel]:
    return db.query(WatchlistModel).order_by(WatchlistModel.created_at.desc()).all()


@router.post("", response_model=WatchlistItem)
async def create_watchlist_item(
    payload: WatchlistCreate, db: Session = Depends(get_db)
) -> WatchlistModel:
    item = WatchlistModel(
        symbol=payload.symbol.upper(),
        note=payload.note,
        target_price=payload.target_price,
        stop_price=payload.stop_price,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/{item_id}")
async def delete_watchlist_item(item_id: int, db: Session = Depends(get_db)) -> dict[str, str]:
    item = db.get(WatchlistModel, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Watchlist item not found.")
    db.delete(item)
    db.commit()
    return {"status": "deleted"}

