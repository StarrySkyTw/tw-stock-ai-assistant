"use client";

import dynamic from "next/dynamic";
import { useMemo, useState } from "react";
import type * as Plotly from "plotly.js";
import type { ChartResponse } from "@/lib/types";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

type Theme = "light" | "dark";
type TraceGroup = "ma5" | "ma20" | "ma60" | "volume" | "macd" | "rsi";

const controls: Array<{ key: TraceGroup; label: string }> = [
  { key: "ma5", label: "MA5" },
  { key: "ma20", label: "MA20" },
  { key: "ma60", label: "MA60" },
  { key: "volume", label: "成交量" },
  { key: "macd", label: "MACD" },
  { key: "rsi", label: "RSI" }
];

const defaultVisible: Record<TraceGroup, boolean> = {
  ma5: false,
  ma20: true,
  ma60: true,
  volume: true,
  macd: false,
  rsi: false
};

export function ChartPanel({ chart, theme }: { chart: ChartResponse | null; theme: Theme }) {
  const [visible, setVisible] = useState(defaultVisible);
  const palette = theme === "dark" ? darkPalette : lightPalette;

  const data = useMemo<Plotly.Data[]>(() => {
    return (((chart?.figure.data as Plotly.Data[]) || []).filter((trace) =>
      shouldShowTrace(trace, visible)
    )) as Plotly.Data[];
  }, [chart, visible]);

  if (!chart) {
    return (
      <section className="rounded-md border border-line bg-panel p-4">
        <div className="text-sm text-muted">尚未載入圖表。</div>
      </section>
    );
  }

  return (
    <section className="chart-shell rounded-md border border-line bg-panel p-3">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-base font-semibold">互動圖表</h2>
          <p className="text-xs text-muted">K 線固定顯示；其他指標可自行開關，下方時間軸可以拖拉。</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {controls.map((item) => {
            const active = visible[item.key];
            return (
              <button
                key={item.key}
                className={`focus-ring rounded-md border px-3 py-2 text-sm font-medium transition ${
                  active
                    ? "border-ink bg-ink text-panel"
                    : "border-line bg-control text-ink hover:border-ink"
                }`}
                type="button"
                onClick={() => setVisible((current) => ({ ...current, [item.key]: !current[item.key] }))}
              >
                {active ? "✓ " : ""}{item.label}
              </button>
            );
          })}
        </div>
      </div>

      <Plot
        data={data}
        layout={{
          ...(chart.figure.layout as Partial<Plotly.Layout>),
          autosize: true,
          paper_bgcolor: palette.panel,
          plot_bgcolor: palette.panel,
          font: { color: palette.ink },
          hoverlabel: {
            bgcolor: palette.control,
            bordercolor: palette.line,
            font: { color: palette.ink }
          },
          legend: {
            bgcolor: palette.panel,
            bordercolor: palette.line,
            borderwidth: 1,
            font: { color: palette.ink }
          },
          xaxis: { ...(chart.figure.layout as Plotly.Layout).xaxis, gridcolor: palette.line },
          xaxis2: { ...(chart.figure.layout as Plotly.Layout).xaxis2, gridcolor: palette.line },
          xaxis3: { ...(chart.figure.layout as Plotly.Layout).xaxis3, gridcolor: palette.line },
          xaxis4: { ...(chart.figure.layout as Plotly.Layout).xaxis4, gridcolor: palette.line },
          yaxis: { ...(chart.figure.layout as Plotly.Layout).yaxis, gridcolor: palette.line },
          yaxis2: { ...(chart.figure.layout as Plotly.Layout).yaxis2, gridcolor: palette.line },
          yaxis3: { ...(chart.figure.layout as Plotly.Layout).yaxis3, gridcolor: palette.line },
          yaxis4: { ...(chart.figure.layout as Plotly.Layout).yaxis4, gridcolor: palette.line }
        }}
        config={{
          responsive: true,
          displaylogo: false,
          modeBarButtonsToRemove: ["select2d", "lasso2d", "autoScale2d"]
        }}
        className="h-[980px] w-full"
        useResizeHandler
      />
    </section>
  );
}

function shouldShowTrace(trace: Plotly.Data, visible: Record<TraceGroup, boolean>) {
  const name = String(trace.name || "").toUpperCase();
  if (trace.type === "candlestick" || name.includes("K")) return true;
  if (name === "MA5") return visible.ma5;
  if (name === "MA20") return visible.ma20;
  if (name === "MA60") return visible.ma60;
  if (name.includes("成交") || name === "VOLUME") return visible.volume;
  if (["DIF", "MACD", "OSC"].includes(name)) return visible.macd;
  if (name.includes("RSI")) return visible.rsi;
  return true;
}

const lightPalette = {
  ink: "#171717",
  line: "#d6d6d6",
  panel: "#ffffff",
  control: "#f4f4f5"
};

const darkPalette = {
  ink: "#f5f5f5",
  line: "#373737",
  panel: "#171717",
  control: "#262626"
};
