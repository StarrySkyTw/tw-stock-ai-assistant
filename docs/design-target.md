# Design Target

This app should move toward the generated research-dashboard concept in
`docs/design-assets/research-dashboard-target.png`.

## Why This Image Exists

The image was generated during the redesign implementation as a UI concept, not as a screenshot of the current app and not as an image copied from the internet.

It appeared because the frontend redesign workflow asked for a complete dashboard concept before coding. The prompt described the product goal: a conservative Taiwan-stock research assistant focused on fundamental quality, valuation, K-line timing, no-chase discipline, a watchlist workspace, and a decision journal.

## Target Direction

- Keep the first screen decision-first: show the research conclusion before market status or generic scores.
- Use three main gates: fundamental quality, valuation, and K-line timing.
- Make "do not chase" visible as a discipline rule, not hidden in detailed notes.
- Treat the watchlist as a research workspace with quality, valuation, timing, no-chase, next review, and notes.
- Include a decision journal for thesis, valuation reason, invalidation condition, expected horizon, and review trigger.
- Avoid order-entry UI, auto-trading language, or a layout that feels like a trading terminal.

## Current Gap

The current app already has the research decision API, gate panels, research candidates, a research workbench, and a local decision journal. The visual target still needs a more polished layout closer to the concept:

- Stronger app shell and navigation structure.
- Clearer top-level "research conclusion" band.
- More compact and table-like watchlist workspace.
- Better visual hierarchy for the three gates.
- More integrated decision journal layout.

## Implementation Rule

Future UI changes should move the app closer to this target image unless the user explicitly changes direction.
