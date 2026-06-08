# Database Schema

第一版使用 PostgreSQL，SQLAlchemy models 位於 `apps/api/app/models/entities.py`，Alembic migration 位於 `apps/api/alembic/versions/0001_initial_schema.py`。

## Tables

- `instruments`：股票/ETF/指數主檔。
- `daily_prices`：日 OHLCV。
- `institutional_flows`：外資、投信、自營商、三大法人合計。
- `fundamentals`：EPS、ROE、毛利率、營益率、本益比、淨值比、營收年/月增。
- `monthly_revenues`：月營收與成長率。
- `margin_balances`：融資、融券、券資比。
- `shareholding_stats`：大戶持股比例、股東人數。
- `news_items`：新聞、公告、法說會資訊。
- `sentiment_scores`：LLM 情緒分數。
- `technical_snapshots`：技術指標快照。
- `analysis_results`：AI 評分與建議快照。
- `market_risk_snapshots`：Market Risk Engine 結果。
- `positions`：個人持倉設定。
- `watchlists`：觀察名單。
- `notification_channels`：通知管道設定。
- `notification_events`：通知事件紀錄。
- `reports`：PDF 報告檔案路徑。
- `backtest_runs`：回測結果與交易紀錄。

## Migration

Docker 啟動後 API 服務會執行：

```bash
alembic upgrade head
```

本機 SQLite 開發模式下，FastAPI startup 會自動建立資料表，方便快速測試 watchlist。

