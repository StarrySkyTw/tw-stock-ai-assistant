from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Instrument, Position
from app.schemas import PositionCreate, PositionItem, PositionUpdate

router = APIRouter(prefix="/positions", tags=["positions"])


@router.get("", response_model=list[PositionItem])
async def list_positions(
    status: str = Query(default="open", pattern="^(open|closed|all)$"),
    db: Session = Depends(get_db),
) -> list[PositionItem]:
    query = db.query(Position, Instrument).join(Instrument, Position.instrument_id == Instrument.id)
    if status != "all":
        query = query.filter(Position.status == status)
    rows = query.order_by(Position.created_at.desc()).all()
    return [_serialize_position(position, instrument) for position, instrument in rows]


@router.post("", response_model=PositionItem)
async def create_position(payload: PositionCreate, db: Session = Depends(get_db)) -> PositionItem:
    symbol = _normalize_symbol(payload.symbol)
    instrument = _get_or_create_instrument(db, symbol)
    existing = (
        db.query(Position)
        .filter(Position.instrument_id == instrument.id, Position.status == "open")
        .first()
    )
    if existing:
        existing.entry_price = payload.entry_price
        existing.quantity = payload.quantity
        existing.highest_price = payload.highest_price
        existing.entry_date = payload.entry_date
        db.commit()
        db.refresh(existing)
        return _serialize_position(existing, instrument)

    position = Position(
        instrument_id=instrument.id,
        entry_date=payload.entry_date,
        entry_price=payload.entry_price,
        quantity=payload.quantity,
        highest_price=payload.highest_price,
        status="open",
    )
    db.add(position)
    db.commit()
    db.refresh(position)
    return _serialize_position(position, instrument)


@router.patch("/{position_id}", response_model=PositionItem)
async def update_position(
    position_id: int,
    payload: PositionUpdate,
    db: Session = Depends(get_db),
) -> PositionItem:
    position = db.get(Position, position_id)
    if not position:
        raise HTTPException(status_code=404, detail="Position not found.")
    instrument = db.get(Instrument, position.instrument_id)
    if not instrument:
        raise HTTPException(status_code=404, detail="Instrument not found.")

    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(position, key, value)
    db.commit()
    db.refresh(position)
    return _serialize_position(position, instrument)


@router.delete("/{position_id}", response_model=PositionItem)
async def close_position(position_id: int, db: Session = Depends(get_db)) -> PositionItem:
    position = db.get(Position, position_id)
    if not position:
        raise HTTPException(status_code=404, detail="Position not found.")
    instrument = db.get(Instrument, position.instrument_id)
    if not instrument:
        raise HTTPException(status_code=404, detail="Instrument not found.")
    position.status = "closed"
    db.commit()
    db.refresh(position)
    return _serialize_position(position, instrument)


def _get_or_create_instrument(db: Session, symbol: str) -> Instrument:
    instrument = db.query(Instrument).filter(Instrument.symbol == symbol).first()
    if instrument:
        return instrument
    instrument = Instrument(symbol=symbol, name=None)
    db.add(instrument)
    db.commit()
    db.refresh(instrument)
    return instrument


def _serialize_position(position: Position, instrument: Instrument) -> PositionItem:
    return PositionItem(
        id=position.id,
        symbol=instrument.symbol,
        name=instrument.name,
        entry_date=position.entry_date,
        entry_price=position.entry_price,
        quantity=position.quantity,
        highest_price=position.highest_price,
        status=position.status,
        created_at=position.created_at,
        updated_at=position.updated_at,
    )


def _normalize_symbol(value: str) -> str:
    symbol = "".join(ch for ch in value.upper().strip() if ch.isalnum() or ch in {".", "^", "-"})
    if not symbol:
        raise HTTPException(status_code=422, detail="Invalid symbol.")
    return symbol
