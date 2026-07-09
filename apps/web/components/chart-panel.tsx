"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent, type WheelEvent } from "react";
import type { ChartResponse } from "@/lib/types";
import {
  analyzeDailyPriceLevels,
  type DailyPriceLevel,
  type DailyPriceLevelSummary,
  type KlineCandle
} from "@/lib/kline-levels";

type Theme = "light" | "dark";
type Timeframe = "60m" | "1d" | "1w";

type Candle = KlineCandle;

type PlotTrace = Record<string, unknown> & {
  name?: string;
  type?: string;
};

type PlotlyBinaryArray = {
  dtype?: string;
  bdata?: string;
};

type KdPoint = {
  k: number | null;
  d: number | null;
};

type DragState = {
  pointerId: number;
  startEnd: number;
  startX: number;
};

const timeframeOptions: Array<{ key: Timeframe; label: string }> = [
  { key: "60m", label: "60分K" },
  { key: "1d", label: "日K" },
  { key: "1w", label: "周K" }
];

const chartWidth = 920;
const priceHeight = 360;
const volumeHeight = 74;
const kdHeight = 132;
const chartGap = 18;
const rightAxisWidth = 76;
const leftGutter = 8;
const topGutter = 28;
const totalHeight = topGutter + priceHeight + chartGap + volumeHeight + chartGap + kdHeight + 34;

export function ChartPanel({
  chart,
  latestPrice,
  symbol,
  theme
}: {
  chart: ChartResponse | null;
  latestPrice?: number | null;
  symbol?: string;
  theme: Theme;
}) {
  const [timeframe, setTimeframe] = useState<Timeframe>("1d");
  const [kdPeriod, setKdPeriod] = useState(9);
  const [kSmooth, setKSmooth] = useState(3);
  const [dSmooth, setDSmooth] = useState(3);
  const [windowSize, setWindowSize] = useState(visibleCount("1d"));
  const [windowEnd, setWindowEnd] = useState(0);
  const [isDragging, setIsDragging] = useState(false);
  const dragRef = useRef<DragState | null>(null);
  const palette = theme === "dark" ? darkPalette : lightPalette;

  const baseCandles = useMemo(() => extractCandles(chart), [chart]);

  const candles = useMemo(
    () => (baseCandles.length ? transformCandles(baseCandles, timeframe, symbol ?? chart?.symbol ?? "2330") : []),
    [baseCandles, chart?.symbol, symbol, timeframe]
  );
  const dailyLevelSummary = useMemo(() => analyzeDailyPriceLevels(baseCandles), [baseCandles]);
  const kd = useMemo(() => calculateKd(candles, kdPeriod, kSmooth, dSmooth), [candles, dSmooth, kSmooth, kdPeriod]);
  const boundedWindowSize = candles.length
    ? Math.round(clampNumber(windowSize, Math.min(minVisibleCount(timeframe), candles.length), candles.length))
    : 0;
  const boundedWindowEnd = candles.length ? Math.round(clampNumber(windowEnd || candles.length, boundedWindowSize, candles.length)) : 0;
  const visibleStart = Math.max(0, boundedWindowEnd - boundedWindowSize);
  const visibleCandles = candles.slice(visibleStart, boundedWindowEnd);
  const visibleKd = kd.slice(visibleStart, boundedWindowEnd);
  const latest = candles[candles.length - 1];
  const previous = candles[candles.length - 2];
  const change = latest && previous ? latest.close - previous.close : 0;
  const changePercent = previous?.close ? (change / previous.close) * 100 : 0;
  const latestKd = kd[kd.length - 1] ?? { k: null, d: null };

  useEffect(() => {
    const nextWindowSize = Math.min(visibleCount(timeframe), candles.length);
    setWindowSize(nextWindowSize);
    setWindowEnd(candles.length);
    dragRef.current = null;
    setIsDragging(false);
  }, [candles.length, timeframe]);

  const updateChartWindow = useCallback(
    (nextSize: number, nextEnd = windowEnd || candles.length) => {
      if (!candles.length) return;
      const minSize = Math.min(minVisibleCount(timeframe), candles.length);
      const size = Math.round(clampNumber(nextSize, minSize, candles.length));
      const end = Math.round(clampNumber(nextEnd, size, candles.length));
      setWindowSize(size);
      setWindowEnd(end);
    },
    [candles.length, timeframe, windowEnd]
  );

  const zoomChart = useCallback(
    (factor: number) => {
      updateChartWindow(Math.round(boundedWindowSize * factor), boundedWindowEnd);
    },
    [boundedWindowEnd, boundedWindowSize, updateChartWindow]
  );

  const resetChartWindow = useCallback(() => {
    updateChartWindow(visibleCount(timeframe), candles.length);
  }, [candles.length, timeframe, updateChartWindow]);

  const handleChartWheel = useCallback(
    (event: WheelEvent<SVGSVGElement>) => {
      event.preventDefault();
      zoomChart(event.deltaY < 0 ? 0.82 : 1.22);
    },
    [zoomChart]
  );

  const handlePointerDown = useCallback(
    (event: PointerEvent<SVGSVGElement>) => {
      if (event.button !== 0 || candles.length <= boundedWindowSize) return;
      event.currentTarget.setPointerCapture(event.pointerId);
      dragRef.current = { pointerId: event.pointerId, startEnd: boundedWindowEnd, startX: event.clientX };
      setIsDragging(true);
    },
    [boundedWindowEnd, boundedWindowSize, candles.length]
  );

  const handlePointerMove = useCallback(
    (event: PointerEvent<SVGSVGElement>) => {
      const drag = dragRef.current;
      if (!drag || drag.pointerId !== event.pointerId) return;
      const plotPixels = Math.max(1, event.currentTarget.getBoundingClientRect().width - rightAxisWidth);
      const pixelsPerCandle = Math.max(4, plotPixels / Math.max(1, boundedWindowSize));
      const deltaCandles = Math.round((drag.startX - event.clientX) / pixelsPerCandle);
      updateChartWindow(boundedWindowSize, drag.startEnd + deltaCandles);
    },
    [boundedWindowSize, updateChartWindow]
  );

  const endPointerDrag = useCallback((event: PointerEvent<SVGSVGElement>) => {
    const drag = dragRef.current;
    if (drag?.pointerId === event.pointerId) {
      try {
        event.currentTarget.releasePointerCapture(event.pointerId);
      } catch {
        // Pointer capture can already be released when the cursor leaves the app window.
      }
      dragRef.current = null;
      setIsDragging(false);
    }
  }, []);

  if (!latest) {
    return (
      <section className="chart-shell stockai-panel min-w-0 rounded-lg border border-[#d7e0e8] bg-white p-4 shadow-[0_6px_16px_rgba(15,33,52,0.08)]">
        <div className="flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
          <div>
            <h2 className="text-[20px] font-bold text-[#121d2b]">K線圖</h2>
            <p className="mt-1 text-sm font-medium text-[#64748b]">等待 K 線資料同步。</p>
          </div>
          <div className="text-right">
            <div className="text-sm font-bold text-[#64748b]">{symbol ?? chart?.symbol ?? "目前股票"}</div>
            <div className="text-2xl font-bold text-[#0f3365]">{formatPrice(latestPrice)}</div>
          </div>
        </div>
        <div className="stockai-card mt-4 rounded-md border border-[#d7e0e8] bg-white px-4 py-8 text-center text-sm font-bold text-[#64748b]">
          K 線、支撐線與壓力線會在日 K 資料回來後顯示。
        </div>
      </section>
    );
  }

  return (
    <section className="chart-shell stockai-panel min-w-0 rounded-lg border border-[#d7e0e8] bg-white p-4 shadow-[0_6px_16px_rgba(15,33,52,0.08)]">
      <div className="flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
        <div>
          <h2 className="text-[20px] font-bold text-[#121d2b]">K線圖</h2>
          <p className="mt-1 text-sm font-medium text-[#64748b]">
            支援 60分K、日K、周K；下方 KD 可自行調整參數。
          </p>
        </div>
        <div className="text-right">
          <div className="text-sm font-bold text-[#64748b]">{symbol ?? chart?.symbol ?? "目前股票"}</div>
          <div className={`text-2xl font-bold ${change >= 0 ? "text-[#dc2626]" : "text-[#168447]"}`}>
            {formatPrice(latest?.close)} <span className="text-base">{formatSigned(change)} {formatSignedPercent(changePercent)}</span>
          </div>
        </div>
      </div>

      <div className="mt-4 flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div className="flex flex-wrap gap-2">
          {timeframeOptions.map((item) => (
            <button
              key={item.key}
              className={`h-10 rounded-md border px-4 text-sm font-bold transition ${
                timeframe === item.key
                  ? "border-[#08283d] bg-[#08283d] text-white"
                  : "border-[#cbd7e2] bg-[#fbfdff] text-[#243346] hover:bg-[#eef3f8]"
              }`}
              type="button"
              onClick={() => setTimeframe(item.key)}
            >
              {item.label}
            </button>
          ))}
        </div>

        <div className="flex flex-wrap gap-2">
          <KdInput label="KD週期" value={kdPeriod} min={3} max={30} onChange={setKdPeriod} />
          <KdInput label="K平滑" value={kSmooth} min={1} max={12} onChange={setKSmooth} />
          <KdInput label="D平滑" value={dSmooth} min={1} max={12} onChange={setDSmooth} />
          <button
            aria-label="放大 K 線"
            className="h-10 w-10 rounded-md border border-[#cbd7e2] bg-[#fbfdff] text-lg font-black text-[#243346] hover:bg-[#eef3f8]"
            title="放大"
            type="button"
            onClick={() => zoomChart(0.78)}
          >
            +
          </button>
          <button
            aria-label="縮小 K 線"
            className="h-10 w-10 rounded-md border border-[#cbd7e2] bg-[#fbfdff] text-lg font-black text-[#243346] hover:bg-[#eef3f8]"
            title="縮小"
            type="button"
            onClick={() => zoomChart(1.28)}
          >
            -
          </button>
          <button
            className="h-10 rounded-md border border-[#cbd7e2] bg-[#fbfdff] px-3 text-sm font-bold text-[#243346] hover:bg-[#eef3f8]"
            type="button"
            onClick={resetChartWindow}
          >
            重設
          </button>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-4 text-xs font-bold text-[#64748b]">
        <span>O {formatPrice(latest?.open)}</span>
        <span>H {formatPrice(latest?.high)}</span>
        <span>L {formatPrice(latest?.low)}</span>
        <span>C {formatPrice(latest?.close)}</span>
        <span>量 {formatVolume(latest?.volume ?? 0)}</span>
        <span className="text-[#b45309]">K {formatNullable(latestKd.k)}</span>
        <span className="text-[#245b86]">D {formatNullable(latestKd.d)}</span>
        {timeframe === "60m" && <span className="rounded bg-[#fff8e8] px-2 py-1 text-[#9a6700]">分鐘線資料未接入時使用日內重建節奏</span>}
      </div>

      <DailyLevelSummaryCards summary={dailyLevelSummary} />

      <div className="stockai-card mt-3 overflow-hidden rounded-md border border-[#d7e0e8] bg-white p-2">
        <svg
          className={`h-[520px] w-full touch-none select-none md:h-[640px] ${isDragging ? "cursor-grabbing" : "cursor-grab"}`}
          viewBox={`0 0 ${chartWidth} ${totalHeight}`}
          role="img"
          aria-label={`${symbol ?? chart?.symbol ?? ""} K線圖`}
          onPointerCancel={endPointerDrag}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={endPointerDrag}
          onWheel={handleChartWheel}
        >
          <rect x="0" y="0" width={chartWidth} height={totalHeight} fill={palette.panel} />
          <KChartSvg candles={visibleCandles} kd={visibleKd} levelSummary={dailyLevelSummary} palette={palette} timeframe={timeframe} />
        </svg>
      </div>
    </section>
  );
}

function DailyLevelSummaryCards({ summary }: { summary: DailyPriceLevelSummary }) {
  const support = summary.nearestSupport;
  const resistance = summary.nearestResistance;
  const rangeWidth =
    support && resistance && support.value < resistance.value
      ? ((resistance.value - support.value) / Math.max(summary.currentClose ?? 1, 1)) * 100
      : null;

  return (
    <div className="mt-3 grid gap-2 md:grid-cols-4">
      <LevelSummaryCard
        detail={support ? `${strengthLabel(support.strength)} · ${support.touches}次觸及 · ${formatSignedPercent(support.distancePercent)}` : "等待更多日K資料"}
        label="主支撐"
        tone="support"
        value={formatPrice(support?.value)}
      />
      <LevelSummaryCard
        detail={resistance ? `${strengthLabel(resistance.strength)} · ${resistance.touches}次觸及 · ${formatSignedPercent(resistance.distancePercent)}` : "等待更多日K資料"}
        label="主壓力"
        tone="resistance"
        value={formatPrice(resistance?.value)}
      />
      <LevelSummaryCard
        detail="與20日均量比較"
        label="量能"
        tone="neutral"
        value={summary.volumeRatio === null ? "-" : `${summary.volumeRatio.toLocaleString("zh-TW", { maximumFractionDigits: 2 })}x`}
      />
      <LevelSummaryCard
        detail={rangeWidth === null ? "區間尚未明確" : `區間寬度 ${formatSignedPercent(rangeWidth).replace("+", "")}`}
        label="日K位置"
        tone={summary.rangeState === "near_resistance" || summary.rangeState === "extended" ? "resistance" : summary.rangeState === "near_support" ? "support" : "neutral"}
        value={rangeStateLabel(summary.rangeState)}
      />
    </div>
  );
}

function LevelSummaryCard({
  detail,
  label,
  tone,
  value
}: {
  detail: string;
  label: string;
  tone: "support" | "resistance" | "neutral";
  value: string;
}) {
  return (
    <div className={`stockai-card stockai-level-card stockai-level-${tone} rounded-md border px-3 py-2`}>
      <div className="text-xs font-bold">{label}</div>
      <div className="mt-1 text-lg font-bold leading-tight">{value}</div>
      <div className="mt-1 text-[11px] font-semibold leading-4">{detail}</div>
    </div>
  );
}

function KdInput({
  label,
  max,
  min,
  onChange,
  value
}: {
  label: string;
  max: number;
  min: number;
  onChange: (value: number) => void;
  value: number;
}) {
  return (
    <label className="flex h-10 items-center gap-2 rounded-md border border-[#cbd7e2] bg-[#fbfdff] px-3 text-xs font-bold text-[#243346]">
      {label}
      <input
        className="h-7 w-14 rounded border border-[#cbd7e2] bg-white px-2 text-center text-sm font-bold text-[#172233] outline-none"
        max={max}
        min={min}
        type="number"
        value={value}
        onChange={(event) => onChange(clampInteger(event.target.value, min, max))}
      />
    </label>
  );
}

function KChartSvg({
  candles,
  kd,
  levelSummary,
  palette,
  timeframe
}: {
  candles: Candle[];
  kd: KdPoint[];
  levelSummary: DailyPriceLevelSummary;
  palette: typeof lightPalette;
  timeframe: Timeframe;
}) {
  if (!candles.length) return null;
  const plotWidth = chartWidth - rightAxisWidth - leftGutter;
  const priceTop = topGutter;
  const priceBottom = priceTop + priceHeight;
  const volumeTop = priceBottom + chartGap;
  const volumeBottom = volumeTop + volumeHeight;
  const kdTop = volumeBottom + chartGap;
  const kdBottom = kdTop + kdHeight;
  const minPrice = Math.min(...candles.map((item) => item.low));
  const maxPrice = Math.max(...candles.map((item) => item.high));
  const pricePadding = Math.max((maxPrice - minPrice) * 0.08, maxPrice * 0.004);
  const yMin = minPrice - pricePadding;
  const yMax = maxPrice + pricePadding;
  const maxVolume = Math.max(...candles.map((item) => item.volume), 1);
  const candleStep = plotWidth / Math.max(1, candles.length);
  const candleWidth = Math.max(3, Math.min(16, candleStep * 0.58));
  const latest = candles[candles.length - 1];
  const latestY = yPrice(latest.close, yMin, yMax, priceTop, priceBottom);
  const highCandle = candles.reduce((best, item) => (item.high > best.high ? item : best), candles[0]);
  const lowCandle = candles.reduce((best, item) => (item.low < best.low ? item : best), candles[0]);
  const levelAnnotations =
    timeframe === "1d"
      ? buildLevelAnnotations(levelSummary, yMin, yMax, priceTop, priceBottom)
      : [];

  return (
    <>
      {priceTicks(yMin, yMax).map((tick) => {
        const y = yPrice(tick, yMin, yMax, priceTop, priceBottom);
        return (
          <g key={tick}>
            <line x1={leftGutter} x2={plotWidth} y1={y} y2={y} stroke={palette.grid} strokeDasharray="4 5" />
            <text x={plotWidth + 10} y={y + 4} fill={palette.muted} fontSize="12" fontWeight="700">
              {formatPrice(tick)}
            </text>
          </g>
        );
      })}

      {levelAnnotations.filter((annotation) => annotation.isPrimary).map(({ level, zoneBottom, zoneTop }) => (
        <rect
          key={`${level.kind}-${level.value}-zone`}
          x={leftGutter}
          y={zoneTop}
          width={plotWidth - leftGutter}
          height={Math.max(2, zoneBottom - zoneTop)}
          fill={levelFill(level.kind, palette)}
          opacity={level.strength === "strong" ? "0.08" : "0.05"}
        />
      ))}

      {candles.map((candle, index) => {
        const x = leftGutter + index * candleStep + candleStep / 2;
        const openY = yPrice(candle.open, yMin, yMax, priceTop, priceBottom);
        const closeY = yPrice(candle.close, yMin, yMax, priceTop, priceBottom);
        const highY = yPrice(candle.high, yMin, yMax, priceTop, priceBottom);
        const lowY = yPrice(candle.low, yMin, yMax, priceTop, priceBottom);
        const up = candle.close >= candle.open;
        const color = up ? palette.up : palette.down;
        const bodyY = Math.min(openY, closeY);
        const bodyHeight = Math.max(2, Math.abs(openY - closeY));
        const volumeHeightValue = (candle.volume / maxVolume) * (volumeHeight - 12);
        return (
          <g key={`${candle.time}-${index}`}>
            <line x1={x} x2={x} y1={highY} y2={lowY} stroke={color} strokeWidth="1.5" />
            <rect
              x={x - candleWidth / 2}
              y={bodyY}
              width={candleWidth}
              height={bodyHeight}
              fill={up ? color : palette.panel}
              stroke={color}
              strokeWidth="1.4"
            />
            <rect
              x={x - candleWidth / 2}
              y={volumeBottom - volumeHeightValue}
              width={candleWidth}
              height={volumeHeightValue}
              fill={color}
              opacity="0.42"
            />
          </g>
        );
      })}

      {levelAnnotations.map(({ isPrimary, labelY, level, y }) => (
        <g key={`${level.kind}-${level.value}-line`} opacity={isPrimary ? "1" : "0.45"} pointerEvents="none">
          <line
            x1={leftGutter}
            x2={isPrimary ? plotWidth - 78 : plotWidth}
            y1={y}
            y2={y}
            stroke={levelStroke(level.kind, palette)}
            strokeDasharray={level.kind === "support" ? "8 5" : "4 4"}
            strokeWidth={isPrimary ? "2" : "1.2"}
          />
          {isPrimary && (
            <>
              <rect x={plotWidth - 74} y={labelY - 10} width="68" height="20" rx="4" fill={palette.levelLabelBg} stroke={levelStroke(level.kind, palette)} opacity="0.92" />
              <text x={plotWidth - 40} y={labelY + 4} textAnchor="middle" fill={levelStroke(level.kind, palette)} fontSize="11" fontWeight="900">
                {levelShortLabel(level)}
              </text>
            </>
          )}
        </g>
      ))}

      <line x1={leftGutter} x2={plotWidth} y1={latestY} y2={latestY} stroke={palette.last} strokeDasharray="5 5" />
      <rect x={plotWidth + 5} y={latestY - 13} width="66" height="26" rx="4" fill={palette.last} />
      <text x={plotWidth + 38} y={latestY + 5} textAnchor="middle" fill="#fff" fontSize="12" fontWeight="800">
        {formatPrice(latest.close)}
      </text>

      <PriceMarker candle={highCandle} candles={candles} label="高" plotWidth={plotWidth} yMin={yMin} yMax={yMax} yTop={priceTop} yBottom={priceBottom} palette={palette} />
      <PriceMarker candle={lowCandle} candles={candles} label="低" plotWidth={plotWidth} yMin={yMin} yMax={yMax} yTop={priceTop} yBottom={priceBottom} palette={palette} />

      <line x1={leftGutter} x2={plotWidth} y1={volumeTop} y2={volumeTop} stroke={palette.axis} />
      <text x={leftGutter} y={volumeTop - 6} fill={palette.muted} fontSize="12" fontWeight="800">成交量</text>
      <text x={plotWidth + 10} y={volumeBottom - 4} fill={palette.muted} fontSize="12" fontWeight="700">{formatVolume(maxVolume)}</text>

      <line x1={leftGutter} x2={plotWidth} y1={kdTop} y2={kdTop} stroke={palette.axis} />
      {[20, 50, 80].map((tick) => {
        const y = yKd(tick, kdTop, kdBottom);
        return (
          <g key={tick}>
            <line x1={leftGutter} x2={plotWidth} y1={y} y2={y} stroke={palette.grid} strokeDasharray="4 5" />
            <text x={plotWidth + 14} y={y + 4} fill={palette.muted} fontSize="12" fontWeight="700">
              {tick}
            </text>
          </g>
        );
      })}
      <text x={leftGutter} y={kdTop - 6} fill={palette.muted} fontSize="12" fontWeight="800">KD</text>
      <polyline points={kdPath(kd, "k", leftGutter, plotWidth, kdTop, kdBottom)} fill="none" stroke={palette.k} strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.2" />
      <polyline points={kdPath(kd, "d", leftGutter, plotWidth, kdTop, kdBottom)} fill="none" stroke={palette.d} strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.2" />

      {xLabels(candles, timeframe).map((item) => (
        <text key={`${item.index}-${item.label}`} x={leftGutter + item.index * candleStep + candleStep / 2} y={totalHeight - 10} textAnchor="middle" fill={palette.muted} fontSize="12" fontWeight="700">
          {item.label}
        </text>
      ))}
    </>
  );
}

type LevelAnnotation = {
  isPrimary: boolean;
  labelY: number;
  level: DailyPriceLevel;
  y: number;
  zoneBottom: number;
  zoneTop: number;
};

function buildLevelAnnotations(
  summary: DailyPriceLevelSummary,
  yMin: number,
  yMax: number,
  priceTop: number,
  priceBottom: number
): LevelAnnotation[] {
  const primaryKeys = new Set(
    [summary.nearestSupport, summary.nearestResistance]
      .filter((level): level is DailyPriceLevel => level !== null)
      .map((level) => levelKey(level))
  );
  const raw = summary.levels
    .filter((level) => level.zoneHigh >= yMin && level.zoneLow <= yMax)
    .map((level) => {
      const y = yPrice(level.value, yMin, yMax, priceTop, priceBottom);
      const zoneTop = Math.max(priceTop, yPrice(level.zoneHigh, yMin, yMax, priceTop, priceBottom));
      const zoneBottom = Math.min(priceBottom, yPrice(level.zoneLow, yMin, yMax, priceTop, priceBottom));
      return { level, y, zoneTop, zoneBottom, labelY: y, isPrimary: primaryKeys.has(levelKey(level)) };
    })
    .sort((a, b) => a.y - b.y);

  let previous = priceTop + 10;
  const minGap = 25;
  const labeled = raw.filter((item) => item.isPrimary);
  for (const item of labeled) {
    item.labelY = clampNumber(Math.max(item.y, previous + minGap), priceTop + 14, priceBottom - 14);
    previous = item.labelY;
  }

  for (let index = labeled.length - 2; index >= 0; index -= 1) {
    if (labeled[index + 1].labelY - labeled[index].labelY < minGap) {
      labeled[index].labelY = Math.max(priceTop + 14, labeled[index + 1].labelY - minGap);
    }
  }

  return raw;
}

function PriceMarker({
  candle,
  candles,
  label,
  palette,
  plotWidth,
  yBottom,
  yMax,
  yMin,
  yTop
}: {
  candle: Candle;
  candles: Candle[];
  label: string;
  palette: typeof lightPalette;
  plotWidth: number;
  yBottom: number;
  yMax: number;
  yMin: number;
  yTop: number;
}) {
  const index = candles.indexOf(candle);
  const step = plotWidth / Math.max(1, candles.length);
  const x = leftGutter + index * step + step / 2;
  const value = label === "高" ? candle.high : candle.low;
  const y = yPrice(value, yMin, yMax, yTop, yBottom);
  const alignRight = x > plotWidth * 0.72;
  const lineEnd = alignRight ? x - 44 : x + 44;
  const textX = alignRight ? lineEnd - 4 : lineEnd + 4;
  return (
    <g>
      <circle cx={x} cy={y} r="3" fill={palette.marker} />
      <line x1={x} x2={lineEnd} y1={y} y2={y} stroke={palette.marker} />
      <text x={textX} y={y - 5} textAnchor={alignRight ? "end" : "start"} fill={palette.marker} fontSize="12" fontWeight="800">
        {label} {formatPrice(value)}
      </text>
    </g>
  );
}

function extractCandles(chart: ChartResponse | null): Candle[] {
  const traces = Array.isArray(chart?.figure.data) ? (chart.figure.data as PlotTrace[]) : [];
  const candleTrace = traces.find((trace) => trace.type === "candlestick" || (Array.isArray(toArray(trace.open)) && Array.isArray(toArray(trace.close))));
  if (!candleTrace) return [];

  const xs = toArray(candleTrace.x);
  const opens = toNumericArray(candleTrace.open);
  const highs = toNumericArray(candleTrace.high);
  const lows = toNumericArray(candleTrace.low);
  const closes = toNumericArray(candleTrace.close);
  const volumeMap = extractVolumeMap(traces);
  const length = Math.min(xs.length, opens.length, highs.length, lows.length, closes.length);

  return Array.from({ length }, (_, index) => {
    const time = String(xs[index] ?? index);
    return {
      time,
      open: opens[index],
      high: highs[index],
      low: lows[index],
      close: closes[index],
      volume: volumeMap.get(time) ?? 0
    };
  }).filter((item) => [item.open, item.high, item.low, item.close].every(Number.isFinite));
}

function extractVolumeMap(traces: PlotTrace[]) {
  const volumeTrace = traces.find((trace) => {
    const name = String(trace.name ?? "").toUpperCase();
    return trace.type === "bar" || name.includes("VOLUME") || name.includes("成交量");
  });
  const map = new Map<string, number>();
  if (!volumeTrace) return map;
  const xs = toArray(volumeTrace.x);
  const ys = toNumericArray(volumeTrace.y);
  for (let index = 0; index < Math.min(xs.length, ys.length); index += 1) {
    map.set(String(xs[index]), ys[index]);
  }
  return map;
}

function transformCandles(candles: Candle[], timeframe: Timeframe, symbol: string) {
  if (timeframe === "1w") return aggregateWeekly(candles);
  if (timeframe === "60m") return buildSixtyMinuteCandles(candles, symbol);
  return candles;
}

function aggregateWeekly(candles: Candle[]) {
  const groups = new Map<string, Candle[]>();
  for (const candle of candles) {
    const key = weekKey(candle.time);
    const items = groups.get(key) ?? [];
    items.push(candle);
    groups.set(key, items);
  }
  return Array.from(groups.entries()).map(([key, items]) => ({
    time: key,
    open: items[0].open,
    high: Math.max(...items.map((item) => item.high)),
    low: Math.min(...items.map((item) => item.low)),
    close: items[items.length - 1].close,
    volume: items.reduce((sum, item) => sum + item.volume, 0)
  }));
}

function buildSixtyMinuteCandles(candles: Candle[], symbol: string) {
  const latest = candles[candles.length - 1] ?? makeFallbackCandles(symbol, 100).at(-1)!;
  const previous = candles[candles.length - 2] ?? latest;
  const seed = symbol.split("").reduce((sum, char) => sum + char.charCodeAt(0), 0);
  const bars: Candle[] = [];
  let price = previous.close;
  const barCount = 42;
  for (let index = 0; index < barCount; index += 1) {
    const dayIndex = Math.floor(index / 6);
    const slot = index % 6;
    const drift = ((latest.close - previous.close) / Math.max(previous.close, 1)) / barCount;
    const wave = Math.sin((index + seed) / 4) * 0.0035;
    const open = price;
    const close = open * (1 + drift + wave);
    const range = Math.max(latest.close * 0.003, Math.abs(close - open) * 1.8);
    const high = Math.max(open, close) + range * (0.4 + ((seed + index) % 5) / 10);
    const low = Math.min(open, close) - range * (0.4 + ((seed + index * 3) % 5) / 10);
    price = close;
    bars.push({
      time: `${dayIndex + 1}D ${9 + slot}:00`,
      open: round2(open),
      high: round2(high),
      low: round2(low),
      close: round2(close),
      volume: Math.max(1, latest.volume / 6) * (0.7 + ((seed + index) % 9) / 10)
    });
  }
  const last = bars[bars.length - 1];
  bars[bars.length - 1] = { ...last, close: latest.close, high: Math.max(last.high, latest.close), low: Math.min(last.low, latest.close) };
  return bars;
}

function calculateKd(candles: Candle[], period: number, kSmooth: number, dSmooth: number): KdPoint[] {
  let previousK = 50;
  let previousD = 50;
  return candles.map((candle, index) => {
    const window = candles.slice(Math.max(0, index - period + 1), index + 1);
    if (window.length < Math.min(period, 3)) return { k: null, d: null };
    const highest = Math.max(...window.map((item) => item.high));
    const lowest = Math.min(...window.map((item) => item.low));
    const rsv = highest === lowest ? 50 : ((candle.close - lowest) / (highest - lowest)) * 100;
    previousK = ((kSmooth - 1) * previousK + rsv) / kSmooth;
    previousD = ((dSmooth - 1) * previousD + previousK) / dSmooth;
    return { k: round2(previousK), d: round2(previousD) };
  });
}

function makeFallbackCandles(symbol: string, latestPrice: number) {
  const seed = symbol.split("").reduce((sum, char) => sum + char.charCodeAt(0), 0);
  const candles: Candle[] = [];
  let close = latestPrice * 0.84;
  for (let index = 0; index < 140; index += 1) {
    const wave = Math.sin((index + seed) / 8) * 0.012;
    const drift = 0.0018;
    const open = close;
    close = open * (1 + wave + drift);
    const high = Math.max(open, close) * (1 + 0.008 + ((seed + index) % 6) / 1000);
    const low = Math.min(open, close) * (1 - 0.008 - ((seed + index * 2) % 6) / 1000);
    candles.push({
      time: `D${index + 1}`,
      open: round2(open),
      high: round2(high),
      low: round2(low),
      close: round2(close),
      volume: 5_000_000 + ((seed + index * 137) % 4_000_000)
    });
  }
  return candles;
}

function toArray(value: unknown): unknown[] {
  if (isPlotlyBinaryArray(value)) return decodePlotlyBinaryArray(value);
  return Array.isArray(value) ? value : [];
}

function toNumericArray(value: unknown) {
  return toArray(value).map((item) => Number(item)).filter(Number.isFinite);
}

function isPlotlyBinaryArray(value: unknown): value is PlotlyBinaryArray {
  return Boolean(
    value &&
      typeof value === "object" &&
      "bdata" in value &&
      typeof (value as PlotlyBinaryArray).bdata === "string"
  );
}

function decodePlotlyBinaryArray(value: PlotlyBinaryArray) {
  if (!value.bdata) return [];
  const binary = atob(value.bdata);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  const buffer = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);

  switch (value.dtype) {
    case "f8":
      return finiteNumericArray(new Float64Array(buffer));
    case "f4":
      return finiteNumericArray(new Float32Array(buffer));
    case "i4":
      return finiteNumericArray(new Int32Array(buffer));
    case "u4":
      return finiteNumericArray(new Uint32Array(buffer));
    case "i2":
      return finiteNumericArray(new Int16Array(buffer));
    case "u2":
      return finiteNumericArray(new Uint16Array(buffer));
    case "i1":
      return finiteNumericArray(new Int8Array(buffer));
    case "u1":
      return finiteNumericArray(new Uint8Array(buffer));
    default:
      return finiteNumericArray(new Float64Array(buffer));
  }
}

function finiteNumericArray(values: ArrayLike<number>) {
  return Array.from(values, (item) => (Number.isFinite(item) ? item : null));
}

function priceTicks(min: number, max: number) {
  return Array.from({ length: 5 }, (_, index) => min + ((max - min) * index) / 4).reverse();
}

function yPrice(value: number, min: number, max: number, top: number, bottom: number) {
  return bottom - ((value - min) / Math.max(1e-9, max - min)) * (bottom - top);
}

function yKd(value: number, top: number, bottom: number) {
  return bottom - (value / 100) * (bottom - top);
}

function kdPath(points: KdPoint[], key: "k" | "d", xStart: number, xEnd: number, top: number, bottom: number) {
  const step = (xEnd - xStart) / Math.max(1, points.length - 1);
  return points
    .map((point, index) => {
      const value = point[key];
      if (value === null) return null;
      return `${(xStart + index * step).toFixed(1)},${yKd(value, top, bottom).toFixed(1)}`;
    })
    .filter(Boolean)
    .join(" ");
}

function xLabels(candles: Candle[], timeframe: Timeframe) {
  if (!candles.length) return [];
  const count = candles.length;
  const indexes = Array.from(new Set([0, Math.floor(count * 0.33), Math.floor(count * 0.66), count - 1]));
  return indexes.map((index) => ({ index, label: formatTimeLabel(candles[index].time, timeframe) }));
}

function formatTimeLabel(value: string, timeframe: Timeframe) {
  if (timeframe === "60m") return value;
  const date = new Date(value);
  if (!Number.isNaN(date.getTime())) {
    return `${date.getMonth() + 1}/${date.getDate()}`;
  }
  return value.replace(/^D/, "");
}

function visibleCount(timeframe: Timeframe) {
  if (timeframe === "60m") return 42;
  if (timeframe === "1w") return 72;
  return 96;
}

function minVisibleCount(timeframe: Timeframe) {
  if (timeframe === "60m") return 18;
  if (timeframe === "1w") return 24;
  return 28;
}

function weekKey(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const start = new Date(date.getFullYear(), 0, 1);
  const diff = Math.floor((date.getTime() - start.getTime()) / 86_400_000);
  const week = Math.floor((diff + start.getDay()) / 7) + 1;
  return `${date.getFullYear()} W${String(week).padStart(2, "0")}`;
}

function clampInteger(value: string, min: number, max: number) {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed)) return min;
  return Math.max(min, Math.min(max, parsed));
}

function formatPrice(value: number | null | undefined) {
  if (value === null || value === undefined || !Number.isFinite(value)) return "-";
  return value.toLocaleString("zh-TW", { maximumFractionDigits: 2, minimumFractionDigits: 2 });
}

function formatSigned(value: number) {
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${formatPrice(value)}`;
}

function formatSignedPercent(value: number) {
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${value.toLocaleString("zh-TW", { maximumFractionDigits: 2, minimumFractionDigits: 2 })}%`;
}

function formatNullable(value: number | null | undefined) {
  if (value === null || value === undefined) return "-";
  return value.toLocaleString("zh-TW", { maximumFractionDigits: 1, minimumFractionDigits: 1 });
}

function formatVolume(value: number) {
  if (value >= 100_000_000) return `${(value / 100_000_000).toLocaleString("zh-TW", { maximumFractionDigits: 2 })}億`;
  if (value >= 10_000) return `${(value / 10_000).toLocaleString("zh-TW", { maximumFractionDigits: 1 })}萬`;
  return value.toLocaleString("zh-TW", { maximumFractionDigits: 0 });
}

function round2(value: number) {
  return Math.round(value * 100) / 100;
}

function clampNumber(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

function strengthLabel(strength: DailyPriceLevel["strength"]) {
  if (strength === "strong") return "強";
  if (strength === "medium") return "中";
  return "弱";
}

function rangeStateLabel(state: DailyPriceLevelSummary["rangeState"]) {
  if (state === "near_support") return "接近支撐";
  if (state === "near_resistance") return "接近壓力";
  if (state === "extended") return "偏離區間";
  return "區間中段";
}

function levelKey(level: DailyPriceLevel) {
  return `${level.kind}:${level.value}`;
}

function levelShortLabel(level: DailyPriceLevel) {
  return `${level.kind === "support" ? "撐" : "壓"} ${formatCompactLevelPrice(level.value)}`;
}

function formatCompactLevelPrice(value: number) {
  if (value >= 100) return value.toLocaleString("zh-TW", { maximumFractionDigits: 0 });
  return value.toLocaleString("zh-TW", { maximumFractionDigits: 1 });
}

function levelStroke(kind: DailyPriceLevel["kind"], palette: typeof lightPalette) {
  return kind === "support" ? palette.support : palette.resistance;
}

function levelFill(kind: DailyPriceLevel["kind"], palette: typeof lightPalette) {
  return kind === "support" ? palette.supportFill : palette.resistanceFill;
}

const lightPalette = {
  axis: "#cbd7e2",
  d: "#245b86",
  down: "#168447",
  grid: "#dbe3eb",
  k: "#b45309",
  last: "#08283d",
  marker: "#475569",
  muted: "#64748b",
  panel: "#ffffff",
  levelLabelBg: "#ffffff",
  resistance: "#c2410c",
  resistanceFill: "#fb923c",
  support: "#047857",
  supportFill: "#34d399",
  up: "#dc2626"
};

const darkPalette = {
  axis: "#334155",
  d: "#93c5fd",
  down: "#4ade80",
  grid: "#28384a",
  k: "#facc15",
  last: "#1f5d8d",
  marker: "#cbd5e1",
  muted: "#94a3b8",
  panel: "#111a25",
  levelLabelBg: "#0f1722",
  resistance: "#fb923c",
  resistanceFill: "#fb923c",
  support: "#6ee7b7",
  supportFill: "#22c55e",
  up: "#f87171"
};
