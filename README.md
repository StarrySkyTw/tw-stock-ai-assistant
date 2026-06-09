# 台股 AI 投資決策助手

這是一個個人研究用的台股投資決策輔助系統。它會整合價格、法人、基本面、籌碼、技術指標、市場風險與 AI 新聞摘要，輸出 100 分評分、建議、停損停利與風險燈號。

本系統不下單，也不保證獲利；所有輸出只作研究與紀律化決策參考。

## 專案結構

- `apps/api`：Python FastAPI 後端、資料 provider、指標、評分、回測、PDF、通知。
- `apps/web`：Next.js + TypeScript + TailwindCSS 前端儀表板。
- `infra`：Dockerfile。
- `docs`：API、資料庫與 Linear backlog 文件。

## 快速啟動

1. 複製環境檔：`copy .env.example .env`
2. 填入可選 token：`FINMIND_TOKEN`、`OPENAI_API_KEY`、Gmail/Telegram/LINE 設定。
3. 啟動：`docker compose up --build`
4. 前端：http://localhost:3000
5. 後端：http://localhost:8000/docs

沒有 token 時，後端會使用 deterministic sample data，方便先驗證 UI、回測、PDF 與通知 dry-run。

Windows 使用者也可以直接執行 `start-stockai.cmd`；啟動器會自動處理中文路徑的 Docker build 問題，並在啟動時重新 build 最新程式碼。

## 本機後端測試

```powershell
cd apps/api
python -m pip install ".[dev]"
pytest
```

## 本機前端測試

```powershell
cd apps/web
npm install
npm test
```

## 一鍵檢查

```powershell
powershell -ExecutionPolicy Bypass -File scripts/check.ps1
```

## 主要功能

- 股票分析：`/api/v1/stocks/{symbol}/analysis`
- Plotly K 線圖：`/api/v1/stocks/{symbol}/chart`
- Market Risk Engine：`/api/v1/market/risk`
- 1/3/5 年回測：`/api/v1/backtests`
- 雷達排行：`/api/v1/radar/{kind}`
- PDF 報告：`/api/v1/reports/{symbol}/pdf`
- Gmail/Telegram/LINE Messaging API 通知測試：`/api/v1/notifications/test`
- 資料可信度：分析結果會回傳 `data_sources`，前端總覽會標示價格、法人、基本面、股權分布、新聞是否使用 sample fallback。
- 後端自選清單：`/api/v1/watchlist` 可儲存自選股，前端可同步清單，盤後 job 未指定股票時會優先使用這份清單。
- 後端持倉清單：`/api/v1/positions` 可儲存買進價、股數與持倉最高價，前端持倉分頁可套用分析。
- 盤後持倉提醒：`/api/v1/jobs/daily-after-close` 會把 open positions 納入掃描，回傳 `position_alerts` 並在通知摘要列出停損/停利觸發狀態。
