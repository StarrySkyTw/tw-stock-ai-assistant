# Product Roadmap

This project is a decision assistant, not an order system. The next upgrades should help the user answer three questions faster:

1. Should I act now, wait, or reduce risk?
2. What exact price or signal would change the plan?
3. Is the data reliable enough to trust the conclusion?

## External Product References

Research checked on 2026-06-15:

- YouTube: 林鈺凱分析師-摩爾證券投顧, `https://www.youtube.com/@win16888`.
- TradingView screeners: focus on configurable filters, columns, and table/chart switching.
- TradingView watchlists: advanced watchlists group symbols and expose overview, news, fundamentals, technicals, risk, and notes.
- CMoney products: 籌碼 K 線 emphasizes主力籌碼, 三大法人, and multiple chip indicators; several products sell the idea of low-position opportunities and risk warnings.
- Taiwan stock app comparisons: common winners combine clear UI, fast workflow, K-line/technical analysis, chip analysis, fundamental analysis, automatic/AI stock picking, and portfolio tracking.

Useful product lessons for this app:

- Keep the first screen decision-first. Avoid showing the same score in several places before the user sees a plan.
- Treat watchlists as a research workspace, not only a symbol input. Add notes, tags, and grouped views later.
- Make every strategy conditional: entry trigger, invalidation trigger, stop, and next review time.
- Separate "data quality" from "decision". Data quality should warn the user, not compete with the main action.
- Use compact cards for repeated rows, but avoid nested cards inside analysis panels.

## Analyst-Style Behavior

The app should answer like a careful analyst:

- Start with stance: prepare entry, hold, wait, or reduce risk.
- Explain with K-line and chips first, then fundamentals/news as supporting evidence.
- Do not say "buy" directly. Say "if support holds, research a small entry" or "if MA60 breaks, reduce risk."
- For "逢低買不殺低", require conditions:
  - price is above or reclaiming MA20/MA60
  - market risk is not red
  - RSI is not overheated
  - volume is not panic-selling through support
  - invalidation price is known before entry

## Web App Next Steps

Design target:

- Use `docs/design-assets/research-dashboard-target.png` as the UI direction for the next dashboard iterations.
- The target is a conservative research workspace: first-screen research conclusion, three gates, no-chase rule, watchlist table, and decision journal.
- The image is an AI-generated concept created during implementation, not the current app screenshot.

Already improved:

- Faster launch path: normal desktop start no longer rebuilds Docker every time.
- Faster refresh feel: individual analysis and chart render before AI picks finish.
- K-line strategy: `kline_analysis` now gives support, resistance, strategy notes, and invalidation.
- OpenAI status: UI now shows fallback reasons such as insufficient quota.

Next web improvements:

1. Add a watchlist table with columns: stance, score, latest close, MA20 distance, risk light, AI-news status, and note.
2. Add a "decision journal" so each stock has a saved thesis, invalidation price, and review trigger.
3. Add a compact analyst chat panel that answers from the existing analysis JSON before any live OpenAI call.
4. Cache repeated data-provider calls for a short TTL during refreshes.
5. Split AI picks refresh from chart refresh completely, with independent refresh buttons.

## iOS Possibility

Best path: keep this project as the backend and build a SwiftUI client later.

Suggested iOS app shape:

- Tab 1: Dashboard, showing market risk and top analyst brief.
- Tab 2: Watchlist, grouped by stance and risk.
- Tab 3: Stock Detail, with K-line summary, chart, support/resistance, and decision journal.
- Tab 4: Positions, with stop loss, trailing take profit, and review alerts.
- Tab 5: Settings, for API endpoint, theme, notifications, and OpenAI status.

SwiftUI architecture:

- Use `TabView` plus per-tab `NavigationStack`.
- Keep feature-local UI state in `@State`.
- Use async loading with `.task(id:)` for symbol/range changes.
- Inject an API client service through `@Environment` or explicit initializers.
- Keep the first iOS version read-only. Add push alerts later.

Minimum viable iOS milestone:

1. Consume the existing `/api/v1/stocks/{symbol}/analysis` endpoint.
2. Render market status, recommendation, K-line strategy, and risk lights.
3. Add watchlist persistence locally on device.
4. Add position inputs after the read-only flow is stable.
