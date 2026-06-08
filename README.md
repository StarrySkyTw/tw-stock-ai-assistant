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

## 主要功能

- 股票分析：`/api/v1/stocks/{symbol}/analysis`
- Plotly K 線圖：`/api/v1/stocks/{symbol}/chart`
- Market Risk Engine：`/api/v1/market/risk`
- 1/3/5 年回測：`/api/v1/backtests`
- 雷達排行：`/api/v1/radar/{kind}`
- PDF 報告：`/api/v1/reports/{symbol}/pdf`
- Gmail/Telegram/LINE Messaging API 通知測試：`/api/v1/notifications/test`

