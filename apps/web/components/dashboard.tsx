"use client";

import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import {
  closePosition,
  createWatchlistItem,
  deleteWatchlistItem,
  fetchAiPicks,
  fetchAnalysis,
  fetchChart,
  fetchPositions,
  fetchWatchlist,
  generatePdf,
  savePosition
} from "@/lib/api";
import { formatNumber, scoreClass } from "@/lib/format";
import type {
  AiStockPick,
  AiStockPicksResponse,
  AnalysisResponse,
  ChartResponse,
  Light,
  MarketRefreshInfo,
  PositionItem,
  WatchlistItem
} from "@/lib/types";
import { ChartPanel } from "./chart-panel";
import { RiskLightBadges } from "./risk-lights";

type Theme = "light" | "dark";
type Tone = "gain" | "warn" | "loss" | "neutral";
type DashboardView = "overview" | "chart" | "watchlist" | "positions" | "settings";

const DEFAULT_SYMBOL = "2330";
const DEFAULT_WATCHLIST = "2330, 2454, 2317, 0050";
const WATCHLIST_STORAGE_KEY = "stockai-watchlist-symbols";
const VIEW_STORAGE_KEY = "stockai-dashboard-view";
const FALLBACK_REFRESH_SECONDS = 900;
const DASHBOARD_VIEWS: Array<{ id: DashboardView; label: string; description: string }> = [
  { id: "overview", label: "看盤總覽", description: "AI 選股與目前個股判斷" },
  { id: "chart", label: "價格圖表", description: "K 線、均線與技術指標" },
  { id: "watchlist", label: "自選清單", description: "管理掃描清單與候選股" },
  { id: "positions", label: "持倉管理", description: "買進價、股數與停損停利" },
  { id: "settings", label: "設定匯出", description: "主題、更新狀態與 PDF" }
];

export function Dashboard() {
  const [symbol, setSymbol] = useState(DEFAULT_SYMBOL);
  const [range, setRange] = useState("1y");
  const [entryPrice, setEntryPrice] = useState("");
  const [highestPrice, setHighestPrice] = useState("");
  const [quantity, setQuantity] = useState("");
  const [watchlistInput, setWatchlistInput] = useState(DEFAULT_WATCHLIST);
  const [watchlistItems, setWatchlistItems] = useState<WatchlistItem[]>([]);
  const [positions, setPositions] = useState<PositionItem[]>([]);
  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null);
  const [chart, setChart] = useState<ChartResponse | null>(null);
  const [aiPicks, setAiPicks] = useState<AiStockPicksResponse | null>(null);
  const [theme, setTheme] = useState<Theme>("light");
  const [activeView, setActiveView] = useState<DashboardView>("overview");
  const [menuOpen, setMenuOpen] = useState(false);
  const [bootReady, setBootReady] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [savingWatchlist, setSavingWatchlist] = useState(false);
  const [savingPosition, setSavingPosition] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [pdfPath, setPdfPath] = useState<string | null>(null);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<string | null>(null);
  const refreshInFlight = useRef(false);
  const didInitialLoad = useRef(false);

  const refreshInfo = aiPicks?.refresh ?? analysis?.refresh ?? null;
  const watchlistSymbols = useMemo(() => parseSymbols(watchlistInput), [watchlistInput]);
  const currentPosition = positions.find((item) => item.symbol === symbol.toUpperCase());

  useEffect(() => {
    const savedTheme = localStorage.getItem("stockai-theme");
    const savedWatchlist = localStorage.getItem(WATCHLIST_STORAGE_KEY);
    const savedView = localStorage.getItem(VIEW_STORAGE_KEY);
    const preferred = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    const nextTheme = savedTheme === "dark" || savedTheme === "light" ? savedTheme : preferred;
    setTheme(nextTheme);
    document.documentElement.dataset.theme = nextTheme;
    if (savedWatchlist) {
      setWatchlistInput(savedWatchlist);
    }
    if (isDashboardView(savedView)) {
      setActiveView(savedView);
    }
    setBootReady(true);
  }, []);

  useEffect(() => {
    if (!bootReady) return;
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("stockai-theme", theme);
  }, [bootReady, theme]);

  useEffect(() => {
    if (!bootReady) return;
    localStorage.setItem(WATCHLIST_STORAGE_KEY, watchlistInput);
  }, [bootReady, watchlistInput]);

  useEffect(() => {
    if (!bootReady) return;
    localStorage.setItem(VIEW_STORAGE_KEY, activeView);
  }, [activeView, bootReady]);

  useEffect(() => {
    if (!bootReady) return;
    async function loadSavedState() {
      try {
        const [savedWatchlist, openPositions] = await Promise.all([fetchWatchlist(), fetchPositions("open")]);
        setWatchlistItems(savedWatchlist);
        setPositions(openPositions);
        if (savedWatchlist.length) {
          setWatchlistInput(savedWatchlist.map((item) => item.symbol).join(", "));
        }
        const savedPosition = openPositions.find((item) => item.symbol === DEFAULT_SYMBOL);
        if (savedPosition) {
          setEntryPrice(String(savedPosition.entry_price));
          setHighestPrice(savedPosition.highest_price ? String(savedPosition.highest_price) : "");
          setQuantity(savedPosition.quantity ? String(savedPosition.quantity) : "");
        }
      } catch {
        setMessage("自選股或持倉暫時讀取失敗，仍可直接查詢分析。");
      }
    }

    void loadSavedState();
  }, [bootReady]);

  const refreshAll = useCallback(
    async (options: { silent?: boolean; nextSymbol?: string } = {}) => {
      const { silent = false } = options;
      if (refreshInFlight.current) return;

      const nextSymbol = normalizeSymbol(options.nextSymbol ?? symbol);
      const parsedEntry = parsePositiveNumber(entryPrice);
      const parsedHighest = parsePositiveNumber(highestPrice);

      if (entryPrice.trim() && parsedEntry === null) {
        setError("買進價請輸入大於 0 的數字。");
        return;
      }
      if (highestPrice.trim() && parsedHighest === null) {
        setError("最高價請輸入大於 0 的數字。");
        return;
      }

      refreshInFlight.current = true;
      setError(null);
      setPdfPath(null);
      if (silent) {
        setRefreshing(true);
      } else {
        setLoading(true);
      }

      const symbols = parseSymbols(watchlistInput);
      const [analysisResult, chartResult, picksResult] = await Promise.allSettled([
        fetchAnalysis(nextSymbol, {
          entryPrice: parsedEntry ?? undefined,
          highestPrice: parsedHighest ?? undefined,
          atrMultiplier: 2
        }),
        fetchChart(nextSymbol, range),
        fetchAiPicks({ universe: symbols.length ? symbols : undefined, limit: 5, minScore: 55 })
      ]);

      const errors: string[] = [];
      if (analysisResult.status === "fulfilled") {
        setAnalysis(analysisResult.value);
        setSymbol(analysisResult.value.symbol);
      } else {
        errors.push(readError(analysisResult.reason, "個股分析讀取失敗"));
      }

      if (chartResult.status === "fulfilled") {
        setChart(chartResult.value);
      } else {
        errors.push(readError(chartResult.reason, "圖表讀取失敗"));
      }

      if (picksResult.status === "fulfilled") {
        setAiPicks(picksResult.value);
      } else {
        errors.push(readError(picksResult.reason, "AI 選股讀取失敗"));
      }

      if (errors.length) {
        setError(errors.join(" / "));
      } else {
        setMessage(silent ? "已依台北時間自動更新。" : "分析已更新。");
      }
      if (analysisResult.status === "fulfilled" || picksResult.status === "fulfilled") {
        setLastUpdatedAt(new Date().toISOString());
      }

      refreshInFlight.current = false;
      setLoading(false);
      setRefreshing(false);
    },
    [entryPrice, highestPrice, range, symbol, watchlistInput]
  );

  useEffect(() => {
    if (!bootReady || didInitialLoad.current) return;
    didInitialLoad.current = true;
    void refreshAll();
  }, [bootReady, refreshAll]);

  useEffect(() => {
    if (!autoRefresh || !analysis) return;
    const seconds = refreshInfo?.refresh_interval_seconds ?? FALLBACK_REFRESH_SECONDS;
    const delay = Math.max(15, seconds) * 1000;
    const timer = window.setTimeout(() => {
      void refreshAll({ silent: true });
    }, delay);
    return () => window.clearTimeout(timer);
  }, [analysis, autoRefresh, refreshAll, refreshInfo?.refresh_interval_seconds]);

  function submit(event: FormEvent) {
    event.preventDefault();
    void refreshAll();
  }

  async function saveCurrentWatchlist() {
    const symbols = parseSymbols(watchlistInput);
    if (!symbols.length) {
      setError("請至少輸入一檔自選股，例如 2330, 2454。");
      return;
    }

    setSavingWatchlist(true);
    setError(null);
    try {
      const existing = await fetchWatchlist();
      const desired = new Set(symbols);
      const kept = new Set<string>();
      await Promise.all(
        existing.map((item) => {
          const normalized = normalizeSymbol(item.symbol);
          if (!desired.has(normalized) || kept.has(normalized)) {
            return deleteWatchlistItem(item.id);
          }
          kept.add(normalized);
          return Promise.resolve({ status: "kept" });
        })
      );
      await Promise.all(symbols.filter((item) => !kept.has(item)).map((item) => createWatchlistItem(item)));
      const updated = await fetchWatchlist();
      setWatchlistItems(updated);
      setWatchlistInput(updated.map((item) => item.symbol).join(", ") || symbols.join(", "));
      setMessage(`已儲存 ${symbols.length} 檔自選股。`);
      void refreshAll({ silent: true });
    } catch (err) {
      setError(readError(err, "自選股儲存失敗"));
    } finally {
      setSavingWatchlist(false);
    }
  }

  async function saveCurrentPosition() {
    const parsedEntry = parsePositiveNumber(entryPrice);
    const parsedHighest = parsePositiveNumber(highestPrice);
    const parsedQuantity = parseNonNegativeNumber(quantity);

    if (parsedEntry === null) {
      setError("請先輸入買進價，才能儲存持倉。");
      return;
    }
    if (highestPrice.trim() && parsedHighest === null) {
      setError("最高價請輸入大於 0 的數字。");
      return;
    }
    if (quantity.trim() && parsedQuantity === null) {
      setError("股數請輸入 0 或大於 0 的數字。");
      return;
    }

    setSavingPosition(true);
    setError(null);
    try {
      const saved = await savePosition({
        symbol,
        entry_price: parsedEntry,
        quantity: parsedQuantity ?? 0,
        highest_price: parsedHighest
      });
      const updated = await fetchPositions("open");
      setPositions(updated);
      setSymbol(saved.symbol);
      setMessage(`已儲存 ${saved.symbol} 持倉。`);
      void refreshAll({ silent: true });
    } catch (err) {
      setError(readError(err, "持倉儲存失敗"));
    } finally {
      setSavingPosition(false);
    }
  }

  async function closeCurrentPosition() {
    if (!currentPosition) return;
    setSavingPosition(true);
    setError(null);
    try {
      await closePosition(currentPosition.id);
      setPositions(await fetchPositions("open"));
      setMessage(`已結束 ${currentPosition.symbol} 持倉。`);
    } catch (err) {
      setError(readError(err, "持倉結束失敗"));
    } finally {
      setSavingPosition(false);
    }
  }

  async function createPdf() {
    if (!analysis) return;
    setError(null);
    setPdfPath(null);
    try {
      const result = await generatePdf(analysis.symbol);
      setPdfPath(result.file_path);
    } catch (err) {
      setError(readError(err, "PDF 產生失敗"));
    }
  }

  function selectSymbol(nextSymbol: string) {
    const normalized = normalizeSymbol(nextSymbol);
    setSymbol(normalized);
    const savedPosition = positions.find((item) => item.symbol === normalized);
    if (savedPosition) {
      setEntryPrice(String(savedPosition.entry_price));
      setHighestPrice(savedPosition.highest_price ? String(savedPosition.highest_price) : "");
      setQuantity(savedPosition.quantity ? String(savedPosition.quantity) : "");
    }
    void refreshAll({ silent: true, nextSymbol: normalized });
  }

  return (
    <main className="min-h-screen bg-paper px-4 py-4 text-ink md:px-8">
      <div className="mx-auto flex max-w-7xl flex-col gap-4">
        <AppHeader
          activeView={activeView}
          menuOpen={menuOpen}
          theme={theme}
          onMenuOpenChange={setMenuOpen}
          onThemeChange={setTheme}
          onViewChange={setActiveView}
        />

        <CommandBar
          analysis={analysis}
          loading={loading}
          range={range}
          refreshing={refreshing}
          symbol={symbol}
          onRangeChange={setRange}
          onSubmit={submit}
          onSymbolChange={setSymbol}
        />

        {error && <Notice tone="loss">{error}</Notice>}
        {message && !error && <Notice tone="gain">{message}</Notice>}
        {pdfPath && <Notice tone="gain">PDF 已產生：{pdfPath}</Notice>}

        {activeView === "overview" && (
          <>
            <MarketStatus
              refreshInfo={refreshInfo}
              loading={loading}
              refreshing={refreshing}
              autoRefresh={autoRefresh}
              lastUpdatedAt={lastUpdatedAt}
              onAutoRefreshChange={setAutoRefresh}
              onRefresh={() => void refreshAll()}
            />
            <section className="grid min-w-0 gap-4 xl:grid-cols-[1.05fr_0.95fr]">
              <AiPickerPanel
                result={aiPicks}
                loading={loading && !aiPicks}
                watchlistCount={watchlistSymbols.length}
                onSelect={selectSymbol}
              />
              <AnalysisPanel analysis={analysis} loading={loading && !analysis} />
            </section>
          </>
        )}

        {activeView === "chart" && <ChartPanel chart={chart} theme={theme} />}

        {activeView === "watchlist" && (
          <>
            <WatchlistEditor
              saving={savingWatchlist}
              value={watchlistInput}
              onChange={setWatchlistInput}
              onSave={saveCurrentWatchlist}
            />
            <section className="grid min-w-0 gap-4 lg:grid-cols-[0.8fr_1.2fr]">
              <WatchlistPanel items={watchlistItems} symbols={watchlistSymbols} onSelect={selectSymbol} />
              <AiPickerPanel
                result={aiPicks}
                loading={loading && !aiPicks}
                watchlistCount={watchlistSymbols.length}
                onSelect={selectSymbol}
              />
            </section>
          </>
        )}

        {activeView === "positions" && (
          <>
            <PositionEditor
              currentPosition={currentPosition}
              entryPrice={entryPrice}
              highestPrice={highestPrice}
              quantity={quantity}
              saving={savingPosition}
              onClose={closeCurrentPosition}
              onEntryPriceChange={setEntryPrice}
              onHighestPriceChange={setHighestPrice}
              onQuantityChange={setQuantity}
              onSave={saveCurrentPosition}
            />
            <section className="grid min-w-0 gap-4 lg:grid-cols-[0.95fr_1.05fr]">
              <PositionPanel positions={positions} onSelect={selectSymbol} />
              <AnalysisPanel analysis={analysis} loading={loading && !analysis} />
            </section>
          </>
        )}

        {activeView === "settings" && (
          <SettingsPanel
            analysis={analysis}
            autoRefresh={autoRefresh}
            lastUpdatedAt={lastUpdatedAt}
            loading={loading}
            refreshInfo={refreshInfo}
            refreshing={refreshing}
            theme={theme}
            onAutoRefreshChange={setAutoRefresh}
            onCreatePdf={createPdf}
            onRefresh={() => void refreshAll()}
            onThemeChange={setTheme}
          />
        )}
      </div>
    </main>
  );
}

function AppHeader({
  activeView,
  menuOpen,
  theme,
  onMenuOpenChange,
  onThemeChange,
  onViewChange
}: {
  activeView: DashboardView;
  menuOpen: boolean;
  theme: Theme;
  onMenuOpenChange: (value: boolean) => void;
  onThemeChange: (theme: Theme) => void;
  onViewChange: (view: DashboardView) => void;
}) {
  const currentView = DASHBOARD_VIEWS.find((item) => item.id === activeView) ?? DASHBOARD_VIEWS[0];

  return (
    <header className="relative flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
      <div className="flex min-w-0 items-center gap-3">
        <div className="relative shrink-0">
          <button
            aria-expanded={menuOpen}
            className="focus-ring h-11 rounded-md border border-line bg-panel px-4 text-sm font-semibold text-ink"
            type="button"
            onClick={() => onMenuOpenChange(!menuOpen)}
          >
            ☰ 主選單
          </button>
          {menuOpen && (
            <div className="absolute left-0 top-12 z-20 w-72 rounded-md border border-line bg-panel p-2 shadow-lg">
              {DASHBOARD_VIEWS.map((item) => (
                <button
                  key={item.id}
                  aria-current={activeView === item.id ? "page" : undefined}
                  className={`focus-ring block w-full rounded-md px-3 py-2 text-left ${
                    activeView === item.id ? "bg-ink text-panel" : "text-ink hover:bg-control"
                  }`}
                  type="button"
                  onClick={() => {
                    onViewChange(item.id);
                    onMenuOpenChange(false);
                  }}
                >
                  <span className="block text-sm font-semibold">{item.label}</span>
                  <span className={`mt-0.5 block text-xs ${activeView === item.id ? "text-panel/80" : "text-muted"}`}>
                    {item.description}
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>
        <div className="min-w-0">
          <h1 className="truncate text-2xl font-semibold tracking-normal">台股 AI 即時看盤</h1>
          <p className="mt-1 text-sm text-muted">{currentView.description}</p>
        </div>
      </div>
      <ThemeToggle theme={theme} onChange={onThemeChange} />
    </header>
  );
}

function CommandBar({
  analysis,
  loading,
  range,
  refreshing,
  symbol,
  onRangeChange,
  onSubmit,
  onSymbolChange
}: {
  analysis: AnalysisResponse | null;
  loading: boolean;
  range: string;
  refreshing: boolean;
  symbol: string;
  onRangeChange: (value: string) => void;
  onSubmit: (event: FormEvent) => void;
  onSymbolChange: (value: string) => void;
}) {
  return (
    <section className="rounded-md border border-line bg-panel p-3">
      <form className="grid gap-3 md:grid-cols-[180px_150px_120px_1fr] md:items-end" onSubmit={onSubmit}>
        <label className="flex flex-col gap-1 text-sm font-medium">
          股票代號
          <input
            className="focus-ring h-11 rounded-md border border-line bg-panel px-3 text-base text-ink"
            value={symbol}
            onChange={(event) => onSymbolChange(event.target.value.toUpperCase())}
            placeholder="2330"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm font-medium">
          圖表期間
          <select
            className="focus-ring h-11 rounded-md border border-line bg-panel px-3 text-ink"
            value={range}
            onChange={(event) => onRangeChange(event.target.value)}
          >
            <option value="1y">1 年</option>
            <option value="3y">3 年</option>
            <option value="5y">5 年</option>
          </select>
        </label>
        <button
          className="focus-ring h-11 rounded-md bg-ink px-5 font-semibold text-panel disabled:opacity-60"
          type="submit"
          disabled={loading || refreshing}
        >
          {loading || refreshing ? "更新中" : "立即更新"}
        </button>
        <div className="flex min-h-11 flex-wrap items-center gap-2 text-sm text-muted md:justify-end">
          <span className="rounded-md border border-line bg-control px-3 py-2">
            最新價 {analysis ? formatNumber(analysis.technical.latest_close) : "-"}
          </span>
          <span className="rounded-md border border-line bg-control px-3 py-2">
            資料 {analysis?.data_sources.price ?? "-"}
          </span>
        </div>
      </form>
    </section>
  );
}

function WatchlistEditor({
  saving,
  value,
  onChange,
  onSave
}: {
  saving: boolean;
  value: string;
  onChange: (value: string) => void;
  onSave: () => void;
}) {
  return (
    <section className="rounded-md border border-line bg-panel p-4">
      <div className="grid gap-3 md:grid-cols-[1fr_auto] md:items-end">
        <label className="flex flex-col gap-1 text-sm font-medium">
          AI 掃描清單
          <input
            className="focus-ring h-11 rounded-md border border-line bg-panel px-3 text-base text-ink"
            value={value}
            onChange={(event) => onChange(event.target.value)}
            placeholder={DEFAULT_WATCHLIST}
          />
        </label>
        <button
          className="focus-ring h-11 rounded-md bg-ink px-5 font-semibold text-panel disabled:opacity-60"
          type="button"
          onClick={onSave}
          disabled={saving}
        >
          {saving ? "儲存中" : "儲存清單"}
        </button>
      </div>
    </section>
  );
}

function PositionEditor({
  currentPosition,
  entryPrice,
  highestPrice,
  quantity,
  saving,
  onClose,
  onEntryPriceChange,
  onHighestPriceChange,
  onQuantityChange,
  onSave
}: {
  currentPosition: PositionItem | undefined;
  entryPrice: string;
  highestPrice: string;
  quantity: string;
  saving: boolean;
  onClose: () => void;
  onEntryPriceChange: (value: string) => void;
  onHighestPriceChange: (value: string) => void;
  onQuantityChange: (value: string) => void;
  onSave: () => void;
}) {
  return (
    <section className="rounded-md border border-line bg-panel p-4">
      <div className="grid gap-3 md:grid-cols-5 md:items-end">
        <label className="flex flex-col gap-1 text-sm font-medium">
          買進價
          <input
            className="focus-ring h-11 rounded-md border border-line bg-panel px-3 text-base text-ink"
            inputMode="decimal"
            value={entryPrice}
            onChange={(event) => onEntryPriceChange(event.target.value)}
            placeholder="可空白"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm font-medium">
          持有最高價
          <input
            className="focus-ring h-11 rounded-md border border-line bg-panel px-3 text-base text-ink"
            inputMode="decimal"
            value={highestPrice}
            onChange={(event) => onHighestPriceChange(event.target.value)}
            placeholder="可空白"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm font-medium">
          股數
          <input
            className="focus-ring h-11 rounded-md border border-line bg-panel px-3 text-base text-ink"
            inputMode="decimal"
            value={quantity}
            onChange={(event) => onQuantityChange(event.target.value)}
            placeholder="可空白"
          />
        </label>
        <button
          className="focus-ring h-11 rounded-md bg-ink px-5 font-semibold text-panel disabled:opacity-60"
          type="button"
          onClick={onSave}
          disabled={saving}
        >
          {currentPosition ? "更新持倉" : "儲存持倉"}
        </button>
        <button
          className="focus-ring h-11 rounded-md border border-line bg-control px-5 font-semibold text-ink disabled:opacity-50"
          type="button"
          onClick={onClose}
          disabled={saving || !currentPosition}
        >
          結束持倉
        </button>
      </div>
    </section>
  );
}

function SettingsPanel({
  analysis,
  autoRefresh,
  lastUpdatedAt,
  loading,
  refreshInfo,
  refreshing,
  theme,
  onAutoRefreshChange,
  onCreatePdf,
  onRefresh,
  onThemeChange
}: {
  analysis: AnalysisResponse | null;
  autoRefresh: boolean;
  lastUpdatedAt: string | null;
  loading: boolean;
  refreshInfo: MarketRefreshInfo | null;
  refreshing: boolean;
  theme: Theme;
  onAutoRefreshChange: (value: boolean) => void;
  onCreatePdf: () => void;
  onRefresh: () => void;
  onThemeChange: (theme: Theme) => void;
}) {
  return (
    <section className="grid gap-4 lg:grid-cols-[0.85fr_1.15fr]">
      <section className="rounded-md border border-line bg-panel p-4">
        <h2 className="text-lg font-semibold">設定</h2>
        <div className="mt-4 grid gap-3">
          <ThemeToggle theme={theme} onChange={onThemeChange} />
          <label className="flex h-11 items-center gap-2 rounded-md border border-line bg-control px-3 text-sm font-medium">
            <input checked={autoRefresh} onChange={(event) => onAutoRefreshChange(event.target.checked)} type="checkbox" />
            自動更新
          </label>
          <button
            className="focus-ring h-11 rounded-md bg-ink px-5 font-semibold text-panel disabled:opacity-60"
            type="button"
            onClick={onRefresh}
            disabled={loading || refreshing}
          >
            {loading || refreshing ? "更新中" : "立即更新"}
          </button>
          <button
            className="focus-ring h-11 rounded-md border border-line bg-control px-5 font-semibold text-ink disabled:opacity-50"
            type="button"
            onClick={onCreatePdf}
            disabled={!analysis}
          >
            匯出 PDF
          </button>
        </div>
      </section>
      <section className="rounded-md border border-line bg-panel p-4">
        <h2 className="text-lg font-semibold">更新狀態</h2>
        <div className="mt-4 grid gap-2 sm:grid-cols-2">
          <StatusTile label="市場狀態" value={refreshInfo?.label ?? "-"} />
          <StatusTile label="更新頻率" value={refreshInfo ? formatDuration(refreshInfo.refresh_interval_seconds) : "-"} />
          <StatusTile label="下次更新" value={refreshInfo ? formatTime(refreshInfo.next_refresh_at) : "-"} />
          <StatusTile label="最後更新" value={lastUpdatedAt ? formatDateTime(lastUpdatedAt) : "-"} />
          <StatusTile label="價格來源" value={analysis?.data_sources.price ?? "-"} />
          <StatusTile label="新聞來源" value={analysis?.data_sources.news ?? "-"} />
        </div>
        <p className="mt-3 text-sm leading-6 text-muted">{refreshInfo?.message ?? "尚未讀取市場時鐘。"}</p>
      </section>
    </section>
  );
}

function MarketStatus({
  refreshInfo,
  loading,
  refreshing,
  autoRefresh,
  lastUpdatedAt,
  onAutoRefreshChange,
  onRefresh
}: {
  refreshInfo: MarketRefreshInfo | null;
  loading: boolean;
  refreshing: boolean;
  autoRefresh: boolean;
  lastUpdatedAt: string | null;
  onAutoRefreshChange: (value: boolean) => void;
  onRefresh: () => void;
}) {
  const tone = refreshInfo?.is_regular_session ? "gain" : refreshInfo?.is_live_refresh ? "warn" : "neutral";
  const label = refreshInfo?.label ?? "讀取中";
  const interval = refreshInfo ? formatDuration(refreshInfo.refresh_interval_seconds) : "-";

  return (
    <section className="min-w-0 rounded-md border border-line bg-panel p-4">
      <div className="grid gap-3 md:grid-cols-[1fr_auto] md:items-center">
        <div className="grid gap-2 md:grid-cols-4">
          <StatusTile label="市場狀態" value={label} tone={tone} />
          <StatusTile label="台北時間" value={refreshInfo ? formatDateTime(refreshInfo.now) : "-"} />
          <StatusTile label="更新頻率" value={interval} />
          <StatusTile label="下次更新" value={refreshInfo ? formatTime(refreshInfo.next_refresh_at) : "-"} />
        </div>
        <div className="flex flex-wrap items-center gap-2 md:justify-end">
          <label className="flex h-10 items-center gap-2 rounded-md border border-line bg-control px-3 text-sm font-medium">
            <input
              checked={autoRefresh}
              onChange={(event) => onAutoRefreshChange(event.target.checked)}
              type="checkbox"
            />
            自動更新
          </label>
          <button
            className="focus-ring h-10 rounded-md bg-ink px-4 text-sm font-semibold text-panel disabled:opacity-60"
            type="button"
            onClick={onRefresh}
            disabled={loading || refreshing}
          >
            {loading || refreshing ? "更新中" : "立即更新"}
          </button>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-muted">
        <span>{refreshInfo?.message ?? "正在讀取市場時鐘。"}</span>
        {lastUpdatedAt && <span>最後更新：{formatDateTime(lastUpdatedAt)}</span>}
        {refreshing && <span className="font-semibold text-gain">背景更新中</span>}
      </div>
    </section>
  );
}

function AiPickerPanel({
  result,
  loading,
  watchlistCount,
  onSelect
}: {
  result: AiStockPicksResponse | null;
  loading: boolean;
  watchlistCount: number;
  onSelect: (symbol: string) => void;
}) {
  const market = result?.market_snapshot;
  const picks = result?.top_picks ?? [];

  return (
    <section className="rounded-md border border-line bg-panel p-4">
      <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
        <div>
          <h2 className="text-lg font-semibold">AI 盤中選股</h2>
          <p className="mt-1 text-sm leading-6 text-muted">用目前盤勢、技術面、籌碼與風險分數掃描自選清單。</p>
        </div>
        <span className="rounded-md border border-line bg-control px-3 py-1.5 text-sm text-muted">
          掃描 {result?.universe.length ?? watchlistCount} 檔
        </span>
      </div>

      {market && (
        <div className="mt-4 grid gap-2 sm:grid-cols-3">
          <StatusTile label="盤勢" value={market.status} tone={lightTone(market.light)} />
          <StatusTile label="大盤分數" value={formatNumber(market.score, 0)} tone={lightTone(market.light)} />
          <StatusTile label="燈號" value={lightLabel(market.light)} tone={lightTone(market.light)} />
        </div>
      )}

      {loading && <EmptyState title="正在掃描" detail="AI 選股讀取中。" />}

      {!loading && !picks.length && <EmptyState title="尚無選股結果" detail="按上方更新後會顯示候選清單。" />}

      <div className="mt-4 grid gap-3">
        {picks.map((pick) => (
          <AiPickRow key={pick.symbol} pick={pick} onSelect={onSelect} />
        ))}
      </div>

      {result?.watch_notes.length ? (
        <ul className="mt-4 space-y-1 text-xs leading-5 text-muted">
          {result.watch_notes.slice(0, 3).map((note, index) => (
            <li key={`${index}-${note}`}>{note}</li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

function AiPickRow({ pick, onSelect }: { pick: AiStockPick; onSelect: (symbol: string) => void }) {
  return (
    <article className="rounded-md border border-line bg-control p-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-xs text-muted">#{pick.rank} {pick.industry}</div>
          <h3 className="mt-1 text-lg font-semibold">
            {pick.symbol}{pick.name ? ` ${pick.name}` : ""}
          </h3>
          <div className="mt-1 text-sm text-muted">
            最新價 {formatNumber(pick.latest_close)} / {biasLabel(pick.bias)} / 信心 {pick.confidence}
          </div>
        </div>
        <div className="text-right">
          <div className={`text-3xl font-bold ${scoreClass(pick.selection_score)}`}>{formatNumber(pick.selection_score, 0)}</div>
          <button
            className="focus-ring mt-2 rounded-md border border-line bg-panel px-3 py-1.5 text-sm font-semibold text-ink"
            type="button"
            onClick={() => onSelect(pick.symbol)}
          >
            看分析
          </button>
        </div>
      </div>
      <p className="mt-3 text-sm leading-6 text-muted">{pick.thesis}</p>
    </article>
  );
}

function AnalysisPanel({ analysis, loading }: { analysis: AnalysisResponse | null; loading: boolean }) {
  if (loading) {
    return (
      <section className="min-w-0 rounded-md border border-line bg-panel p-4">
        <EmptyState title="正在更新分析" detail="讀取個股、風險燈號和停利停損資訊。" />
      </section>
    );
  }

  if (!analysis) {
    return (
      <section className="min-w-0 rounded-md border border-line bg-panel p-4">
        <EmptyState title="尚無個股分析" detail="輸入股票代號後按更新。" />
      </section>
    );
  }

  const strategy = analysis.strategy_judgement;
  const close = analysis.technical.latest_close;
  const dataSourceCount = Object.values(analysis.data_sources).filter((source) => source === "sample" || source === "unknown").length;

  return (
    <section className="min-w-0 rounded-md border border-line bg-panel p-4">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <div className="text-sm text-muted">{analysis.analysis_date}</div>
          <h2 className="mt-1 text-2xl font-semibold">
            {analysis.symbol}{analysis.name ? ` ${analysis.name}` : ""}
          </h2>
          <p className="mt-2 text-sm leading-6 text-muted">{analysis.decision_plan.action}</p>
        </div>
        <div className="text-left md:text-right">
          <div className={`text-5xl font-bold ${scoreClass(analysis.adjusted_score)}`}>
            {formatNumber(analysis.adjusted_score, 0)}
          </div>
          <div className="mt-1 text-lg font-semibold">{analysis.recommendation}</div>
        </div>
      </div>

      <div className="mt-4 grid gap-2 sm:grid-cols-4">
        <StatusTile label="最新價" value={formatNumber(close)} />
        <StatusTile label="MA20" value={formatNumber(analysis.technical.ma.ma20)} />
        <StatusTile label="RSI14" value={formatNumber(analysis.technical.rsi.rsi14)} />
        <StatusTile label="ATR 停損" value={formatNumber(analysis.stop_loss.atr_stop)} tone="warn" />
      </div>

      <div className="mt-4">
        <RiskLightBadges lights={analysis.risk_lights} />
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-2">
        <SimplePanel title="AI 判斷" tone={stanceTone(strategy.stance)}>
          <div className="text-base font-semibold">{strategy.headline}</div>
          <p className="mt-2 text-sm leading-6">{strategy.action}</p>
          <div className="mt-3 grid grid-cols-2 gap-2">
            <StatusTile label="時機分數" value={formatNumber(strategy.timing_score, 0)} tone={stanceTone(strategy.stance)} />
            <StatusTile label="策略" value={stanceLabel(strategy.stance)} tone={stanceTone(strategy.stance)} />
          </div>
        </SimplePanel>
        <SimplePanel title="資料來源" tone={dataSourceCount >= 2 ? "warn" : "neutral"}>
          <div className="grid grid-cols-2 gap-2 text-sm">
            {Object.entries(analysis.data_sources).map(([key, source]) => (
              <div key={key} className="rounded-md border border-line bg-control px-3 py-2">
                <div className="text-xs text-muted">{sourceLabel(key)}</div>
                <div className="mt-1 font-semibold">{source}</div>
              </div>
            ))}
          </div>
        </SimplePanel>
      </div>
    </section>
  );
}

function WatchlistPanel({
  items,
  symbols,
  onSelect
}: {
  items: WatchlistItem[];
  symbols: string[];
  onSelect: (symbol: string) => void;
}) {
  const display = items.length ? items.map((item) => item.symbol) : symbols;
  return (
    <section className="min-w-0 rounded-md border border-line bg-panel p-4">
      <h2 className="text-lg font-semibold">自選股</h2>
      <p className="mt-1 text-sm text-muted">這份清單同時用於 AI 盤中掃描。</p>
      <div className="mt-3 flex flex-wrap gap-2">
        {display.map((item) => (
          <button
            key={item}
            className="focus-ring rounded-md border border-line bg-control px-3 py-2 text-sm font-semibold text-ink"
            type="button"
            onClick={() => onSelect(item)}
          >
            {item}
          </button>
        ))}
        {!display.length && <span className="text-sm text-muted">尚未建立自選股。</span>}
      </div>
    </section>
  );
}

function PositionPanel({
  positions,
  onSelect
}: {
  positions: PositionItem[];
  onSelect: (symbol: string) => void;
}) {
  return (
    <section className="min-w-0 rounded-md border border-line bg-panel p-4">
      <div>
        <h2 className="text-lg font-semibold">持倉</h2>
        <p className="mt-1 text-sm text-muted">點選載入後，可在上方調整買進價、最高價和股數。</p>
      </div>
      <div className="mt-3 overflow-x-auto">
        <table className="w-full min-w-[540px] border-collapse text-left text-sm">
          <thead className="border-b border-line text-xs text-muted">
            <tr>
              <th className="py-2 pr-3 font-semibold">股票</th>
              <th className="py-2 pr-3 font-semibold">買進價</th>
              <th className="py-2 pr-3 font-semibold">股數</th>
              <th className="py-2 pr-3 font-semibold">最高價</th>
              <th className="py-2 pr-3 font-semibold">操作</th>
            </tr>
          </thead>
          <tbody>
            {positions.map((item) => (
              <tr key={item.id} className="border-b border-line last:border-b-0">
                <td className="py-3 pr-3 font-semibold">{item.symbol}</td>
                <td className="py-3 pr-3">{formatNumber(item.entry_price)}</td>
                <td className="py-3 pr-3">{formatNumber(item.quantity, 0)}</td>
                <td className="py-3 pr-3">{formatNumber(item.highest_price)}</td>
                <td className="py-3 pr-3">
                  <button
                    className="focus-ring rounded-md border border-line bg-control px-3 py-1.5 font-semibold text-ink"
                    type="button"
                    onClick={() => onSelect(item.symbol)}
                  >
                    載入
                  </button>
                </td>
              </tr>
            ))}
            {!positions.length && (
              <tr>
                <td className="py-6 text-center text-muted" colSpan={5}>
                  目前沒有開放持倉。
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function ThemeToggle({ theme, onChange }: { theme: Theme; onChange: (theme: Theme) => void }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-sm text-muted">主題</span>
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
            {item === "light" ? "亮色" : "暗色"}
          </button>
        ))}
      </div>
    </div>
  );
}

function StatusTile({ label, value, tone = "neutral" }: { label: string; value: string; tone?: Tone }) {
  return (
    <div className={`rounded-md border p-3 ${toneClass(tone)}`}>
      <div className="text-xs text-muted">{label}</div>
      <div className="mt-1 text-base font-semibold leading-6">{value}</div>
    </div>
  );
}

function SimplePanel({ title, tone, children }: { title: string; tone: Tone; children: ReactNode }) {
  return (
    <section className={`rounded-md border p-3 ${toneClass(tone)}`}>
      <h3 className="text-sm font-semibold">{title}</h3>
      <div className="mt-2">{children}</div>
    </section>
  );
}

function Notice({ tone, children }: { tone: Tone; children: ReactNode }) {
  return <div className={`mt-3 rounded-md border p-3 text-sm ${toneClass(tone)}`}>{children}</div>;
}

function EmptyState({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="rounded-md border border-line bg-control p-4">
      <div className="font-semibold">{title}</div>
      <p className="mt-1 text-sm text-muted">{detail}</p>
    </div>
  );
}

function isDashboardView(value: string | null): value is DashboardView {
  return DASHBOARD_VIEWS.some((item) => item.id === value);
}

function parseSymbols(value: string) {
  const seen = new Set<string>();
  return value
    .split(/[,\s，、]+/)
    .map(normalizeSymbol)
    .filter((item) => {
      if (!item || seen.has(item)) return false;
      seen.add(item);
      return true;
    })
    .slice(0, 30);
}

function normalizeSymbol(value: string) {
  return value.toUpperCase().replace(/[^A-Z0-9.^-]/g, "").trim();
}

function parsePositiveNumber(value: string) {
  if (!value.trim()) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

function parseNonNegativeNumber(value: string) {
  if (!value.trim()) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
}

function readError(value: unknown, fallback: string) {
  return value instanceof Error ? value.message : fallback;
}

function toneClass(tone: Tone) {
  if (tone === "gain") return "border-gain/50 bg-gain/10 text-gain";
  if (tone === "warn") return "border-warn/50 bg-warn/10 text-warn";
  if (tone === "loss") return "border-loss/50 bg-loss/10 text-loss";
  return "border-line bg-panel text-ink";
}

function lightTone(light: Light): Tone {
  if (light === "green") return "gain";
  if (light === "red") return "loss";
  return "warn";
}

function stanceTone(stance: AnalysisResponse["strategy_judgement"]["stance"]): Tone {
  if (stance === "prepare_entry") return "gain";
  if (stance === "reduce_risk") return "loss";
  if (stance === "hold_steady") return "warn";
  return "neutral";
}

function biasLabel(bias: AiStockPick["bias"]) {
  if (bias === "bullish") return "偏多";
  if (bias === "bearish") return "偏空";
  return "中性";
}

function stanceLabel(stance: AnalysisResponse["strategy_judgement"]["stance"]) {
  const labels: Record<AnalysisResponse["strategy_judgement"]["stance"], string> = {
    prepare_entry: "準備進場",
    hold_steady: "續抱觀察",
    wait: "等待確認",
    reduce_risk: "降低風險"
  };
  return labels[stance];
}

function lightLabel(light: Light) {
  if (light === "green") return "綠燈";
  if (light === "red") return "紅燈";
  return "黃燈";
}

function sourceLabel(key: string) {
  const labels: Record<string, string> = {
    price: "價格",
    institutional: "法人",
    margin: "融資券",
    fundamental: "基本面",
    shareholding: "股權",
    news: "新聞"
  };
  return labels[key] ?? key;
}

function formatDateTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-TW", {
    timeZone: "Asia/Taipei",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit"
  });
}

function formatTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleTimeString("zh-TW", {
    timeZone: "Asia/Taipei",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit"
  });
}

function formatDuration(seconds: number) {
  if (seconds < 60) return `${seconds} 秒`;
  return `${Math.round(seconds / 60)} 分鐘`;
}
