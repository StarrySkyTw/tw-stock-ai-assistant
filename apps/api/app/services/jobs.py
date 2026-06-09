from __future__ import annotations

from app.services.analysis import AnalysisService
from app.services.notifications import NotificationService


class DailyJobService:
    def __init__(self) -> None:
        self.analysis = AnalysisService()
        self.notifications = NotificationService()

    async def run_after_close(
        self,
        symbols: list[str] | None = None,
        positions: list[dict] | None = None,
    ) -> dict:
        symbols = _normalize_symbols(symbols)
        position_map = {
            symbol: item
            for item in positions or []
            if (symbol := _normalize_symbol(str(item.get("symbol", ""))))
        }
        results = []
        for symbol in symbols:
            position = position_map.get(symbol)
            item = await self.analysis.analyze(
                symbol,
                entry_price=_float_or_none(position.get("entry_price")) if position else None,
                highest_price=_float_or_none(position.get("highest_price")) if position else None,
            )
            results.append(item)
        lines = ["台股 AI 每日盤後摘要"]
        for item in results:
            lines.append(f"{item['symbol']}: {item['recommendation']} / {item['adjusted_score']} 分")

        position_alerts = [_position_alert(item, position_map[item["symbol"]]) for item in results if item["symbol"] in position_map]
        if position_alerts:
            lines.append("")
            lines.append("持倉風險提醒")
            lines.extend(f"- {alert['summary']}" for alert in position_alerts)

        notify = await self.notifications.send("gmail", "台股 AI 每日盤後摘要", "\n".join(lines))
        return {
            "count": len(results),
            "results": results,
            "position_alerts": position_alerts,
            "notification": notify.to_dict(),
        }


def _normalize_symbols(symbols: list[str] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for item in symbols or ["2330", "2317", "2454"]:
        symbol = "".join(ch for ch in item.upper().strip() if ch.isalnum() or ch in {".", "^", "-"})
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        normalized.append(symbol)
        if len(normalized) >= 20:
            break
    return normalized or ["2330", "2317", "2454"]


def _normalize_symbol(value: str) -> str | None:
    symbol = "".join(ch for ch in value.upper().strip() if ch.isalnum() or ch in {".", "^", "-"})
    return symbol or None


def _position_alert(analysis: dict, position: dict) -> dict:
    entry_price = _float_or_none(position.get("entry_price")) or analysis["technical"]["latest_close"]
    quantity = _float_or_none(position.get("quantity")) or 0
    close = analysis["technical"]["latest_close"]
    profit_percent = ((close - entry_price) / entry_price) * 100 if entry_price else 0
    stop = analysis["stop_loss"]
    trailing = analysis["trailing_take_profit"]
    triggered: list[str] = []
    atr_stop = _float_or_none(stop.get("atr_stop"))
    trailing_price = _float_or_none(trailing.get("current_take_profit_price"))

    if atr_stop is not None and close <= atr_stop:
        triggered.append("ATR 停損")
    if trailing_price is not None and close <= trailing_price and close > entry_price:
        triggered.append("移動停利")
    if stop.get("ma60_stop_triggered"):
        triggered.append("MA60 跌破")
    elif stop.get("ma20_stop_triggered"):
        triggered.append("MA20 跌破")

    status = "、".join(triggered) if triggered else "未觸發主要停損"
    summary = (
        f"{analysis['symbol']} {analysis.get('name') or ''}：收盤 {close:.2f}，"
        f"損益 {profit_percent:+.2f}%，{status}。"
    )
    return {
        "symbol": analysis["symbol"],
        "entry_price": entry_price,
        "quantity": quantity,
        "latest_close": close,
        "profit_percent": round(profit_percent, 2),
        "triggered": triggered,
        "summary": summary,
    }


def _float_or_none(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
