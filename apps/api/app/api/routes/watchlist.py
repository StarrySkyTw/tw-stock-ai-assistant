import asyncio

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import WatchlistItem as WatchlistModel
from app.schemas import WatchlistCreate, WatchlistItem
from app.services.data_providers.composite import MarketDataService

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


@router.get("", response_model=list[WatchlistItem])
async def list_watchlist(db: Session = Depends(get_db)) -> list[dict]:
    items = db.query(WatchlistModel).order_by(WatchlistModel.created_at.desc()).all()
    service = MarketDataService()
    return list(await asyncio.gather(*(_watchlist_payload(item, service) for item in items)))


@router.post("", response_model=WatchlistItem)
async def create_watchlist_item(
    payload: WatchlistCreate, db: Session = Depends(get_db)
) -> dict:
    symbol = payload.symbol.upper().strip()
    if not symbol:
        raise HTTPException(status_code=422, detail="Stock symbol is required.")
    existing = db.query(WatchlistModel).filter(WatchlistModel.symbol == symbol).first()
    if existing:
        if payload.note is not None:
            existing.note = payload.note
        if payload.target_price is not None:
            existing.target_price = payload.target_price
        if payload.stop_price is not None:
            existing.stop_price = payload.stop_price
        db.commit()
        db.refresh(existing)
        return await _watchlist_payload(existing)

    item = WatchlistModel(
        symbol=symbol,
        note=payload.note,
        target_price=payload.target_price,
        stop_price=payload.stop_price,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return await _watchlist_payload(item)


@router.delete("/{item_id}")
async def delete_watchlist_item(item_id: int, db: Session = Depends(get_db)) -> dict[str, str]:
    item = db.get(WatchlistModel, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Watchlist item not found.")
    db.delete(item)
    db.commit()
    return {"status": "deleted"}


async def _watchlist_payload(item: WatchlistModel, service: MarketDataService | None = None) -> dict:
    lookup = service or MarketDataService()
    symbol = item.symbol.upper().strip()
    try:
        profile = await lookup.stock_profile(symbol)
    except Exception:
        profile = {"name": None}
    name = str(profile.get("name") or "").strip() or None
    return {
        "id": item.id,
        "symbol": symbol,
        "note": item.note,
        "target_price": item.target_price,
        "stop_price": item.stop_price,
        "name": name,
        "lookup_status": "verified" if name else "unknown_symbol",
        "created_at": item.created_at,
    }
