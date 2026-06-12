from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

TAIPEI_TZ = ZoneInfo("Asia/Taipei")
REGULAR_SESSION_START = time(9, 0)
REGULAR_SESSION_END = time(13, 30)
PRE_OPEN_START = time(8, 30)
POST_CLOSE_END = time(14, 0)


def taipei_now() -> datetime:
    return datetime.now(TAIPEI_TZ)


def taipei_today() -> date:
    return taipei_now().date()


def market_refresh_clock(now: datetime | None = None) -> dict:
    current = (now or taipei_now()).astimezone(TAIPEI_TZ)
    current_time = current.time()
    is_trading_day = current.weekday() < 5

    if is_trading_day and REGULAR_SESSION_START <= current_time <= REGULAR_SESSION_END:
        phase = "regular"
        label = "盤中"
        interval_seconds = 30
        is_live_refresh = True
        message = "盤中自動更新中，資料會依後端資料源可用性刷新。"
    elif is_trading_day and PRE_OPEN_START <= current_time < REGULAR_SESSION_START:
        phase = "pre_open"
        label = "盤前"
        interval_seconds = 300
        is_live_refresh = True
        message = "盤前準備中，會用較低頻率更新。"
    elif is_trading_day and REGULAR_SESSION_END < current_time <= POST_CLOSE_END:
        phase = "post_close"
        label = "盤後"
        interval_seconds = 120
        is_live_refresh = True
        message = "盤後整理中，分析會繼續短時間更新。"
    else:
        phase = "closed"
        label = "休市"
        interval_seconds = 900
        is_live_refresh = False
        message = "目前非台股交易時段，更新頻率會降低。"

    return {
        "now": current,
        "timezone": "Asia/Taipei",
        "market_phase": phase,
        "label": label,
        "is_trading_day": is_trading_day,
        "is_regular_session": phase == "regular",
        "is_live_refresh": is_live_refresh,
        "refresh_interval_seconds": interval_seconds,
        "next_refresh_at": current + timedelta(seconds=interval_seconds),
        "message": message,
    }
