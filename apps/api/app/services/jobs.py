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
        watchlist: list[dict] | None = None,
    ) -> dict:
        symbols = _normalize_symbols(symbols)
        position_map = {
            symbol: item
            for item in positions or []
            if (symbol := _normalize_symbol(str(item.get("symbol", ""))))
        }
        watchlist_map = {
            symbol: item
            for item in watchlist or []
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

        position_alerts = [
            _position_alert(item, position_map[item["symbol"]])
            for item in results
            if item["symbol"] in position_map
        ]
        if position_alerts:
            lines.append("")
            lines.append("持倉風險提醒")
            lines.extend(f"- {alert['summary']}" for alert in position_alerts)

        watchlist_alerts = [
            alert
            for item in results
            if item["symbol"] in watchlist_map
            if (alert := _watchlist_alert(item, watchlist_map[item["symbol"]])) is not None
        ]
        if watchlist_alerts:
            lines.append("")
            lines.append("自選到價提醒")
            lines.extend(f"- {alert['summary']}" for alert in watchlist_alerts)

        notify = await self.notifications.send("gmail", "台股 AI 每日盤後摘要", "\n".join(lines))
        return {
            "count": len(results),
            "results": results,
            "position_alerts": position_alerts,
            "watchlist_alerts": watchlist_alerts,
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


def _watchlist_alert(analysis: dict, item: dict) -> dict | None:
    close = _float_or_none(analysis.get("technical", {}).get("latest_close"))
    target_price = _positive_float_or_none(item.get("target_price"))
    stop_price = _positive_float_or_none(item.get("stop_price"))
    if close is None or (target_price is None and stop_price is None):
        return None

    triggered: list[str] = []
    if target_price is not None and close >= target_price:
        triggered.append("目標價觸及")
    if stop_price is not None and close <= stop_price:
        triggered.append("停損價觸及")
    if not triggered:
        return None

    symbol = analysis["symbol"]
    name = analysis.get("name") or ""
    status = "、".join(triggered)
    target_gap = _price_gap_percent(close, target_price)
    stop_gap = _price_gap_percent(close, stop_price)
    summary = (
        f"{symbol} {name}：收盤 {close:.2f}，{status}。"
        "這是到價提醒，不會自動下單。"
    )
    return {
        "symbol": symbol,
        "name": analysis.get("name"),
        "latest_close": close,
        "target_price": target_price,
        "stop_price": stop_price,
        "target_gap_percent": target_gap,
        "stop_gap_percent": stop_gap,
        "triggered": triggered,
        "summary": summary,
    }


def _positive_float_or_none(value: object) -> float | None:
    numeric = _float_or_none(value)
    if numeric is None or numeric <= 0:
        return None
    return numeric


def _price_gap_percent(close: float, reference: float | None) -> float | None:
    if reference is None:
        return None
    return round((close - reference) / reference * 100, 2)


def _float_or_none(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
