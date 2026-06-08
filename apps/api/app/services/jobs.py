from __future__ import annotations

from app.services.analysis import AnalysisService
from app.services.notifications import NotificationService


class DailyJobService:
    def __init__(self) -> None:
        self.analysis = AnalysisService()
        self.notifications = NotificationService()

    async def run_after_close(self, symbols: list[str] | None = None) -> dict:
        symbols = symbols or ["2330", "2317", "2454"]
        results = []
        for symbol in symbols:
            item = await self.analysis.analyze(symbol)
            results.append(item)
        lines = ["台股 AI 每日盤後摘要"]
        for item in results:
            lines.append(f"{item['symbol']}: {item['recommendation']} / {item['adjusted_score']} 分")
        notify = await self.notifications.send("gmail", "台股 AI 每日盤後摘要", "\n".join(lines))
        return {"count": len(results), "results": results, "notification": notify.to_dict()}

