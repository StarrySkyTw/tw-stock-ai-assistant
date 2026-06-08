# API Design

Base URL: `/api/v1`

## Stock Analysis

`GET /stocks/{symbol}/analysis?entry_price=&highest_price=&atr_multiplier=2`

回傳 `AnalysisResponse`，包含：

- `raw_score`、`adjusted_score`、`recommendation`
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

