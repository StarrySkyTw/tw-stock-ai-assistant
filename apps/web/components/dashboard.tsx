"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { fetchAnalysis, fetchChart, generatePdf } from "@/lib/api";
import { formatNumber, scoreClass } from "@/lib/format";
import type { AnalysisResponse, ChartResponse } from "@/lib/types";
import { ChartPanel } from "./chart-panel";
import { MetricGrid } from "./metric-grid";
import { RiskLightBadges } from "./risk-lights";

type Theme = "light" | "dark";
type TabKey = "decision" | "overview" | "position" | "watchlist" | "chart" | "signals" | "ai";

type PositionSnapshot = {
  entryPrice: number | null;
  highestPrice: number | null;
};

const tabs: Array<{ key: TabKey; label: string }> = [
  { key: "decision", label: "決策" },
  { key: "overview", label: "總覽" },
  { key: "position", label: "持倉" },
  { key: "watchlist", label: "自選比較" },
  { key: "chart", label: "圖表" },
  { key: "signals", label: "訊號" },
  { key: "ai", label: "AI" }
];

const WATCHLIST_STORAGE_KEY = "stockai-watchlist-symbols";

export function Dashboard() {
  const [symbol, setSymbol] = useState("2330");
  const [range, setRange] = useState("1y");
  const [entryPrice, setEntryPrice] = useState("");
  const [highestPrice, setHighestPrice] = useState("");
  const [watchlistInput, setWatchlistInput] = useState("2330, 2454, 2317, 0050");
  const [watchlistResults, setWatchlistResults] = useState<AnalysisResponse[]>([]);
  const [watchlistLoading, setWatchlistLoading] = useState(false);
  const [watchlistError, setWatchlistError] = useState<string | null>(null);
  const [loadedPosition, setLoadedPosition] = useState<PositionSnapshot>({ entryPrice: null, highestPrice: null });
  const [activeTab, setActiveTab] = useState<TabKey>("decision");
  const [theme, setTheme] = useState<Theme>("light");
  const [themeReady, setThemeReady] = useState(false);
  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null);
  const [chart, setChart] = useState<ChartResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [chartError, setChartError] = useState<string | null>(null);
  const [pdfPath, setPdfPath] = useState<string | null>(null);

  useEffect(() => {
    const saved = localStorage.getItem("stockai-theme");
    const savedWatchlist = localStorage.getItem(WATCHLIST_STORAGE_KEY);
    const preferred = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    const nextTheme = saved === "dark" || saved === "light" ? saved : preferred;
    setTheme(nextTheme);
    if (savedWatchlist) setWatchlistInput(savedWatchlist);
    document.documentElement.dataset.theme = nextTheme;
    setThemeReady(true);
  }, []);

  useEffect(() => {
    if (!themeReady) return;
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("stockai-theme", theme);
  }, [theme, themeReady]);

  useEffect(() => {
    if (!themeReady) return;
    localStorage.setItem(WATCHLIST_STORAGE_KEY, watchlistInput);
  }, [watchlistInput, themeReady]);

  async function load(nextSymbol = symbol, nextRange = range) {
    const parsedEntry = parsePositiveNumber(entryPrice);
    const parsedHighest = parsePositiveNumber(highestPrice);

    if (entryPrice.trim() && parsedEntry === null) {
      setError("買進價請輸入大於 0 的數字，例如 650。");
      return;
    }
    if (highestPrice.trim() && parsedHighest === null) {
      setError("持倉最高價請輸入大於 0 的數字，或留空。");
      return;
    }

    setLoading(true);
    setError(null);
    setChartError(null);
    setPdfPath(null);

    try {
      const analysisData = await fetchAnalysis(nextSymbol, {
        entryPrice: parsedEntry ?? undefined,
        highestPrice: parsedHighest ?? undefined,
        atrMultiplier: 2
      });
      setAnalysis(analysisData);
      setLoadedPosition({ entryPrice: parsedEntry, highestPrice: parsedHighest });
      setActiveTab(parsedEntry ? "position" : "decision");
    } catch (err) {
      setAnalysis(null);
      setChart(null);
      setError(err instanceof Error ? err.message : "分析資料載入失敗");
      setLoading(false);
      return;
    }

    try {
      const chartData = await fetchChart(nextSymbol, nextRange);
      setChart(chartData);
    } catch (err) {
      setChart(null);
      setChartError(err instanceof Error ? err.message : "圖表載入失敗");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load("2330", "1y");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function submit(event: FormEvent) {
    event.preventDefault();
    void load(symbol, range);
  }

  async function createPdf() {
    if (!analysis) return;
    setPdfPath(null);
    setError(null);
    try {
      const result = await generatePdf(analysis.symbol);
      setPdfPath(result.file_path);
    } catch (err) {
      setError(err instanceof Error ? err.message : "PDF 產生失敗");
    }
  }

  async function compareWatchlist() {
    const symbols = parseWatchlistSymbols(watchlistInput);
    if (!symbols.length) {
      setWatchlistError("請先輸入至少一個股票代號，例如 2330, 2454, 2317。");
      setActiveTab("watchlist");
      return;
    }

    setWatchlistLoading(true);
    setWatchlistError(null);
    setActiveTab("watchlist");
    try {
      const settled = await Promise.allSettled(symbols.map((item) => fetchAnalysis(item)));
      const fulfilled = settled
        .filter((result): result is PromiseFulfilledResult<AnalysisResponse> => result.status === "fulfilled")
        .map((result) => result.value)
        .sort((a, b) => b.adjusted_score - a.adjusted_score);
      const failed = settled.length - fulfilled.length;
      setWatchlistResults(fulfilled);
      setWatchlistError(failed ? `${failed} 檔載入失敗，其餘標的已完成比較。` : null);
    } catch (err) {
      setWatchlistResults([]);
      setWatchlistError(err instanceof Error ? err.message : "自選比較載入失敗");
    } finally {
      setWatchlistLoading(false);
    }
  }

  function selectWatchlistSymbol(nextSymbol: string) {
    setSymbol(nextSymbol);
    void load(nextSymbol, range);
  }

  return (
    <main className="min-h-screen bg-paper px-4 py-5 text-ink md:px-8">
      <div className="mx-auto flex max-w-7xl flex-col gap-4">
        <section className="rounded-md border border-line bg-panel p-4">
          <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div>
              <h1 className="text-xl font-semibold">台股 AI 投資決策助手</h1>
              <p className="text-sm text-muted">輸入股票代號與買進價，查看評分、持倉停利停損、風險與圖表。</p>
            </div>
            <ThemeToggle theme={theme} onChange={setTheme} />
          </div>

          <form className="grid gap-3 md:grid-cols-12 md:items-end" onSubmit={submit}>
            <label className="flex flex-col gap-1 text-sm font-medium md:col-span-3">
              股票代號
              <input
                className="focus-ring h-11 rounded-md border border-line bg-panel px-3 text-base text-ink"
                value={symbol}
                onChange={(event) => setSymbol(event.target.value.toUpperCase())}
                placeholder="2330"
              />
            </label>
            <label className="flex flex-col gap-1 text-sm font-medium md:col-span-2">
              區間
              <select
                className="focus-ring h-11 rounded-md border border-line bg-panel px-3 text-ink"
                value={range}
                onChange={(event) => setRange(event.target.value)}
              >
                <option value="1y">1年</option>
                <option value="3y">3年</option>
                <option value="5y">5年</option>
              </select>
            </label>
            <label className="flex flex-col gap-1 text-sm font-medium md:col-span-2">
              我的買進價
              <input
                className="focus-ring h-11 rounded-md border border-line bg-panel px-3 text-base text-ink"
                inputMode="decimal"
                value={entryPrice}
                onChange={(event) => setEntryPrice(event.target.value)}
                placeholder="例如 650"
              />
            </label>
            <label className="flex flex-col gap-1 text-sm font-medium md:col-span-2">
              持倉最高價
              <input
                className="focus-ring h-11 rounded-md border border-line bg-panel px-3 text-base text-ink"
                inputMode="decimal"
                value={highestPrice}
                onChange={(event) => setHighestPrice(event.target.value)}
                placeholder="可留空"
              />
            </label>
            <div className="flex gap-2 md:col-span-3">
              <button
                className="focus-ring h-11 flex-1 rounded-md bg-ink px-5 font-semibold text-panel disabled:opacity-60"
                type="submit"
                disabled={loading}
              >
                {loading ? "分析中" : "開始分析"}
              </button>
              <button
                className="focus-ring h-11 rounded-md border border-line bg-control px-5 font-semibold text-ink disabled:opacity-50"
                type="button"
                onClick={createPdf}
                disabled={!analysis}
              >
                產生PDF
              </button>
            </div>
          </form>
          <div className="mt-3 grid gap-2 border-t border-line pt-3 md:grid-cols-[1fr_auto] md:items-end">
            <label className="flex flex-col gap-1 text-sm font-medium">
              自選比較
              <input
                className="focus-ring h-11 rounded-md border border-line bg-panel px-3 text-base text-ink"
                value={watchlistInput}
                onChange={(event) => setWatchlistInput(event.target.value)}
                placeholder="2330, 2454, 2317, 0050"
              />
            </label>
            <button
              className="focus-ring h-11 rounded-md border border-line bg-control px-5 font-semibold text-ink disabled:opacity-50"
              type="button"
              onClick={compareWatchlist}
              disabled={watchlistLoading}
            >
              {watchlistLoading ? "比較中" : "比較自選"}
            </button>
          </div>
          {error && <div className="mt-3 rounded-md bg-loss/10 p-3 text-sm text-loss">{error}</div>}
          {pdfPath && <div className="mt-3 rounded-md bg-gain/10 p-3 text-sm text-gain">PDF 已產生：{pdfPath}</div>}
        </section>

        {analysis && (
          <>
            <nav className="flex gap-2 overflow-x-auto rounded-md border border-line bg-panel p-2">
              {tabs.map((tab) => (
                <button
                  key={tab.key}
                  className={`focus-ring rounded-md px-4 py-2 text-sm font-semibold transition ${
                    activeTab === tab.key ? "bg-ink text-panel" : "bg-control text-ink hover:border-ink"
                  }`}
                  type="button"
                  onClick={() => setActiveTab(tab.key)}
                >
                  {tab.label}
                </button>
              ))}
            </nav>

            {activeTab === "decision" && <DecisionTab analysis={analysis} />}
            {activeTab === "overview" && <OverviewTab analysis={analysis} />}
            {activeTab === "position" && <PositionTab analysis={analysis} position={loadedPosition} />}
            {activeTab === "watchlist" && (
              <WatchlistTab
                input={watchlistInput}
                loading={watchlistLoading}
                error={watchlistError}
                results={watchlistResults}
                onInputChange={setWatchlistInput}
                onCompare={compareWatchlist}
                onSelect={selectWatchlistSymbol}
              />
            )}
            {activeTab === "chart" && (
              <>
                {chartError && <div className="rounded-md bg-loss/10 p-3 text-sm text-loss">{chartError}</div>}
                <ChartPanel chart={chart} theme={theme} />
              </>
            )}
            {activeTab === "signals" && <SignalsTab analysis={analysis} />}
            {activeTab === "ai" && <AiTab analysis={analysis} />}
          </>
        )}

        {!analysis && (
          <>
            {chartError && <div className="rounded-md bg-loss/10 p-3 text-sm text-loss">{chartError}</div>}
            <ChartPanel chart={chart} theme={theme} />
          </>
        )}
      </div>
    </main>
  );
}

function OverviewTab({ analysis }: { analysis: AnalysisResponse }) {
  return (
    <div className="flex flex-col gap-3">
      <section className="grid gap-3 md:grid-cols-[280px_1fr]">
        <div className="rounded-md border border-line bg-panel p-4">
          <div className="text-sm text-muted">{analysis.analysis_date}</div>
          <div className="mt-1 text-xl font-semibold">
            {analysis.symbol}{analysis.name ? ` ${analysis.name}` : ""}
          </div>
          <div className={`mt-2 text-5xl font-bold ${scoreClass(analysis.adjusted_score)}`}>
            {formatNumber(analysis.adjusted_score, 0)}
          </div>
          <div className="mt-2 text-2xl font-semibold">{analysis.recommendation}</div>
          <div className="mt-3 text-sm text-muted">原始分數 {formatNumber(analysis.raw_score, 0)} / 100</div>
        </div>
        <div className="rounded-md border border-line bg-panel p-4">
          <RiskLightBadges lights={analysis.risk_lights} />
          <p className="mt-4 text-sm leading-6 text-muted">{analysis.disclaimer}</p>
        </div>
      </section>
      <MetricGrid analysis={analysis} />
      <section className="grid gap-3 md:grid-cols-2">
        <InfoList title="主要理由" items={analysis.reasons} tone="gain" limit={5} />
        <InfoList title="風險提醒" items={analysis.risks} tone="loss" limit={5} />
      </section>
    </div>
  );
}

function DecisionTab({ analysis }: { analysis: AnalysisResponse }) {
  const plan = analysis.decision_plan;
  const topReason = analysis.reasons[0] ?? "目前需要更多資料確認。";
  const topRisk = analysis.risks[0] ?? "目前未偵測到重大單一風險。";

  return (
    <div className="flex flex-col gap-3">
      <section className="grid gap-3 lg:grid-cols-[1.1fr_0.9fr]">
        <div className={`rounded-md border p-4 ${biasClass(plan.bias)}`}>
          <div className="text-sm font-medium">決策結論</div>
          <div className="mt-1 text-2xl font-bold">{plan.headline}</div>
          <p className="mt-3 text-sm leading-6">{plan.action}</p>
          <div className="mt-4 grid grid-cols-2 gap-2 md:grid-cols-4">
            <DecisionStat label="偏向" value={biasLabel(plan.bias)} />
            <DecisionStat label="信心" value={plan.confidence} />
            <DecisionStat label="總分" value={formatNumber(analysis.adjusted_score, 0)} />
            <DecisionStat label="建議上限" value={plan.research_position_size} />
          </div>
        </div>
        <div className="rounded-md border border-line bg-panel p-4">
          <h2 className="text-lg font-semibold">證據摘要</h2>
          <div className="mt-3 grid gap-2">
            <EvidenceRow label="最強理由" value={topReason} tone="gain" />
            <EvidenceRow label="最大風險" value={topRisk} tone="loss" />
            <EvidenceRow label="資料信心" value={plan.data_quality[plan.data_quality.length - 1] ?? "資料來源已列出。"} />
          </div>
        </div>
      </section>

      <section className="grid gap-3 md:grid-cols-5">
        {Object.entries(plan.score_breakdown).map(([key, value]) => (
          <div key={key} className="rounded-md border border-line bg-panel p-3">
            <div className="text-xs text-muted">{breakdownLabel(key)}</div>
            <div className={`mt-1 text-lg font-semibold ${value < 0 ? "text-loss" : ""}`}>
              {value > 0 ? "+" : ""}
              {formatNumber(value, 1)}
            </div>
          </div>
        ))}
      </section>

      <section className="grid gap-3 lg:grid-cols-3">
        {Object.entries(plan.checklist).map(([title, items]) => (
          <InfoList
            key={title}
            title={title}
            items={items}
            tone={title === "進場條件" ? "gain" : title === "不進場條件" ? "loss" : "warn"}
          />
        ))}
      </section>

      <section className="grid gap-3 lg:grid-cols-3">
        {plan.scenarios.map((scenario) => (
          <section key={scenario.name} className="rounded-md border border-line bg-panel p-4">
            <h2 className="text-lg font-semibold">{scenario.name}</h2>
            <div className="mt-3 space-y-3 text-sm leading-6">
              <ScenarioLine label="條件" value={scenario.condition} />
              <ScenarioLine label="行動" value={scenario.action} />
              <ScenarioLine label="失效" value={scenario.invalidation} />
            </div>
          </section>
        ))}
      </section>

      <section className="grid gap-3 md:grid-cols-2">
        <TextPanel title="重新檢查觸發點" items={plan.next_review_triggers} />
        <TextPanel title="資料來源與限制" items={plan.data_quality} />
      </section>
    </div>
  );
}

function WatchlistTab({
  input,
  loading,
  error,
  results,
  onInputChange,
  onCompare,
  onSelect
}: {
  input: string;
  loading: boolean;
  error: string | null;
  results: AnalysisResponse[];
  onInputChange: (value: string) => void;
  onCompare: () => void;
  onSelect: (symbol: string) => void;
}) {
  const breadth = useMemo(() => {
    return results.reduce(
      (acc, item) => {
        acc[item.decision_plan.bias] += 1;
        return acc;
      },
      { bullish: 0, neutral: 0, bearish: 0 }
    );
  }, [results]);
  const leader = results[0];

  return (
    <div className="flex flex-col gap-3">
      <section className="rounded-md border border-line bg-panel p-4">
        <div className="grid gap-3 md:grid-cols-[1fr_auto] md:items-end">
          <label className="flex flex-col gap-1 text-sm font-medium">
            自選股清單
            <input
              className="focus-ring h-11 rounded-md border border-line bg-panel px-3 text-base text-ink"
              value={input}
              onChange={(event) => onInputChange(event.target.value)}
              placeholder="2330, 2454, 2317, 0050"
            />
          </label>
          <button
            className="focus-ring h-11 rounded-md bg-ink px-5 font-semibold text-panel disabled:opacity-60"
            type="button"
            onClick={onCompare}
            disabled={loading}
          >
            {loading ? "比較中" : "開始比較"}
          </button>
        </div>
        {error && <div className="mt-3 rounded-md bg-warn/10 p-3 text-sm text-warn">{error}</div>}
      </section>

      <section className="grid gap-3 md:grid-cols-4">
        <DecisionStat label="已比較" value={`${results.length} 檔`} />
        <DecisionStat label="偏多" value={`${breadth.bullish} 檔`} />
        <DecisionStat label="中性" value={`${breadth.neutral} 檔`} />
        <DecisionStat label="偏空" value={`${breadth.bearish} 檔`} />
      </section>

      {leader && (
        <section className={`rounded-md border p-4 ${biasClass(leader.decision_plan.bias)}`}>
          <div className="text-sm font-medium">目前排序第一</div>
          <div className="mt-1 text-2xl font-bold">
            {leader.symbol}{leader.name ? ` ${leader.name}` : ""} · {formatNumber(leader.adjusted_score, 0)} 分
          </div>
          <p className="mt-2 text-sm leading-6">{leader.decision_plan.action}</p>
        </section>
      )}

      <section className="overflow-x-auto rounded-md border border-line bg-panel">
        <table className="w-full min-w-[760px] border-collapse text-left text-sm">
          <thead className="border-b border-line bg-control text-xs text-muted">
            <tr>
              <th className="px-3 py-2 font-semibold">標的</th>
              <th className="px-3 py-2 font-semibold">分數</th>
              <th className="px-3 py-2 font-semibold">偏向</th>
              <th className="px-3 py-2 font-semibold">建議上限</th>
              <th className="px-3 py-2 font-semibold">主要行動</th>
              <th className="px-3 py-2 font-semibold">操作</th>
            </tr>
          </thead>
          <tbody>
            {results.map((item) => (
              <tr key={item.symbol} className="border-b border-line last:border-b-0">
                <td className="px-3 py-3 font-semibold">
                  {item.symbol}{item.name ? ` ${item.name}` : ""}
                </td>
                <td className={`px-3 py-3 font-semibold ${scoreClass(item.adjusted_score)}`}>
                  {formatNumber(item.adjusted_score, 0)}
                </td>
                <td className="px-3 py-3">{biasLabel(item.decision_plan.bias)}</td>
                <td className="px-3 py-3">{item.decision_plan.research_position_size}</td>
                <td className="px-3 py-3 text-muted">{item.decision_plan.action}</td>
                <td className="px-3 py-3">
                  <button
                    className="focus-ring rounded-md border border-line bg-control px-3 py-1.5 font-semibold text-ink"
                    type="button"
                    onClick={() => onSelect(item.symbol)}
                  >
                    分析
                  </button>
                </td>
              </tr>
            ))}
            {!results.length && (
              <tr>
                <td className="px-3 py-8 text-center text-muted" colSpan={6}>
                  輸入自選股後按「開始比較」，這裡會依分數排序。
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </section>
    </div>
  );
}

function PositionTab({ analysis, position }: { analysis: AnalysisResponse; position: PositionSnapshot }) {
  const advice = useMemo(() => buildPositionAdvice(analysis, position.entryPrice), [analysis, position.entryPrice]);

  if (!position.entryPrice) {
    return (
      <section className="rounded-md border border-line bg-panel p-4">
        <h2 className="text-lg font-semibold">持倉停利停損</h2>
        <p className="mt-3 text-sm leading-6 text-muted">
          你還沒有輸入「我的買進價」。輸入後再按「開始分析」，我會幫你算目前損益、固定停損、ATR 停損與移動停利。
        </p>
      </section>
    );
  }

  const stop = analysis.stop_loss;
  const trailing = analysis.trailing_take_profit;
  const close = analysis.technical.latest_close;
  const profitPercent = ((close - position.entryPrice) / position.entryPrice) * 100;

  return (
    <div className="grid gap-3 lg:grid-cols-[1fr_1.25fr]">
      <section className="rounded-md border border-line bg-panel p-4">
        <div className={`rounded-md border p-4 ${toneClass(advice.tone)}`}>
          <div className="text-sm font-medium">持倉判斷</div>
          <div className="mt-1 text-2xl font-bold">{advice.title}</div>
          <p className="mt-2 text-sm leading-6">{advice.message}</p>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-2">
          <PriceBox label="我的買進價" value={position.entryPrice} />
          <PriceBox label="最新收盤價" value={close} />
          <PriceBox label="目前損益" value={profitPercent} suffix="%" signed />
          <PriceBox label="移動停利價" value={trailing.current_take_profit_price} />
        </div>

        <ul className="mt-4 space-y-2 text-sm leading-6 text-muted">
          {advice.points.map((point) => (
            <li key={point}>• {point}</li>
          ))}
        </ul>
      </section>

      <section className="rounded-md border border-line bg-panel p-4">
        <h2 className="text-lg font-semibold">停損停利線</h2>
        <div className="mt-3 grid gap-2 md:grid-cols-2">
          <PriceRow label="固定 -5% 停損" value={stop.fixed_5_percent} />
          <PriceRow label="固定 -8% 停損" value={stop.fixed_8_percent} />
          <PriceRow label="固定 -10% 停損" value={stop.fixed_10_percent} />
          <PriceRow label="ATR 停損" value={stop.atr_stop} />
          <PriceRow label="MA20 跌破" value={stop.ma20_stop_triggered ? "已觸發" : "未觸發"} />
          <PriceRow label="MA60 跌破" value={stop.ma60_stop_triggered ? "已觸發" : "未觸發"} />
          <PriceRow label="移動停利用高點" value={trailing.highest_price_used} />
          <PriceRow label="風險報酬比" value={trailing.risk_reward_ratio} />
        </div>
        <p className="mt-3 text-xs leading-5 text-muted">
          移動停利公式：最高價 - 2 × ATR14。若你沒有填持倉最高價，系統會用近期高點估算。
        </p>
      </section>
    </div>
  );
}

function SignalsTab({ analysis }: { analysis: AnalysisResponse }) {
  return (
    <div className="grid gap-3 md:grid-cols-2">
      <InfoList title="主要理由" items={analysis.reasons} tone="gain" />
      <InfoList title="風險提醒" items={analysis.risks} tone="loss" />
      <TextPanel title="技術訊號" items={analysis.technical.signals} />
      <TextPanel title="法人訊號" items={analysis.institutional.signals} />
    </div>
  );
}

function AiTab({ analysis }: { analysis: AnalysisResponse }) {
  const enabled = Boolean(analysis.sentiment.model);
  return (
    <div className="grid gap-3 md:grid-cols-[320px_1fr]">
      <section className="rounded-md border border-line bg-panel p-4">
        <h2 className="text-lg font-semibold">AI 狀態</h2>
        <div className={`mt-3 rounded-md border p-3 ${enabled ? "border-gain bg-gain/10 text-gain" : "border-warn bg-warn/10 text-warn"}`}>
          {enabled ? "OpenAI 已啟用" : "OpenAI 尚未啟用"}
        </div>
        <p className="mt-3 text-sm leading-6 text-muted">
          {enabled
            ? `目前新聞摘要使用模型：${analysis.sentiment.model}`
            : "目前沒有設定 OpenAI API key，所以新聞摘要使用規則式估計。技術指標、停利停損與評分仍可正常計算。"}
        </p>
      </section>
      <div className="grid gap-3">
        <TextPanel title="AI 新聞摘要" items={[analysis.sentiment.summary, ...analysis.sentiment.headlines]} />
        <SnapshotPromptPanel prompt={analysis.decision_plan.ai_snapshot_prompt} />
      </div>
    </div>
  );
}

function SnapshotPromptPanel({ prompt }: { prompt: string }) {
  return (
    <section className="rounded-md border border-line bg-panel p-4">
      <h2 className="text-lg font-semibold">AI 分析快照</h2>
      <textarea
        className="mt-3 min-h-[16rem] w-full resize-y rounded-md border border-line bg-control p-3 text-sm leading-6 text-ink"
        readOnly
        value={prompt}
      />
    </section>
  );
}

function ThemeToggle({ theme, onChange }: { theme: Theme; onChange: (theme: Theme) => void }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-sm text-muted">外觀</span>
      <div className="rounded-md border border-line bg-control p-1">
        {(["light", "dark"] as const).map((item) => (
          <button
            key={item}
            className={`focus-ring rounded px-3 py-1.5 text-sm font-medium ${
              theme === item ? "bg-panel text-ink shadow-sm" : "text-muted hover:text-ink"
            }`}
            type="button"
            onClick={() => onChange(item)}
          >
            {item === "light" ? "淺色" : "深色"}
          </button>
        ))}
      </div>
    </div>
  );
}

function InfoList({
  title,
  items,
  tone,
  limit = 8
}: {
  title: string;
  items: string[];
  tone: "gain" | "warn" | "loss";
  limit?: number;
}) {
  const toneColor = tone === "gain" ? "text-gain" : tone === "warn" ? "text-warn" : "text-loss";
  return (
    <section className="rounded-md border border-line bg-panel p-4">
      <h2 className={`text-lg font-semibold ${toneColor}`}>{title}</h2>
      <ul className="mt-3 space-y-2 text-sm leading-6">
        {items.slice(0, limit).map((item, index) => (
          <li key={`${index}-${item}`}>• {item}</li>
        ))}
      </ul>
    </section>
  );
}

function TextPanel({ title, items }: { title: string; items: string[] }) {
  return (
    <section className="rounded-md border border-line bg-panel p-4">
      <h2 className="text-lg font-semibold">{title}</h2>
      <ul className="mt-3 space-y-2 text-sm leading-6 text-muted">
        {items.length ? items.slice(0, 8).map((item, index) => <li key={`${index}-${item}`}>• {item}</li>) : <li>尚無訊號</li>}
      </ul>
    </section>
  );
}

function DecisionStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-line bg-panel/70 p-3">
      <div className="text-xs text-muted">{label}</div>
      <div className="mt-1 text-base font-semibold leading-6">{value}</div>
    </div>
  );
}

function EvidenceRow({
  label,
  value,
  tone = "neutral"
}: {
  label: string;
  value: string;
  tone?: "gain" | "loss" | "neutral";
}) {
  const color = tone === "gain" ? "text-gain" : tone === "loss" ? "text-loss" : "text-ink";
  return (
    <div className="rounded-md border border-line bg-control p-3">
      <div className="text-xs text-muted">{label}</div>
      <div className={`mt-1 text-sm font-medium leading-6 ${color}`}>{value}</div>
    </div>
  );
}

function ScenarioLine({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs font-semibold text-muted">{label}</div>
      <div className="mt-1 text-muted">{value}</div>
    </div>
  );
}

function biasLabel(bias: "bullish" | "neutral" | "bearish") {
  if (bias === "bullish") return "偏多";
  if (bias === "bearish") return "偏空";
  return "中性";
}

function biasClass(bias: "bullish" | "neutral" | "bearish") {
  if (bias === "bullish") return "border-gain bg-gain/10 text-gain";
  if (bias === "bearish") return "border-loss bg-loss/10 text-loss";
  return "border-warn bg-warn/10 text-warn";
}

function breakdownLabel(key: string) {
  const labels: Record<string, string> = {
    technical: "技術",
    institutional: "法人",
    fundamental: "基本面",
    sentiment: "新聞情緒",
    market_risk_adjustment: "市場風險調整"
  };
  return labels[key] ?? key;
}

function PriceBox({
  label,
  value,
  suffix,
  signed
}: {
  label: string;
  value: number | null | undefined;
  suffix?: string;
  signed?: boolean;
}) {
  const numericValue = typeof value === "number" ? value : null;
  const color = signed && numericValue !== null ? (numericValue >= 0 ? "text-gain" : "text-loss") : "";
  return (
    <div className="rounded-md border border-line bg-control p-3">
      <div className="text-xs text-muted">{label}</div>
      <div className={`mt-1 text-lg font-semibold ${color}`}>
        {numericValue === null ? "-" : `${signed && numericValue > 0 ? "+" : ""}${formatNumber(numericValue)}${suffix ?? ""}`}
      </div>
    </div>
  );
}

function PriceRow({ label, value }: { label: string; value: number | string | null | undefined }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-md border border-line bg-control px-3 py-2 text-sm">
      <span className="text-muted">{label}</span>
      <span className="font-semibold">{typeof value === "number" ? formatNumber(value) : value ?? "-"}</span>
    </div>
  );
}

function buildPositionAdvice(analysis: AnalysisResponse, entryPrice: number | null) {
  if (!entryPrice) {
    return {
      tone: "neutral" as const,
      title: "尚未輸入買進價",
      message: "輸入買進價後，才能判斷你的持倉該續抱、停利或停損。",
      points: []
    };
  }

  const close = analysis.technical.latest_close;
  const profitPercent = ((close - entryPrice) / entryPrice) * 100;
  const stop = analysis.stop_loss;
  const trailing = analysis.trailing_take_profit;
  const atrStop = stop.atr_stop;
  const trailingPrice = trailing.current_take_profit_price;

  const points = [
    `目前損益約 ${formatPercent(profitPercent)}。`,
    `ATR 停損價是 ${formatNumber(atrStop)}。`,
    `移動停利價是 ${formatNumber(trailingPrice)}。`
  ];

  if (atrStop !== null && atrStop !== undefined && close <= atrStop) {
    return {
      tone: "loss" as const,
      title: "停損線已觸發",
      message: "目前價格已跌到 ATR 停損線下方，風險優先，不建議用情緒凹單。",
      points
    };
  }
  if (trailingPrice !== null && trailingPrice !== undefined && close <= trailingPrice && close > entryPrice) {
    return {
      tone: "warn" as const,
      title: "移動停利已觸發",
      message: "目前仍是獲利，但價格已跌破移動停利線，適合考慮分批停利或降低部位。",
      points
    };
  }
  if (stop.ma60_stop_triggered) {
    return {
      tone: "loss" as const,
      title: "中期趨勢轉弱",
      message: "價格跌破 MA60，波段防守要優先，適合減碼或依停損規則處理。",
      points
    };
  }
  if (stop.ma20_stop_triggered) {
    return {
      tone: "warn" as const,
      title: "短線防守",
      message: "價格跌破 MA20，還不到最壞，但應該提高警覺並避免加碼。",
      points
    };
  }
  if (profitPercent >= 12) {
    return {
      tone: "gain" as const,
      title: "獲利中，守移動停利",
      message: "目前獲利幅度不小，可以續抱，但要把移動停利價當成紀律線。",
      points
    };
  }
  if (profitPercent >= 3) {
    return {
      tone: "gain" as const,
      title: "小獲利，持有觀察",
      message: "目前有獲利但還不到明確停利區，適合持有並觀察技術面是否轉弱。",
      points
    };
  }
  if (profitPercent <= -5) {
    return {
      tone: "warn" as const,
      title: "虧損擴大，接近停損",
      message: "目前虧損已超過 5%，要嚴格看固定停損與 ATR 停損，不要靠感覺補倉。",
      points
    };
  }
  return {
    tone: "neutral" as const,
    title: "持有觀察",
    message: "目前還沒有明確停利或停損訊號，先照停損線與技術訊號管理。",
    points
  };
}

function toneClass(tone: "gain" | "warn" | "loss" | "neutral") {
  if (tone === "gain") return "border-gain bg-gain/10 text-gain";
  if (tone === "warn") return "border-warn bg-warn/10 text-warn";
  if (tone === "loss") return "border-loss bg-loss/10 text-loss";
  return "border-line bg-control text-ink";
}

function parsePositiveNumber(value: string): number | null {
  const normalized = value.trim().replace(/,/g, "");
  if (!normalized) return null;
  const parsed = Number(normalized);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

function parseWatchlistSymbols(value: string) {
  const symbols = value
    .split(/[\s,，、]+/)
    .map((item) => item.trim().toUpperCase())
    .filter(Boolean)
    .map((item) => item.replace(/[^A-Z0-9.^-]/g, ""))
    .filter(Boolean);
  return Array.from(new Set(symbols)).slice(0, 8);
}

function formatPercent(value: number) {
  return `${value > 0 ? "+" : ""}${formatNumber(value)}%`;
}
