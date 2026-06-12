# API Design

Base URL: `/api/v1`

## Stock Analysis

`GET /stocks/{symbol}/analysis?entry_price=&highest_price=&atr_multiplier=2`

回傳 `AnalysisResponse`，包含：

- `raw_score`、`adjusted_score`、`recommendation`
- `generated_at`、`data_sources`
- `reasons[]`、`risks[]`
- `technical`：MA、RSI、KD、MACD、Bollinger、ATR
- `institutional`：近 5/20/60 日法人趨勢
- `fundamental`：EPS、ROE、毛利率、營益率、本益比、淨值比、營收年/月增
- `sentiment`：OpenAI 或規則式新聞情緒
- `stop_loss`：固定%、ATR、MA20/MA60
- `trailing_take_profit`：最高價 - N * ATR
- `risk_lights`：大盤、法人、技術、風險、綜合燈號

## Chart

`GET /stocks/{symbol}/chart?range=1y|3y|5y`

回傳 Plotly figure JSON，前端直接渲染。

## Market

- `GET /market/risk`
- `GET /market/overview`

## Backtest

`POST /backtests`

```json
{
  "symbol": "2330",
  "years": 1,
  "strategy": "score_ma_atr",
  "initial_capital": 100000
}
```

回傳勝率、最大回撤、年化報酬率、Sharpe Ratio、交易紀錄與 equity curve。

## Notifications

`POST /notifications/test`

```json
{
  "channel": "gmail",
  "subject": "測試",
  "message": "測試通知"
}
```

沒有憑證時會回傳 `dry_run`，不會拋錯。

## Watchlist

- `GET /watchlist`
- `POST /watchlist`
- `DELETE /watchlist/{item_id}`

`POST /watchlist` 會以股票代號去重；重複送出同一代號時回傳既有項目，並更新有帶入的 note/target/stop 欄位。

## Positions

- `GET /positions?status=open|closed|all`
- `POST /positions`
- `PATCH /positions/{position_id}`
- `DELETE /positions/{position_id}`

`POST /positions` 會以 open position 去重；同一股票已經有 open position 時會更新買進價、股數、最高價與買進日期。`DELETE` 會把 position 標記為 `closed`，不會直接刪除歷史。

## Jobs

`POST /jobs/daily-after-close`

若 body 沒有提供股票代號清單，會優先使用後端 watchlist 與 open positions；兩者都為空時才使用預設 `2330, 2317, 2454`。若有 open positions，回傳會包含 `position_alerts`，並在通知摘要列出 ATR 停損、移動停利、MA20/MA60 觸發狀態。

若 watchlist item 有設定 `target_price` 或 `stop_price`，daily job 也會回傳 `watchlist_alerts`。這是到價提醒，只進通知摘要，不會自動下單。
