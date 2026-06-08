import { formatNumber } from "@/lib/format";
import type { AnalysisResponse } from "@/lib/types";

export function MetricGrid({ analysis }: { analysis: AnalysisResponse }) {
  const technical = analysis.technical;
  const stop = analysis.stop_loss;
  const trailing = analysis.trailing_take_profit;

  const items = [
    ["收盤價", formatNumber(technical.latest_close)],
    ["MA20", formatNumber(technical.ma.ma20)],
    ["RSI14", formatNumber(technical.rsi.rsi14)],
    ["ATR14", formatNumber(technical.atr14)],
    ["停利價", formatNumber(trailing.current_take_profit_price)],
    ["ATR停損", formatNumber(stop.atr_stop)],
    ["5日法人", formatNumber(analysis.institutional.five_day_total, 0)],
    ["20日法人", formatNumber(analysis.institutional.twenty_day_total, 0)]
  ];

  return (
    <section className="grid grid-cols-2 gap-2 md:grid-cols-4">
      {items.map(([label, value]) => (
        <div key={label} className="rounded-md border border-line bg-panel p-3">
          <div className="text-xs text-ink/60">{label}</div>
          <div className="mt-1 text-lg font-semibold">{value}</div>
        </div>
      ))}
    </section>
  );
}

