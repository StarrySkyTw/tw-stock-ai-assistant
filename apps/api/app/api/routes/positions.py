from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.models import Instrument, Position
from app.schemas import PositionCreate, PositionDecisionItem, PositionItem, PositionUpdate
from app.services.analysis import AnalysisService
from app.services.future_outlook import build_fallback_future_outlook, build_future_outlook
from app.services.market_context import build_market_context
from app.services.source_quality import is_trusted_source

router = APIRouter(prefix="/positions", tags=["positions"])

EVENT_RISK_KEYWORDS = (
    "制裁",
    "關稅",
    "出口管制",
    "禁令",
    "調查",
    "罰款",
    "訴訟",
    "戰爭",
    "地緣",
    "兩岸",
    "美中",
    "政治",
    "政策",
    "法規",
    "停工",
    "火災",
    "缺料",
    "下修",
    "衰退",
    "虧損",
    "違約",
)
EVENT_POSITIVE_KEYWORDS = (
    "調升",
    "接單",
    "成長",
    "新高",
    "大單",
    "擴產",
    "需求",
    "核准",
    "通過",
    "轉強",
    "法說會樂觀",
    "營收創高",
)


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


@router.get("/decisions", response_model=list[PositionDecisionItem])
async def list_position_decisions(
    status: str = Query(default="open", pattern="^(open|closed|all)$"),
    db: Session = Depends(get_db),
) -> list[PositionDecisionItem]:
    query = db.query(Position, Instrument).join(Instrument, Position.instrument_id == Instrument.id)
    if status != "all":
        query = query.filter(Position.status == status)
    rows = query.order_by(Position.created_at.desc()).all()
    service = AnalysisService()
    analysis_timeout = get_settings().analysis_background_timeout_seconds

    async def analyze_position(position: Position, instrument: Instrument) -> PositionDecisionItem:
        item = _serialize_position(position, instrument)
        try:
            analysis = await service.analyze(
                instrument.symbol,
                entry_price=position.entry_price,
                highest_price=position.highest_price,
                data_timeout_seconds=analysis_timeout,
            )
        except Exception as exc:
            return _fallback_position_decision(item, exc)
        return _build_position_decision(item, analysis)

    return await asyncio.gather(*(analyze_position(position, instrument) for position, instrument in rows))


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


def _build_position_decision(position: PositionItem, analysis: dict[str, Any]) -> PositionDecisionItem:
    data_sources = analysis.get("data_sources", {})
    market_context = build_market_context(analysis, position.symbol)
    latest_close = _positive_float_or_none(analysis.get("technical", {}).get("latest_close"))
    quantity = max(0.0, float(position.quantity or 0))
    cost_basis = round(float(position.entry_price) * quantity, 2)
    market_value = round(latest_close * quantity, 2) if latest_close is not None else None
    unrealized_pnl = (
        round((latest_close - float(position.entry_price)) * quantity, 2)
        if latest_close is not None
        else None
    )
    unrealized_pnl_percent = (
        round((latest_close / float(position.entry_price) - 1) * 100, 2)
        if latest_close is not None and position.entry_price
        else None
    )

    priority_factors = [
        _event_signal(analysis, data_sources),
        _revenue_signal(analysis, data_sources),
        *market_context["signals"],
        _market_signal(analysis),
    ]
    bullish_factors = [signal for signal in priority_factors if signal["tone"] == "positive"]
    risk_factors = [signal for signal in priority_factors if signal["tone"] == "risk"]
    bullish_factors.extend(_analysis_lines("analysis", analysis.get("reasons", []), "分析理由", "positive", 3))
    risk_factors.extend(_analysis_lines("risk", analysis.get("risks", []), "分析風險", "risk", 3))

    action = _decide_position_action(
        analysis=analysis,
        data_sources=data_sources,
        latest_close=latest_close,
        market_context=market_context,
        priority_factors=priority_factors,
        unrealized_pnl_percent=unrealized_pnl_percent,
    )
    confidence = _position_confidence(analysis, data_sources, market_context, priority_factors, latest_close)
    headline = _position_headline(action, market_context, priority_factors, unrealized_pnl_percent)
    rationale = _position_rationale(action, analysis, market_context, priority_factors)
    future_outlook = build_future_outlook(
        position=position,
        analysis=analysis,
        market_context=market_context,
        priority_factors=priority_factors,
        latest_close=latest_close,
        action=action,
        unrealized_pnl_percent=unrealized_pnl_percent,
    )

    return PositionDecisionItem(
        position=position,
        latest_close=latest_close,
        cost_basis=cost_basis,
        market_value=market_value,
        unrealized_pnl=unrealized_pnl,
        unrealized_pnl_percent=unrealized_pnl_percent,
        action=action,
        action_label=_action_label(action),
        confidence=confidence,
        headline=headline,
        rationale=rationale,
        priority_factors=priority_factors,
        bullish_factors=bullish_factors[:5],
        risk_factors=risk_factors[:6],
        future_outlook=future_outlook,
        next_review_triggers=_position_review_triggers(analysis, market_context),
        data_quality=_position_data_quality(data_sources, market_context),
    )


def _fallback_position_decision(position: PositionItem, exc: Exception) -> PositionDecisionItem:
    detail = f"庫存分析暫時失敗：{type(exc).__name__}。先保留紀錄，不做買賣判斷。"
    signal = _signal("system", "分析狀態", detail, "neutral", 1)
    return PositionDecisionItem(
        position=position,
        latest_close=None,
        cost_basis=round(float(position.entry_price) * max(0.0, float(position.quantity or 0)), 2),
        market_value=None,
        unrealized_pnl=None,
        unrealized_pnl_percent=None,
        action="watch",
        action_label=_action_label("watch"),
        confidence="低",
        headline="資料不足，先只記錄庫存",
        rationale="後端分析未完成前，不用這筆庫存資料判斷賣出、續抱、減碼或加碼。",
        priority_factors=[signal],
        bullish_factors=[],
        risk_factors=[signal],
        future_outlook=build_fallback_future_outlook(),
        next_review_triggers=["確認 API 與資料來源後重新整理庫存。"],
        data_quality=["庫存資料已保存，但分析資料未完成。"],
    )


def _event_signal(analysis: dict[str, Any], data_sources: dict[str, str]) -> dict[str, Any]:
    source = data_sources.get("news")
    sentiment = analysis.get("sentiment", {})
    headlines = [str(item) for item in sentiment.get("headlines", []) if item]
    text = " ".join(headlines)
    score = _float_or_none(sentiment.get("score")) or 0.0
    label = str(sentiment.get("label") or "neutral")
    has_risk_keyword = any(keyword in text for keyword in EVENT_RISK_KEYWORDS)
    has_positive_keyword = any(keyword in text for keyword in EVENT_POSITIVE_KEYWORDS)

    if not is_trusted_source(source, "news"):
        return _signal(
            "event",
            "重大新聞 / 政治",
            f"新聞來源為 {source or 'unknown'}，不足以判斷政治、政策或重大消息利多利空。",
            "neutral",
            1,
        )
    if label == "negative" or score <= -0.25 or has_risk_keyword:
        headline = headlines[0] if headlines else str(sentiment.get("summary") or "新聞情緒偏負向")
        return _signal(
            "event",
            "重大新聞 / 政治",
            f"優先風險：{headline}。重大消息或政治/政策風險先於技術面判斷。",
            "risk",
            1,
        )
    if label == "positive" or score >= 0.25 or has_positive_keyword:
        headline = headlines[0] if headlines else str(sentiment.get("summary") or "新聞情緒偏正向")
        return _signal(
            "event",
            "重大新聞 / 政治",
            f"偏利多：{headline}。仍需搭配營收與支撐，不因消息追高。",
            "positive",
            1,
        )
    return _signal(
        "event",
        "重大新聞 / 政治",
        str(sentiment.get("summary") or "重大新聞目前中性，未偵測到明確利多或利空。"),
        "neutral",
        1,
    )


def _revenue_signal(analysis: dict[str, Any], data_sources: dict[str, str]) -> dict[str, Any]:
    if not is_trusted_source(data_sources.get("fundamental"), "fundamental"):
        return _signal(
            "revenue",
            "營收",
            "營收來源不是官方或 FinMind 等可信資料，本輪不把營收當成利多利空。",
            "neutral",
            1,
        )
    metrics = analysis.get("fundamental_gate", {}).get("metrics", {})
    revenue_yoy = _float_or_none(metrics.get("revenue_yoy"))
    revenue_mom = _float_or_none(metrics.get("revenue_mom"))
    if revenue_yoy is not None and revenue_yoy < 0:
        return _signal(
            "revenue",
            "營收",
            f"營收年增 {revenue_yoy:.1f}% 為負，先視為優先利空，除非後續公告修復。",
            "risk",
            1,
        )
    if revenue_mom is not None and revenue_mom <= -10:
        return _signal(
            "revenue",
            "營收",
            f"營收月減 {abs(revenue_mom):.1f}% 過大，需先確認是季節性還是結構性轉弱。",
            "risk",
            1,
        )
    if revenue_yoy is not None and revenue_yoy >= 10 and (revenue_mom is None or revenue_mom >= 0):
        mom_text = "月增資料不足" if revenue_mom is None else f"月增 {revenue_mom:.1f}%"
        return _signal(
            "revenue",
            "營收",
            f"營收年增 {revenue_yoy:.1f}% 且{mom_text}，基本動能偏利多。",
            "positive",
            1,
        )
    if revenue_yoy is not None:
        return _signal(
            "revenue",
            "營收",
            f"營收年增 {revenue_yoy:.1f}%，尚未形成明確利多或利空。",
            "neutral",
            1,
        )
    return _signal("revenue", "營收", "營收資料不足，等待月營收或財報更新後重判斷。", "neutral", 1)


def _market_signal(analysis: dict[str, Any]) -> dict[str, Any]:
    light = str(analysis.get("risk_lights", {}).get("composite", "yellow"))
    if light == "red":
        return _signal("market", "大盤風險", "大盤綜合燈號為紅燈，庫存先以降低風險為主。", "risk", 2)
    if light == "green":
        return _signal("market", "大盤風險", "大盤綜合燈號為綠燈，若個股事件與營收沒轉壞，可續抱觀察。", "positive", 2)
    return _signal("market", "大盤風險", "大盤綜合燈號為黃燈，部位不宜過度放大。", "neutral", 2)


def _decide_position_action(
    *,
    analysis: dict[str, Any],
    data_sources: dict[str, str],
    latest_close: float | None,
    market_context: dict[str, Any],
    priority_factors: list[dict[str, Any]],
    unrealized_pnl_percent: float | None,
) -> str:
    trusted_price = latest_close is not None and is_trusted_source(data_sources.get("price"), "price")
    if not trusted_price:
        return "watch"

    event_risk = _has_priority_risk(priority_factors, "event")
    revenue_risk = _has_priority_risk(priority_factors, "revenue")
    event_positive = _has_priority_positive(priority_factors, "event")
    revenue_positive = _has_priority_positive(priority_factors, "revenue")
    decision = analysis.get("research_decision", {})
    stance = str(decision.get("stance") or "watch")
    timing_status = str(analysis.get("timing_gate", {}).get("status") or "unknown")
    fundamental_status = str(analysis.get("fundamental_gate", {}).get("status") or "unknown")
    no_chase = bool(decision.get("do_not_chase_reason"))
    stop_loss = analysis.get("stop_loss", {})
    stop_triggered = bool(stop_loss.get("ma60_stop_triggered") or stop_loss.get("ma20_stop_triggered"))
    invalidation_price = _float_or_none(analysis.get("timing_gate", {}).get("invalidation_price"))
    invalidation_broken = bool(invalidation_price is not None and latest_close <= invalidation_price)

    if event_risk and (revenue_risk or stop_triggered or invalidation_broken):
        return "sell" if stop_triggered or invalidation_broken or (unrealized_pnl_percent is not None and unrealized_pnl_percent <= -8) else "reduce"
    if event_risk or revenue_risk:
        return "reduce"
    if stop_triggered or invalidation_broken:
        return "reduce"
    if stance in {"avoid", "reduce_risk"} or timing_status == "fail":
        if market_context.get("event_window") and not (event_risk or revenue_risk or stop_triggered or invalidation_broken):
            return "hold"
        return "reduce"
    if market_context.get("event_window") and market_context.get("no_confirmed_bullish"):
        return "hold"
    if event_positive and revenue_positive and fundamental_status == "pass" and timing_status == "pass" and not no_chase:
        return "add" if unrealized_pnl_percent is None or unrealized_pnl_percent < 12 else "hold"
    return "hold"


def _position_confidence(
    analysis: dict[str, Any],
    data_sources: dict[str, str],
    market_context: dict[str, Any],
    priority_factors: list[dict[str, Any]],
    latest_close: float | None,
) -> str:
    if latest_close is None or not is_trusted_source(data_sources.get("price"), "price"):
        return "低"
    if not is_trusted_source(data_sources.get("news"), "news") or not is_trusted_source(data_sources.get("fundamental"), "fundamental"):
        return "低"
    if market_context.get("event_window") and market_context.get("no_confirmed_bullish"):
        return "中"
    if any(signal["tone"] == "risk" for signal in priority_factors):
        return "中"
    return str(analysis.get("research_decision", {}).get("confidence") or "中")


def _position_headline(action: str, market_context: dict[str, Any], priority_factors: list[dict[str, Any]], pnl_percent: float | None) -> str:
    priority_risk = next((signal for signal in priority_factors if signal["tone"] == "risk"), None)
    pnl_text = "" if pnl_percent is None else f"未實現損益 {pnl_percent:+.1f}%："
    if action == "sell":
        return f"{pnl_text}重大風險優先，先做離場檢查"
    if action == "reduce":
        reason = priority_risk["label"] if priority_risk else "風險條件"
        return f"{pnl_text}{reason}偏弱，偏向減碼控風險"
    if action == "add":
        return f"{pnl_text}事件與營收沒有轉壞，可小幅加碼研究"
    if action == "hold":
        if market_context.get("event_window") and market_context.get("no_confirmed_bullish"):
            return f"{pnl_text}事件前震盪，續抱但不加碼"
        return f"{pnl_text}續抱觀察，等待下一個事件或營收驗證"
    return "資料不足，先只記錄庫存"


def _position_rationale(action: str, analysis: dict[str, Any], market_context: dict[str, Any], priority_factors: list[dict[str, Any]]) -> str:
    priority_text = "；".join(signal["detail"] for signal in priority_factors[:4])
    next_action = str(analysis.get("research_decision", {}).get("next_action") or "")
    if market_context.get("event_window") and action == "hold":
        return (
            f"本輪先把事件催化與籌碼情境放在價格訊號前面：{priority_text}。"
            f"重大事件公布前不把震盪當成完整利空，也不把反彈當成利多；先續抱、壓低加碼衝動，等事件後重算。{next_action}"
        )
    if action in {"sell", "reduce"}:
        return f"第 1 優先看重大新聞/政治與營收：{priority_text}。因此先降低庫存風險；{next_action}"
    if action == "add":
        return f"重大事件與營收未轉壞，且基本面/K 線條件較完整；只能小幅分批研究，仍需遵守失效價。{next_action}"
    if action == "hold":
        return f"重大事件與營收尚未給出明確利空，先續抱觀察；若新聞、政治、營收或失效價轉弱要重新判斷。{next_action}"
    return "資料品質不足時不做買賣判斷；先把均價與股數保存，等重大消息、營收與價格資料同步後再看。"


def _position_review_triggers(analysis: dict[str, Any], market_context: dict[str, Any]) -> list[str]:
    triggers = list(analysis.get("research_decision", {}).get("review_triggers", []))
    priority = [
        *market_context.get("review_triggers", []),
        "重大新聞、政策、政治或地緣風險出現時立即重算。",
        "月營收、財報、法說會公告後優先重新判斷。",
        "跌破失效價、MA60 或 ATR 停損價時檢查是否減碼或離場。",
    ]
    return [*priority, *triggers][:6]


def _position_data_quality(data_sources: dict[str, str], market_context: dict[str, Any]) -> list[str]:
    labels = {
        "price": "價格",
        "fundamental": "基本面/營收",
        "news": "重大新聞",
        "institutional": "法人",
        "margin": "信用交易",
    }
    rows = [f"{label}來源：{data_sources.get(key, 'unknown')}" for key, label in labels.items()]
    if not is_trusted_source(data_sources.get("news"), "news"):
        rows.append("重大新聞/政治資料不足時，庫存決策信心降為低。")
    if not is_trusted_source(data_sources.get("fundamental"), "fundamental"):
        rows.append("營收不是可信來源時，不把營收當成利多利空。")
    rows.extend(market_context.get("data_quality", []))
    return rows


def _analysis_lines(kind: str, values: list[Any], label: str, tone: str, priority: int) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for value in values[:3]:
        text = str(value).strip()
        if text:
            result.append(_signal(kind, label, text, tone, priority))
    return result


def _has_priority_risk(signals: list[dict[str, Any]], kind: str) -> bool:
    return any(signal["kind"] == kind and signal["tone"] == "risk" for signal in signals)


def _has_priority_positive(signals: list[dict[str, Any]], kind: str) -> bool:
    return any(signal["kind"] == kind and signal["tone"] == "positive" for signal in signals)


def _signal(kind: str, label: str, detail: str, tone: str, priority: int) -> dict[str, Any]:
    return {"kind": kind, "label": label, "detail": detail, "tone": tone, "priority": priority}


def _action_label(action: str) -> str:
    labels = {
        "sell": "偏向賣出 / 離場檢查",
        "reduce": "偏向減碼",
        "hold": "續抱觀察",
        "add": "可小幅加碼研究",
        "watch": "只記錄，先觀察",
    }
    return labels.get(action, "只記錄，先觀察")


def _float_or_none(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _positive_float_or_none(value: object) -> float | None:
    number = _float_or_none(value)
    return number if number is not None and number > 0 else None
