"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ChartPanel } from "@/components/chart-panel";
import {
  closePosition,
  createMarketScan,
  createWatchlistItem,
  deleteWatchlistItem,
  fetchAnalysis,
  fetchChart,
  fetchLatestMarketScan,
  fetchMarketOverview,
  fetchPositionDecisions,
  fetchWatchlist,
  savePosition
} from "@/lib/api";
import { formatGateStatus, formatNumber, formatResearchStance } from "@/lib/format";
import {
  MARKET_SCAN_STATUS_OPTIONS,
  breakoutStatusLabel,
  breakoutStatusTone,
  candidateStatusDescription,
  candidateStatusLabel,
  candidateStatusTone,
  hasTrustedSource,
  sourceQualityLabel,
  universeSourceLabel
} from "@/lib/market-scan";
import {
  buildFundamentalMetrics,
  buildResearchSummary,
  buildTimingMetrics,
  buildTodayActionPlan,
  buildValuationMetrics,
  hasTrustedFundamentalData,
  hasTrustedPriceData
} from "@/lib/research-metrics";
import { displayStockName, knownStockName } from "@/lib/stock-display";
import type {
  AnalysisResponse,
  CandidateStatus,
  ChartResponse,
  GateStatus,
  Light,
  MarketOverviewResponse,
  MarketRefreshInfo,
  MarketScanCandidate,
  MarketScanResponse,
  PositionDecisionItem,
  PositionFutureOutlook,
  WatchlistItem
} from "@/lib/types";

type ViewKey = "command" | "positions" | "research" | "scanner" | "quality";
type Theme = "light" | "dark";
type Tone = "gain" | "warn" | "loss" | "neutral";

type PositionForm = {
  entryDate: string;
  entryPrice: string;
  highestPrice: string;
  quantity: string;
  symbol: string;
};

type SourceRow = {
  key: string;
  label: string;
  source: string;
  trusted: boolean;
  detail: string;
};

type ExecutionItem = {
  action: string;
  detail: string;
  label: string;
  tone: Tone;
};

type PositionSummary = {
  addCount: number;
  hasMarketValue: boolean;
  holdCount: number;
  marketValue: number | null;
  reduceCount: number;
  sellCount: number;
  totalCost: number;
  totalPnl: number | null;
  totalPnlPercent: number | null;
  watchCount: number;
};

type MenuItem = {
  key: ViewKey;
  label: string;
  icon: IconName;
  description: string;
};

type PlotTrace = Record<string, unknown> & {
  close?: unknown;
  name?: string;
  open?: unknown;
  type?: string;
  x?: unknown;
  y?: unknown;
};

type PlotlyBinaryArray = {
  bdata?: string;
  dtype?: string;
};

const DEFAULT_SYMBOL = "2330";
const DEFAULT_POSITION_FORM: PositionForm = {
  entryDate: "",
  entryPrice: "",
  highestPrice: "",
  quantity: "",
  symbol: ""
};

const NAV_ITEMS: MenuItem[] = [
  { key: "command", label: "今日決策", icon: "home", description: "先看今天要做什麼" },
  { key: "positions", label: "持股總覽", icon: "briefcase", description: "續抱、減碼、加碼" },
  { key: "research", label: "選股研究", icon: "search", description: "基本面到 K 線" },
  { key: "scanner", label: "市場候選", icon: "radar", description: "掃描但不追高" },
  { key: "quality", label: "資料品質", icon: "shield", description: "先確認能不能信" }
];

const SOURCE_LABELS: Array<{ key: string; kind: string; label: string }> = [
  { key: "price", kind: "price", label: "價格 / 日 K" },
  { key: "fundamental", kind: "fundamental", label: "基本面 / 營收" },
  { key: "news", kind: "news", label: "重大新聞 / 政治" },
  { key: "institutional", kind: "institutional", label: "法人" },
  { key: "margin", kind: "margin", label: "融資券" },
  { key: "shareholding", kind: "shareholding", label: "集保籌碼" }
];

const THEME_STORAGE_KEY = "stockai-theme";

export function Dashboard() {
  const [activeView, setActiveView] = useState<ViewKey>("command");
  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null);
  const [chart, setChart] = useState<ChartResponse | null>(null);
  const [marketOverview, setMarketOverview] = useState<MarketOverviewResponse | null>(null);
  const [marketScan, setMarketScan] = useState<MarketScanResponse | null>(null);
  const [positionDecisions, setPositionDecisions] = useState<PositionDecisionItem[]>([]);
  const [positionForm, setPositionForm] = useState<PositionForm>(DEFAULT_POSITION_FORM);
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [selectedSymbol, setSelectedSymbol] = useState(DEFAULT_SYMBOL);
  const [symbolDraft, setSymbolDraft] = useState(DEFAULT_SYMBOL);
  const [theme, setTheme] = useState<Theme>(() => {
    if (typeof window === "undefined") return "dark";
    const savedTheme = window.localStorage.getItem(THEME_STORAGE_KEY);
    return savedTheme === "light" || savedTheme === "dark" ? savedTheme : "dark";
  });
  const [bootLoading, setBootLoading] = useState(false);
  const [researchLoading, setResearchLoading] = useState(false);
  const [positionsLoading, setPositionsLoading] = useState(false);
  const [scanLoading, setScanLoading] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const researchRequestRef = useRef(0);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  }, [theme]);

  const refreshShell = useCallback(async () => {
    setBootLoading(true);
    const [overviewResult, scanResult, positionsResult, watchlistResult] = await Promise.allSettled([
      fetchMarketOverview(),
      fetchLatestMarketScan(),
      fetchPositionDecisions("open"),
      fetchWatchlist()
    ]);

    if (overviewResult.status === "fulfilled") setMarketOverview(overviewResult.value);
    if (scanResult.status === "fulfilled") setMarketScan(scanResult.value);
    if (positionsResult.status === "fulfilled") setPositionDecisions(positionsResult.value);
    if (watchlistResult.status === "fulfilled") setWatchlist(watchlistResult.value);

    const failures = [overviewResult, scanResult, positionsResult, watchlistResult].filter((item) => item.status === "rejected");
    if (failures.length) {
      setNotice("有些資料暫時沒有同步完成；畫面會保留已取得的資料，不能把缺口當成結論。");
    }
    setBootLoading(false);
  }, []);

  const loadResearch = useCallback(async (symbolInput: string, nextView?: ViewKey) => {
    const symbol = normalizeSymbol(symbolInput);
    if (!symbol) {
      setNotice("請輸入有效股票代碼。");
      return;
    }

    const requestId = researchRequestRef.current + 1;
    researchRequestRef.current = requestId;
    setSelectedSymbol(symbol);
    setSymbolDraft(symbol);
    if (nextView) setActiveView(nextView);
    setResearchLoading(true);
    setNotice(null);

    const [analysisResult, chartResult] = await Promise.allSettled([
      fetchAnalysis(symbol, { wait: true }),
      fetchChart(symbol, "1y")
    ]);
    if (researchRequestRef.current !== requestId) return;

    if (analysisResult.status === "fulfilled") {
      setAnalysis(analysisResult.value);
    } else {
      setAnalysis(null);
      setNotice(`無法完成 ${symbol} 分析；請先檢查 API 或資料來源。`);
    }

    if (chartResult.status === "fulfilled") {
      setChart(chartResult.value);
    } else {
      setChart(null);
      setNotice((current) => current ?? `無法取得 ${symbol} K 線圖；先不要判斷支撐與壓力。`);
    }

    setResearchLoading(false);
  }, []);

  useEffect(() => {
    void refreshShell();
    void loadResearch(DEFAULT_SYMBOL);
  }, [loadResearch, refreshShell]);

  const sourceRows = useMemo(() => buildSourceRows(analysis), [analysis]);
  const dataQuality = useMemo(() => buildDataQuality(sourceRows), [sourceRows]);
  const researchSummary = useMemo(() => buildResearchSummary(analysis), [analysis]);
  const todayPlan = useMemo(() => buildTodayActionPlan(analysis), [analysis]);
  const positionSummary = useMemo(() => summarizePositions(positionDecisions), [positionDecisions]);
  const selectedName = displayStockName(selectedSymbol, analysis?.name ?? null);
  const refresh = marketOverview?.risk.refresh ?? analysis?.refresh ?? null;

  const handleRefreshAll = useCallback(async () => {
    await Promise.all([refreshShell(), loadResearch(selectedSymbol)]);
  }, [loadResearch, refreshShell, selectedSymbol]);

  const handleOpenSymbol = useCallback(
    (symbol: string, nextView: ViewKey = "research") => {
      void loadResearch(symbol, nextView);
    },
    [loadResearch]
  );

  const handleSavePosition = useCallback(async () => {
    const symbol = normalizeSymbol(positionForm.symbol || selectedSymbol);
    const entryPrice = parsePositiveNumber(positionForm.entryPrice);
    const quantity = parsePositiveNumber(positionForm.quantity);
    const highestPrice = parseOptionalPositiveNumber(positionForm.highestPrice);

    if (!symbol || entryPrice === null || quantity === null) {
      setNotice("庫存至少需要股票代碼、均價與股數，否則無法判斷損益與部位風險。");
      return;
    }

    setPositionsLoading(true);
    setNotice(null);
    try {
      await savePosition({
        symbol,
        entry_price: entryPrice,
        quantity,
        highest_price: highestPrice,
        entry_date: positionForm.entryDate || null
      });
      const decisions = await fetchPositionDecisions("open");
      setPositionDecisions(decisions);
      setPositionForm(DEFAULT_POSITION_FORM);
      setActiveView("positions");
      setNotice(`${symbol} 已加入庫存，決策卡已重新計算。`);
    } catch {
      setNotice("庫存儲存失敗；請確認 API 正常後再試一次。");
    } finally {
      setPositionsLoading(false);
    }
  }, [positionForm, selectedSymbol]);

  const handleClosePosition = useCallback(async (id: number, symbol: string) => {
    setPositionsLoading(true);
    try {
      await closePosition(id);
      const decisions = await fetchPositionDecisions("open");
      setPositionDecisions(decisions);
      setNotice(`${symbol} 已標記為結清。`);
    } catch {
      setNotice("結清庫存失敗；資料未變更。");
    } finally {
      setPositionsLoading(false);
    }
  }, []);

  const handleCreateScan = useCallback(async () => {
    setScanLoading(true);
    setNotice(null);
    try {
      const scan = await createMarketScan({ limit: 50, max_symbols: 120 });
      setMarketScan(scan);
      setActiveView("scanner");
      setNotice("市場候選已重新掃描；請先看資料範圍與低信任警示，再看候選。");
    } catch {
      setNotice("市場掃描失敗；先使用上次快取，不要把候選清單當成最新全市場結果。");
    } finally {
      setScanLoading(false);
    }
  }, []);

  const handleAddWatchlist = useCallback(async () => {
    const symbol = normalizeSymbol(selectedSymbol);
    if (!symbol) return;
    try {
      const item = await createWatchlistItem(symbol);
      setWatchlist((current) => mergeWatchlist(current, item));
      setNotice(`${symbol} 已加入觀察清單。`);
    } catch {
      setNotice("觀察清單暫時無法寫入，但目前研究畫面仍可使用。");
    }
  }, [selectedSymbol]);

  const handleDeleteWatchlist = useCallback(async (item: WatchlistItem) => {
    try {
      await deleteWatchlistItem(item.id);
      setWatchlist((current) => current.filter((row) => row.id !== item.id));
      setNotice(`${item.symbol} 已從觀察清單移除。`);
    } catch {
      setNotice("移除觀察清單失敗；資料未變更。");
    }
  }, []);

  const renderActiveView = () => {
    if (activeView === "positions") {
      return (
        <PositionsView
          decisions={positionDecisions}
          form={positionForm}
          loading={positionsLoading}
          summary={positionSummary}
          onClose={handleClosePosition}
          onFormChange={(patch) => setPositionForm((current) => ({ ...current, ...patch }))}
          onRefresh={async () => {
            setPositionsLoading(true);
            try {
              setPositionDecisions(await fetchPositionDecisions("open"));
            } finally {
              setPositionsLoading(false);
            }
          }}
          onSave={handleSavePosition}
          onSelectSymbol={handleOpenSymbol}
        />
      );
    }

    if (activeView === "research") {
      return (
        <ResearchView
          analysis={analysis}
          chart={chart}
          loading={researchLoading}
          selectedName={selectedName}
          selectedSymbol={selectedSymbol}
          sourceRows={sourceRows}
          symbolDraft={symbolDraft}
          theme={theme}
          todayPlan={todayPlan}
          watchlist={watchlist}
          onAddWatchlist={handleAddWatchlist}
          onDraftChange={setSymbolDraft}
          onOpenQuality={() => setActiveView("quality")}
          onRefresh={() => void loadResearch(selectedSymbol)}
          onSubmit={(symbol) => void loadResearch(symbol, "research")}
        />
      );
    }

    if (activeView === "scanner") {
      return (
        <ScannerView
          loading={scanLoading}
          scan={marketScan}
          onOpenSymbol={handleOpenSymbol}
          onRunScan={handleCreateScan}
        />
      );
    }

    if (activeView === "quality") {
      return (
        <DataQualityView
          analysis={analysis}
          dataQuality={dataQuality}
          marketOverview={marketOverview}
          marketScan={marketScan}
          selectedName={selectedName}
          selectedSymbol={selectedSymbol}
          sourceRows={sourceRows}
          onRefresh={handleRefreshAll}
        />
      );
    }

    return (
      <CommandCenter
        analysis={analysis}
        bootLoading={bootLoading}
        dataQuality={dataQuality}
        marketOverview={marketOverview}
        marketScan={marketScan}
        positionDecisions={positionDecisions}
        positionSummary={positionSummary}
        researchLoading={researchLoading}
        selectedName={selectedName}
        selectedSymbol={selectedSymbol}
        sourceRows={sourceRows}
        todayPlan={todayPlan}
        onOpenSymbol={handleOpenSymbol}
        onOpenView={setActiveView}
        onRefresh={handleRefreshAll}
        onRunScan={handleCreateScan}
      />
    );
  };

  return (
    <div className="stockai-app stockai-shell min-h-screen bg-[#f3f6fa] pb-24 text-[#0c1b2a] lg:pb-0">
      <div className="flex min-h-screen">
        <Sidebar
          activeView={activeView}
          selectedSymbol={selectedSymbol}
          watchlist={watchlist}
          onDeleteWatchlist={handleDeleteWatchlist}
          onNavigate={setActiveView}
          onOpenSymbol={handleOpenSymbol}
        />
        <div className="flex min-w-0 flex-1 flex-col">
          <TopBar
            dataQuality={dataQuality}
            loading={bootLoading || researchLoading}
            marketOverview={marketOverview}
            refresh={refresh}
            theme={theme}
            onRefresh={() => void handleRefreshAll()}
            onToggleTheme={() => setTheme((current) => (current === "light" ? "dark" : "light"))}
          />
          <main className="stockai-content grid flex-1 gap-4 px-4 py-4 xl:grid-cols-[minmax(0,1fr)_400px] 2xl:grid-cols-[minmax(0,1fr)_460px]">
            <section className="min-w-0 space-y-4">
              {notice ? <Notice message={notice} onDismiss={() => setNotice(null)} /> : null}
              {renderActiveView()}
            </section>
            <SelectedStockPanel
              analysis={analysis}
              chart={chart}
              dataQuality={dataQuality}
              loading={researchLoading}
              selectedName={selectedName}
              selectedSymbol={selectedSymbol}
              sourceRows={sourceRows}
              theme={theme}
              todayPlan={todayPlan}
              onOpenPositions={() => setActiveView("positions")}
              onOpenQuality={() => setActiveView("quality")}
              onOpenResearch={() => setActiveView("research")}
            />
          </main>
        </div>
      </div>
      <MobileNav activeView={activeView} onNavigate={setActiveView} />
    </div>
  );
}

function Sidebar({
  activeView,
  selectedSymbol,
  watchlist,
  onDeleteWatchlist,
  onNavigate,
  onOpenSymbol
}: {
  activeView: ViewKey;
  selectedSymbol: string;
  watchlist: WatchlistItem[];
  onDeleteWatchlist: (item: WatchlistItem) => void;
  onNavigate: (view: ViewKey) => void;
  onOpenSymbol: (symbol: string, view?: ViewKey) => void;
}) {
  return (
    <aside className="stockai-sidebar sticky top-0 hidden h-screen w-[236px] shrink-0 flex-col border-r border-[#0d2942] bg-[#08233a] text-white lg:flex">
      <div className="flex h-[58px] items-center gap-3 border-b border-white/10 px-4">
        <LogoMark />
        <div>
          <div className="text-[17px] font-black tracking-normal">台股決策助手</div>
          <div className="text-[11px] font-bold text-[#9fc3df]">研究版</div>
        </div>
      </div>
      <nav className="space-y-1 p-3">
        {NAV_ITEMS.map((item) => (
          <button
            key={item.key}
            className={`flex w-full items-center gap-3 rounded-lg px-3 py-3 text-left transition ${
              activeView === item.key ? "bg-[#1e6aa5] text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.18)]" : "text-[#d8e9f6] hover:bg-white/10"
            }`}
            type="button"
            onClick={() => onNavigate(item.key)}
          >
            <Icon className="h-5 w-5 shrink-0" name={item.icon} />
            <span>
              <span className="block text-[14px] font-black">{item.label}</span>
              <span className="block text-[11px] font-semibold text-[#9fc3df]">{item.description}</span>
            </span>
          </button>
        ))}
      </nav>
      <div className="mt-auto p-3">
        <div className="rounded-lg border border-white/15 bg-white/5 p-3">
          <div className="flex items-center gap-2 text-sm font-black">
            <Icon className="h-4 w-4 text-[#f9c74f]" name="star" />
            我的觀察清單
          </div>
          <div className="mt-3 space-y-1">
            {(watchlist.length ? watchlist.slice(0, 7) : [{ id: -1, symbol: selectedSymbol, name: knownStockName(selectedSymbol), created_at: "" } as WatchlistItem]).map((item) => (
              <div key={`${item.id}-${item.symbol}`} className="group flex items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-white/10">
                <button className="min-w-0 flex-1 truncate text-left font-semibold" type="button" onClick={() => onOpenSymbol(item.symbol, "research")}>
                  {item.symbol} <span className="text-[#bed6ea]">{displayStockName(item.symbol, item.name)}</span>
                </button>
                {item.id > 0 ? (
                  <button
                    aria-label={`移除 ${item.symbol}`}
                    className="rounded p-1 text-[#9fc3df] opacity-0 hover:bg-white/10 group-hover:opacity-100"
                    type="button"
                    onClick={() => onDeleteWatchlist(item)}
                  >
                    <Icon className="h-3.5 w-3.5" name="x" />
                  </button>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      </div>
    </aside>
  );
}

function MobileNav({ activeView, onNavigate }: { activeView: ViewKey; onNavigate: (view: ViewKey) => void }) {
  const items = NAV_ITEMS.slice(0, 5);
  return (
    <nav className="fixed inset-x-0 bottom-0 z-30 border-t border-[#cbd7e2] bg-white/95 px-2 pb-[env(safe-area-inset-bottom)] pt-2 shadow-[0_-8px_22px_rgba(15,33,52,0.12)] backdrop-blur lg:hidden" aria-label="主要功能">
      <div className="grid grid-cols-5 gap-1">
        {items.map((item) => (
          <button
            key={item.key}
            className={`flex min-h-[58px] flex-col items-center justify-center gap-1 rounded-lg px-1 text-[11px] font-black ${
              activeView === item.key ? "bg-[#1e6aa5] text-white" : "text-[#35506a]"
            }`}
            type="button"
            onClick={() => onNavigate(item.key)}
          >
            <Icon className="h-5 w-5" name={item.icon} />
            <span className="leading-none">{item.label.replace("總覽", "")}</span>
          </button>
        ))}
      </div>
    </nav>
  );
}

function TopBar({
  dataQuality,
  loading,
  marketOverview,
  refresh,
  theme,
  onRefresh,
  onToggleTheme
}: {
  dataQuality: ReturnType<typeof buildDataQuality>;
  loading: boolean;
  marketOverview: MarketOverviewResponse | null;
  refresh: MarketRefreshInfo | null;
  theme: Theme;
  onRefresh: () => void;
  onToggleTheme: () => void;
}) {
  const quote = marketOverview?.taiex_quote;
  const marketTone = quote ? quoteTone(quote.change_percent) : marketLightTone(marketOverview?.risk.lights.composite);
  return (
    <header className="stockai-topbar sticky top-0 z-20 flex min-h-[58px] items-center gap-3 border-b border-[#d8e1ea] bg-white/95 px-4 backdrop-blur">
      <div className="flex min-w-0 flex-1 flex-wrap items-center gap-x-6 gap-y-1 text-sm">
        <TickerValue label="加權指數" tone={marketTone} value={quote ? formatNumber(quote.value, 2) : "-"} subValue={quote ? formatSignedPercent(quote.change_percent) : marketLightLabel(marketOverview?.risk.lights.composite)} />
        <TickerValue label="成交量(億)" value={quote?.volume ? formatCompactNumber(quote.volume) : "-"} />
        <TickerValue label="市場風險" tone={marketLightTone(marketOverview?.risk.lights.composite)} value={marketOverview?.risk.score !== undefined ? `${formatNumber(marketOverview.risk.score, 0)}` : "-"} subValue={marketLightLabel(marketOverview?.risk.lights.composite)} />
      </div>
      <div className="hidden items-center gap-2 text-xs font-bold text-[#64748b] md:flex">
        <Icon className="h-4 w-4" name="clock" />
        <span>{refresh?.label ?? "等待更新"}</span>
        <span className="h-4 w-px bg-[#d8e1ea]" />
        <span>資料品質</span>
        <span className={qualityBadgeClass(dataQuality.tone)}>{dataQuality.label}</span>
      </div>
      <button className="focus-ring h-9 rounded-lg border border-[#cbd7e2] bg-[#fbfdff] px-3 text-sm font-black text-[#1f3349] hover:bg-[#eef4f8]" type="button" onClick={onToggleTheme}>
        {theme === "light" ? "深色" : "淺色"}
      </button>
      <button className="focus-ring h-9 rounded-lg border border-[#cbd7e2] bg-[#fbfdff] px-3 text-sm font-black text-[#1f3349] hover:bg-[#eef4f8]" type="button" onClick={onRefresh}>
        {loading ? "同步中" : "重新整理"}
      </button>
    </header>
  );
}

function CommandCenter({
  analysis,
  bootLoading,
  dataQuality,
  marketOverview,
  marketScan,
  positionDecisions,
  positionSummary,
  researchLoading,
  selectedName,
  selectedSymbol,
  sourceRows,
  todayPlan,
  onOpenSymbol,
  onOpenView,
  onRefresh,
  onRunScan
}: {
  analysis: AnalysisResponse | null;
  bootLoading: boolean;
  dataQuality: ReturnType<typeof buildDataQuality>;
  marketOverview: MarketOverviewResponse | null;
  marketScan: MarketScanResponse | null;
  positionDecisions: PositionDecisionItem[];
  positionSummary: PositionSummary;
  researchLoading: boolean;
  selectedName: string;
  selectedSymbol: string;
  sourceRows: SourceRow[];
  todayPlan: ReturnType<typeof buildTodayActionPlan>;
  onOpenSymbol: (symbol: string, view?: ViewKey) => void;
  onOpenView: (view: ViewKey) => void;
  onRefresh: () => void;
  onRunScan: () => void;
}) {
  const risk = marketOverview?.risk ?? null;
  const candidateCount = marketScan?.top_candidates.filter((item) => item.candidate_status === "qualified_research" || item.candidate_status === "wait_price").length ?? 0;
  const priorityPositions = [...positionDecisions].sort(comparePositionUrgency).slice(0, 4);
  const marketReasons = risk?.reasons.slice(0, 3) ?? ["等待大盤資料同步。"];
  const scanScope = universeSourceLabel(marketScan?.universe_source);
  const executionItems = buildExecutionItems({
    candidateCount,
    dataQuality,
    marketScan,
    positionSummary,
    priorityPositions,
    risk,
    todayPlan
  });

  return (
    <div className="space-y-4">
      <section className="stockai-panel rounded-lg border border-[#d7e0e8] bg-white p-5 shadow-[0_8px_22px_rgba(15,33,52,0.07)]">
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div>
            <h1 className="text-[28px] font-black leading-tight text-[#0c1b2a]">今日決策中心</h1>
            <p className="mt-1 text-sm font-semibold text-[#526174]">先判斷可不可以相信資料，再判斷持股、候選與選定股票，不因分數或消息追高。</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button className="focus-ring inline-flex h-10 items-center gap-2 rounded-lg border border-[#cbd7e2] bg-[#fbfdff] px-4 text-sm font-black text-[#1f3349] hover:bg-[#eef4f8]" type="button" onClick={onRefresh}>
              <Icon className="h-4 w-4" name="refresh" />
              {bootLoading || researchLoading ? "同步中" : "同步全部"}
            </button>
            <button className="focus-ring inline-flex h-10 items-center gap-2 rounded-lg bg-[#0f6b4f] px-4 text-sm font-black text-white hover:bg-[#0b5c43]" type="button" onClick={onRunScan}>
              <Icon className="h-4 w-4" name="radar" />
              掃描候選
            </button>
          </div>
        </div>
        <div className="mt-5 flex flex-col gap-3">
          <div className="order-2 grid gap-3 md:order-1 md:grid-cols-2 2xl:grid-cols-4">
            <MetricCard
              detail={positionSummary.totalPnlPercent === null ? "等待即時價格同步" : `總損益 ${formatSignedPercent(positionSummary.totalPnlPercent)}`}
              label="今日整體基調"
              tone={positionSummary.sellCount || positionSummary.reduceCount ? "loss" : positionSummary.addCount ? "gain" : "warn"}
              value={positionSummary.sellCount || positionSummary.reduceCount ? "先控風險" : positionSummary.addCount ? "可小幅研究" : "中性偏謹慎"}
            />
            <MetricCard
              detail={marketReasons[0] ?? "等待大盤理由"}
              label="市場風險分數"
              tone={marketLightTone(risk?.lights.composite)}
              value={risk?.score !== undefined ? `${formatNumber(risk.score, 0)} /100` : "-"}
            />
            <MetricCard
              detail={marketScan ? `${scanScope} · ${marketScan.completed_count}/${marketScan.universe_count}` : "尚未建立掃描快取"}
              label="可操作候選"
              tone={candidateCount > 0 ? "gain" : marketScan ? "warn" : "neutral"}
              value={marketScan ? `${candidateCount} 檔` : "未掃描"}
            />
            <MetricCard
              detail={`${dataQuality.trusted}/${dataQuality.total} 個核心來源可信`}
              label="資料品質總覽"
              tone={dataQuality.tone}
              value={dataQuality.label}
            />
          </div>
          <div className="order-1 md:order-2">
            <ExecutionPanel items={executionItems} />
          </div>
        </div>
      </section>

      <section className="grid gap-3 md:grid-cols-2 2xl:grid-cols-4">
        <PriorityCard
          actionLabel="檢視持股總覽"
          icon="briefcase"
          kicker="1"
          title="持股決策"
          tone={positionSummary.sellCount || positionSummary.reduceCount ? "loss" : "warn"}
          onAction={() => onOpenView("positions")}
        >
          <div className="space-y-2">
            {priorityPositions.length ? (
              priorityPositions.map((item) => (
                <CompactDecisionRow key={item.position.id} decision={item} onOpenSymbol={(symbol) => onOpenSymbol(symbol, "research")} />
              ))
            ) : (
              <EmptyLine text="尚未建立庫存；先輸入均價與股數，系統才有能力判斷續抱或減碼。" />
            )}
          </div>
        </PriorityCard>
        <PriorityCard actionLabel="檢視市場訊號" icon="activity" kicker="2" title="市場風險" tone={marketLightTone(risk?.lights.composite)} onAction={() => onOpenView("quality")}>
          <InfoList items={marketReasons} />
        </PriorityCard>
        <PriorityCard actionLabel="繼續研究" icon="search" kicker="3" title={`${selectedSymbol} ${selectedName}`} tone={todayPlan.tone} onAction={() => onOpenView("research")}>
          <div className="rounded-lg border border-[#d7e0e8] bg-[#fbfdff] p-3">
            <div className="text-sm font-black text-[#0c1b2a]">{todayPlan.headline}</div>
            <div className="mt-1 text-xs font-semibold leading-5 text-[#526174]">{todayPlan.primaryAction}</div>
          </div>
          <div className="mt-2 text-xs font-bold text-[#9a3412]">{todayPlan.noChase}</div>
        </PriorityCard>
        <PriorityCard actionLabel="檢視資料品質" icon="shield" kicker="4" title="資料品質" tone={dataQuality.tone} onAction={() => onOpenView("quality")}>
          <div className="space-y-2">
            {sourceRows.slice(0, 4).map((row) => (
              <SourceMiniRow key={row.key} row={row} />
            ))}
          </div>
        </PriorityCard>
      </section>

      <section className="grid gap-4 2xl:grid-cols-[1.1fr_0.9fr]">
        <Panel title="市場候選快照" action={<button className="text-sm font-black text-[#1d5f8f]" type="button" onClick={() => onOpenView("scanner")}>看完整候選</button>}>
          <CandidateSnapshot scan={marketScan} onOpenSymbol={onOpenSymbol} />
        </Panel>
        <Panel title="選定股票三關檢查" action={<button className="text-sm font-black text-[#1d5f8f]" type="button" onClick={() => onOpenView("research")}>打開研究</button>}>
          <GateSummary analysis={analysis} />
        </Panel>
      </section>
    </div>
  );
}

function SelectedStockPanel({
  analysis,
  chart,
  dataQuality,
  loading,
  selectedName,
  selectedSymbol,
  sourceRows,
  theme,
  todayPlan,
  onOpenPositions,
  onOpenQuality,
  onOpenResearch
}: {
  analysis: AnalysisResponse | null;
  chart: ChartResponse | null;
  dataQuality: ReturnType<typeof buildDataQuality>;
  loading: boolean;
  selectedName: string;
  selectedSymbol: string;
  sourceRows: SourceRow[];
  theme: Theme;
  todayPlan: ReturnType<typeof buildTodayActionPlan>;
  onOpenPositions: () => void;
  onOpenQuality: () => void;
  onOpenResearch: () => void;
}) {
  const latest = hasTrustedPriceData(analysis) ? analysis?.technical.latest_close ?? null : null;
  const summary = buildResearchSummary(analysis);
  const support = analysis?.kline_analysis.support_levels?.slice(0, 2) ?? [];
  const resistance = analysis?.kline_analysis.resistance_levels?.slice(0, 2) ?? [];

  return (
    <aside className="stockai-panel sticky top-[74px] h-fit min-w-0 rounded-lg border border-[#d7e0e8] bg-white p-4 shadow-[0_8px_22px_rgba(15,33,52,0.07)]">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <button className="text-[#9aa8b7]" type="button" aria-label="目前選定股票">
              <Icon className="h-5 w-5" name="star" />
            </button>
            <h2 className="text-xl font-black text-[#0c1b2a]">{selectedSymbol} {selectedName}</h2>
            <span className={qualityBadgeClass(dataQuality.tone)}>{dataQuality.label}</span>
          </div>
          <div className="mt-1 text-xs font-semibold text-[#64748b]">{analysis?.industry ?? "產業資料待補"} · {formatDateTime(analysis?.generated_at)}</div>
        </div>
        <button className="rounded-md p-1.5 text-[#64748b] hover:bg-[#eef4f8]" type="button" onClick={onOpenResearch} aria-label="打開研究">
          <Icon className="h-5 w-5" name="expand" />
        </button>
      </div>

      <div className="mt-4 flex items-end justify-between gap-3">
        <div>
          <div className="text-[40px] font-black leading-none text-[#0f7a48]">{latest === null ? "-" : formatNumber(latest, 2)}</div>
          <div className="mt-1 text-xs font-bold text-[#64748b]">最新可信價格</div>
        </div>
        <StatusPill tone={todayPlan.tone}>{todayPlan.label}</StatusPill>
      </div>

      <div className="mt-4">
        <MiniPriceChart chart={chart} loading={loading} theme={theme} />
      </div>

      <div className="mt-4 grid gap-2 md:grid-cols-2 xl:grid-cols-1 2xl:grid-cols-2">
        <LevelBox label="支撐" tone="gain" values={support} fallback={analysis?.timing_gate.support_zone ?? "等待 K 線"} />
        <LevelBox label="壓力 / 禁追" tone="loss" values={resistance} fallback={analysis?.timing_gate.no_chase_zone ?? todayPlan.noChase} />
      </div>

      <div className="mt-4 grid gap-2 md:grid-cols-3 xl:grid-cols-1 2xl:grid-cols-3">
        <GateMini label="基本面" status={analysis?.fundamental_gate.status ?? "unknown"} />
        <GateMini label="估值面" status={analysis?.valuation_gate.status ?? "unknown"} />
        <GateMini label="時機面" status={analysis?.timing_gate.status ?? "unknown"} />
      </div>

      <div className="mt-4 rounded-lg border border-[#d7e0e8] bg-[#fbfdff] p-3">
        <div className="text-sm font-black text-[#0c1b2a]">{todayPlan.headline}</div>
        <p className="mt-1 text-xs font-semibold leading-5 text-[#526174]">{todayPlan.detail}</p>
        <div className="mt-3 grid gap-2">
          <DisciplineLine icon="target" label="等待條件" value={todayPlan.waitFor} />
          <DisciplineLine icon="shield" label="失效條件" value={todayPlan.invalidation} />
          <DisciplineLine icon="alert" label="紀律提醒" value={summary.noChase} />
        </div>
      </div>

      <div className="mt-4 grid grid-cols-3 gap-2">
        <button className="focus-ring rounded-lg border border-[#cbd7e2] bg-[#fbfdff] px-3 py-2 text-sm font-black text-[#1f3349] hover:bg-[#eef4f8]" type="button" onClick={onOpenPositions}>持股</button>
        <button className="focus-ring rounded-lg bg-[#0f6b4f] px-3 py-2 text-sm font-black text-white hover:bg-[#0b5c43]" type="button" onClick={onOpenResearch}>研究</button>
        <button className="focus-ring rounded-lg border border-[#cbd7e2] bg-[#fbfdff] px-3 py-2 text-sm font-black text-[#1f3349] hover:bg-[#eef4f8]" type="button" onClick={onOpenQuality}>品質</button>
      </div>

      <div className="mt-4 space-y-2">
        {sourceRows.slice(0, 3).map((row) => (
          <SourceMiniRow key={row.key} row={row} />
        ))}
      </div>
    </aside>
  );
}

function PositionsView({
  decisions,
  form,
  loading,
  summary,
  onClose,
  onFormChange,
  onRefresh,
  onSave,
  onSelectSymbol
}: {
  decisions: PositionDecisionItem[];
  form: PositionForm;
  loading: boolean;
  summary: PositionSummary;
  onClose: (id: number, symbol: string) => void;
  onFormChange: (patch: Partial<PositionForm>) => void;
  onRefresh: () => void;
  onSave: () => void;
  onSelectSymbol: (symbol: string, view?: ViewKey) => void;
}) {
  return (
    <div className="space-y-4">
      <SectionHeader
        description="輸入均價與股數後，庫存卡會優先看重大新聞 / 政治、營收，再看價格與 K 線。"
        eyebrow="Holdings"
        title="持股總覽"
        actions={<button className="focus-ring rounded-lg border border-[#cbd7e2] bg-[#fbfdff] px-4 py-2 text-sm font-black text-[#1f3349] hover:bg-[#eef4f8]" type="button" onClick={onRefresh}>{loading ? "同步中" : "重新整理"}</button>}
      />
      <div className="grid gap-3 md:grid-cols-4">
        <MetricCard detail="已保存開放庫存" label="持股筆數" value={`${decisions.length}`} />
        <MetricCard detail="均價 × 股數" label="總成本" value={formatMoney(summary.totalCost)} />
        <MetricCard detail="可信價格同步後顯示" label="市值" value={summary.marketValue === null ? "-" : formatMoney(summary.marketValue)} />
        <MetricCard detail={summary.totalPnlPercent === null ? "等待價格資料" : formatSignedPercent(summary.totalPnlPercent)} label="未實現損益" tone={summary.totalPnl === null ? "neutral" : summary.totalPnl >= 0 ? "gain" : "loss"} value={summary.totalPnl === null ? "-" : formatSignedMoney(summary.totalPnl)} />
      </div>
      <Panel title="新增 / 更新庫存">
        <div className="grid gap-3 md:grid-cols-5">
          <PositionField label="股票代碼" placeholder="2330" value={form.symbol} onChange={(value) => onFormChange({ symbol: value })} />
          <PositionField label="均價" placeholder="例如 850" value={form.entryPrice} type="number" onChange={(value) => onFormChange({ entryPrice: value })} />
          <PositionField label="股數" placeholder="例如 1000" value={form.quantity} type="number" onChange={(value) => onFormChange({ quantity: value })} />
          <PositionField label="最高價" placeholder="可留空" value={form.highestPrice} type="number" onChange={(value) => onFormChange({ highestPrice: value })} />
          <PositionField label="買進日" value={form.entryDate} type="date" onChange={(value) => onFormChange({ entryDate: value })} />
        </div>
        <div className="mt-3 flex justify-end">
          <button className="focus-ring rounded-lg bg-[#0f6b4f] px-5 py-2.5 text-sm font-black text-white hover:bg-[#0b5c43]" type="button" onClick={onSave}>
            {loading ? "儲存中" : "儲存並重新判斷"}
          </button>
        </div>
      </Panel>
      <div className="grid gap-3">
        {decisions.length ? (
          [...decisions].sort(comparePositionUrgency).map((decision) => (
            <PositionDecisionCard key={decision.position.id} decision={decision} onClose={onClose} onSelectSymbol={onSelectSymbol} />
          ))
        ) : (
          <EmptyState
            icon="briefcase"
            title="還沒有庫存"
            detail="先輸入均價與股數。這個功能不是記帳，而是讓系統能判斷續抱、減碼、加碼或只觀察。"
          />
        )}
      </div>
    </div>
  );
}

function ResearchView({
  analysis,
  chart,
  loading,
  selectedName,
  selectedSymbol,
  sourceRows,
  symbolDraft,
  theme,
  todayPlan,
  watchlist,
  onAddWatchlist,
  onDraftChange,
  onOpenQuality,
  onRefresh,
  onSubmit
}: {
  analysis: AnalysisResponse | null;
  chart: ChartResponse | null;
  loading: boolean;
  selectedName: string;
  selectedSymbol: string;
  sourceRows: SourceRow[];
  symbolDraft: string;
  theme: Theme;
  todayPlan: ReturnType<typeof buildTodayActionPlan>;
  watchlist: WatchlistItem[];
  onAddWatchlist: () => void;
  onDraftChange: (value: string) => void;
  onOpenQuality: () => void;
  onRefresh: () => void;
  onSubmit: (symbol: string) => void;
}) {
  const summary = buildResearchSummary(analysis);
  const fundamentalMetrics = buildFundamentalMetrics(analysis);
  const valuationMetrics = buildValuationMetrics(analysis);
  const timingMetrics = buildTimingMetrics(analysis);
  const inWatchlist = watchlist.some((item) => normalizeSymbol(item.symbol) === normalizeSymbol(selectedSymbol));

  return (
    <div className="space-y-4">
      <SectionHeader
        description="一檔股票只問三件事：基本面值不值得研究、估值有沒有安全邊際、K 線時機能不能出手。"
        eyebrow="Research"
        title={`${selectedSymbol} ${selectedName}`}
        actions={
          <form className="flex flex-wrap gap-2" onSubmit={(event) => { event.preventDefault(); onSubmit(symbolDraft); }}>
            <input className="focus-ring h-10 w-28 rounded-lg border border-[#cbd7e2] bg-white px-3 text-sm font-black text-[#0c1b2a]" value={symbolDraft} onChange={(event) => onDraftChange(event.target.value)} />
            <button className="focus-ring h-10 rounded-lg bg-[#0f6b4f] px-4 text-sm font-black text-white hover:bg-[#0b5c43]" type="submit">{loading ? "分析中" : "分析"}</button>
            <button className="focus-ring h-10 rounded-lg border border-[#cbd7e2] bg-[#fbfdff] px-4 text-sm font-black text-[#1f3349] hover:bg-[#eef4f8]" type="button" onClick={onRefresh}>刷新</button>
            <button className="focus-ring h-10 rounded-lg border border-[#cbd7e2] bg-[#fbfdff] px-4 text-sm font-black text-[#1f3349] hover:bg-[#eef4f8]" type="button" onClick={onAddWatchlist}>{inWatchlist ? "已在觀察" : "加入觀察"}</button>
          </form>
        }
      />
      <div className="grid gap-4 2xl:grid-cols-[0.9fr_1.1fr]">
        <Panel title="今天的研究結論" action={<button className="text-sm font-black text-[#1d5f8f]" type="button" onClick={onOpenQuality}>資料品質</button>}>
          <div className="rounded-lg border border-[#d7e0e8] bg-[#fbfdff] p-4">
            <StatusPill tone={todayPlan.tone}>{todayPlan.label}</StatusPill>
            <h2 className="mt-3 text-2xl font-black text-[#0c1b2a]">{todayPlan.headline}</h2>
            <p className="mt-2 text-sm font-semibold leading-6 text-[#526174]">{todayPlan.detail}</p>
            <div className="mt-4 grid gap-2">
              <DisciplineLine icon="search" label="下一步" value={todayPlan.primaryAction} />
              <DisciplineLine icon="target" label="等待" value={todayPlan.waitFor} />
              <DisciplineLine icon="shield" label="失效" value={todayPlan.invalidation} />
              <DisciplineLine icon="alert" label="禁追" value={todayPlan.noChase} />
            </div>
          </div>
        </Panel>
        <Panel title="三關檢查">
          <div className="grid gap-3 md:grid-cols-3">
            <GateColumn title="基本面" status={analysis?.fundamental_gate.status ?? "unknown"} metrics={fundamentalMetrics} trusted={hasTrustedFundamentalData(analysis)} />
            <GateColumn title="估值面" status={analysis?.valuation_gate.status ?? "unknown"} metrics={valuationMetrics} trusted={hasTrustedFundamentalData(analysis)} />
            <GateColumn title="時機面" status={analysis?.timing_gate.status ?? "unknown"} metrics={timingMetrics} trusted={hasTrustedPriceData(analysis)} />
          </div>
        </Panel>
      </div>
      <Panel title="K 線與價格計畫">
        <div className="grid gap-4 2xl:grid-cols-[1fr_360px]">
          <ChartPanel chart={chart} latestPrice={analysis?.technical.latest_close} symbol={selectedSymbol} theme={theme} />
          <div className="space-y-3">
            <PricePlanCard analysis={analysis} />
            <KlineNotes analysis={analysis} />
            <PanelInset title="研究摘要">
              <div className="text-sm font-black text-[#0c1b2a]">{summary.headline}</div>
              <div className="mt-1 text-xs font-bold text-[#64748b]">週期：{summary.horizon}</div>
              <InfoList items={summary.nextActions} />
            </PanelInset>
          </div>
        </div>
      </Panel>
      <Panel title="理由、風險與資料來源">
        <div className="grid gap-4 xl:grid-cols-3">
          <PanelInset title="支持理由">
            <InfoList items={analysis?.reasons.slice(0, 5) ?? ["等待分析資料。"]} />
          </PanelInset>
          <PanelInset title="風險與阻擋">
            <InfoList items={[...(analysis?.risks.slice(0, 4) ?? []), ...(analysis?.research_decision.blockers.slice(0, 3) ?? [])].slice(0, 6)} fallback="暫無明確風險，但仍需看資料品質。" />
          </PanelInset>
          <PanelInset title="資料來源">
            <div className="space-y-2">
              {sourceRows.map((row) => <SourceMiniRow key={row.key} row={row} />)}
            </div>
          </PanelInset>
        </div>
      </Panel>
    </div>
  );
}

function ScannerView({
  loading,
  scan,
  onOpenSymbol,
  onRunScan
}: {
  loading: boolean;
  scan: MarketScanResponse | null;
  onOpenSymbol: (symbol: string, view?: ViewKey) => void;
  onRunScan: () => void;
}) {
  const [filter, setFilter] = useState<"all" | CandidateStatus>("all");
  const candidates = (scan?.top_candidates ?? []).filter((candidate) => filter === "all" || candidate.candidate_status === filter);

  return (
    <div className="space-y-4">
      <SectionHeader
        description="候選清單先看未來事件、預期差與波段觸發；不是全市場、資料不可信、或禁追時，都不該變成買進理由。"
        eyebrow="Scanner"
        title="市場候選"
        actions={<button className="focus-ring rounded-lg bg-[#0f6b4f] px-4 py-2 text-sm font-black text-white hover:bg-[#0b5c43]" type="button" onClick={onRunScan}>{loading ? "掃描中" : "重新掃描"}</button>}
      />
      <div className="grid gap-3 md:grid-cols-4">
        <MetricCard detail={universeSourceLabel(scan?.universe_source)} label="掃描範圍" value={scan ? `${scan.completed_count}/${scan.universe_count}` : "-"} />
        <MetricCard detail="資料不足會被壓低" label="可研究候選" tone="gain" value={`${scan?.top_candidates.filter((item) => item.candidate_status === "qualified_research").length ?? 0}`} />
        <MetricCard detail="估值或價位不到" label="等便宜價" tone="warn" value={`${scan?.top_candidates.filter((item) => item.candidate_status === "wait_price").length ?? 0}`} />
        <MetricCard detail={scan?.is_full_market ? "全市場掃描" : "不是全市場"} label="範圍誠實標示" tone={scan?.is_full_market ? "gain" : "warn"} value={scan?.is_full_market ? "完整" : "有限"} />
      </div>
      {!scan?.is_full_market ? (
        <Notice message="目前掃描不是全市場結果，不能把沒有出現在清單上的股票視為不好，也不能把榜首當成市場最佳標的。" />
      ) : null}
      <Notice message="市場候選現在以未來劇本為主：上行情境要等超預期與支撐確認；震盪只觀察籌碼清洗；轉弱就排除，不用跌深說服自己進場。" />
      <Panel
        title="候選清單"
        action={
          <select className="focus-ring h-9 rounded-lg border border-[#cbd7e2] bg-white px-3 text-sm font-black text-[#0c1b2a]" value={filter} onChange={(event) => setFilter(event.target.value as "all" | CandidateStatus)}>
            {MARKET_SCAN_STATUS_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        }
      >
        {candidates.length ? (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[1240px] border-collapse text-left text-sm">
              <thead className="bg-[#f7fafc] text-xs font-black text-[#526174]">
                <tr>
                  <th className="border-b border-[#d7e0e8] px-3 py-3">股票</th>
                  <th className="border-b border-[#d7e0e8] px-3 py-3">狀態</th>
                  <th className="border-b border-[#d7e0e8] px-3 py-3">研究結論</th>
                  <th className="border-b border-[#d7e0e8] px-3 py-3">未來劇本</th>
                  <th className="border-b border-[#d7e0e8] px-3 py-3">價格計畫</th>
                  <th className="border-b border-[#d7e0e8] px-3 py-3">資料品質</th>
                  <th className="border-b border-[#d7e0e8] px-3 py-3">阻擋條件</th>
                </tr>
              </thead>
              <tbody>
                {candidates.map((candidate) => (
                  <tr key={`${candidate.rank}-${candidate.symbol}`} className="align-top hover:bg-[#fbfdff]">
                    <td className="border-b border-[#eef2f6] px-3 py-3">
                      <button className="text-left" type="button" onClick={() => onOpenSymbol(candidate.symbol, "research")}>
                        <div className="font-black text-[#0c1b2a]">#{candidate.rank} {candidate.symbol}</div>
                        <div className="text-xs font-semibold text-[#64748b]">{displayStockName(candidate.symbol, candidate.name)} · {candidate.industry}</div>
                      </button>
                    </td>
                    <td className="border-b border-[#eef2f6] px-3 py-3">
                      <StatusPill tone={candidateStatusTone(candidate.candidate_status)}>{candidateStatusLabel(candidate.candidate_status)}</StatusPill>
                      <div className="mt-2 text-xs font-semibold leading-5 text-[#64748b]">{candidateStatusDescription(candidate.candidate_status)}</div>
                    </td>
                    <td className="border-b border-[#eef2f6] px-3 py-3">
                      <div className="font-bold text-[#0c1b2a]">{formatResearchStance(candidate.research_decision.stance)}</div>
                      <div className="mt-1 text-xs font-semibold leading-5 text-[#526174]">{candidate.research_decision.next_action}</div>
                      <div className="mt-2">
                        <StatusPill tone={breakoutStatusTone(candidate.breakout_potential.status)}>{breakoutStatusLabel(candidate.breakout_potential.status)}</StatusPill>
                      </div>
                    </td>
                    <td className="border-b border-[#eef2f6] px-3 py-3">
                      <CandidateFutureSummary candidate={candidate} />
                    </td>
                    <td className="border-b border-[#eef2f6] px-3 py-3">
                      <div className="text-xs font-bold text-[#526174]">研究價 {formatNumber(candidate.price_plan.research_price, 2)}</div>
                      <div className="text-xs font-bold text-[#526174]">失效價 {formatNumber(candidate.price_plan.invalidation_price, 2)}</div>
                      {candidate.no_chase_reason ? <div className="mt-1 text-xs font-black text-[#c2410c]">禁追：{candidate.no_chase_reason}</div> : null}
                    </td>
                    <td className="border-b border-[#eef2f6] px-3 py-3">
                      <div className="font-black text-[#0c1b2a]">{formatNumber(candidate.data_quality_score, 0)} /100</div>
                      <div className="mt-1 text-xs font-semibold leading-5 text-[#64748b]">{sourceCoverageSummary(candidate.data_sources)}</div>
                    </td>
                    <td className="border-b border-[#eef2f6] px-3 py-3">
                      <InfoList items={candidate.blockers.slice(0, 3)} fallback="尚無主要阻擋。" compact />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState icon="radar" title="沒有符合條件的候選" detail="這可能是好事：沒有足夠勝率時，保留現金也是決策。先檢查掃描範圍與資料品質。" />
        )}
      </Panel>
    </div>
  );
}

function DataQualityView({
  analysis,
  dataQuality,
  marketOverview,
  marketScan,
  selectedName,
  selectedSymbol,
  sourceRows,
  onRefresh
}: {
  analysis: AnalysisResponse | null;
  dataQuality: ReturnType<typeof buildDataQuality>;
  marketOverview: MarketOverviewResponse | null;
  marketScan: MarketScanResponse | null;
  selectedName: string;
  selectedSymbol: string;
  sourceRows: SourceRow[];
  onRefresh: () => void;
}) {
  return (
    <div className="space-y-4">
      <SectionHeader
        description="這頁專門防止 app 看起來很聰明、但其實資料不足。資料不可信時，系統要誠實降信心。"
        eyebrow="Trust"
        title="資料品質"
        actions={<button className="focus-ring rounded-lg border border-[#cbd7e2] bg-[#fbfdff] px-4 py-2 text-sm font-black text-[#1f3349] hover:bg-[#eef4f8]" type="button" onClick={onRefresh}>重新檢查</button>}
      />
      <div className="grid gap-3 md:grid-cols-4">
        <MetricCard detail={`${selectedSymbol} ${selectedName}`} label="目前標的" value={dataQuality.label} tone={dataQuality.tone} />
        <MetricCard detail="價格、基本面、新聞等" label="可信來源" value={`${dataQuality.trusted}/${dataQuality.total}`} tone={dataQuality.tone} />
        <MetricCard detail={universeSourceLabel(marketScan?.universe_source)} label="掃描範圍" value={marketScan?.is_full_market ? "全市場" : "有限"} tone={marketScan?.is_full_market ? "gain" : "warn"} />
        <MetricCard detail={marketOverview?.risk.generated_at ? formatDateTime(marketOverview.risk.generated_at) : "等待同步"} label="市場資料" value={marketOverview?.market_status ?? "未同步"} />
      </div>
      <Panel title="來源矩陣">
        <div className="grid gap-3 md:grid-cols-2">
          {sourceRows.map((row) => (
            <div key={row.key} className="rounded-lg border border-[#d7e0e8] bg-[#fbfdff] p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-sm font-black text-[#0c1b2a]">{row.label}</div>
                  <div className="mt-1 text-xs font-semibold text-[#64748b]">{row.detail}</div>
                </div>
                <StatusPill tone={row.trusted ? "gain" : "warn"}>{row.trusted ? "可信" : "降信心"}</StatusPill>
              </div>
              <div className="mt-3 text-2xl font-black text-[#0f3365]">{sourceQualityLabel(row.source)}</div>
            </div>
          ))}
        </div>
      </Panel>
      <Panel title="本輪限制">
        <div className="grid gap-3 xl:grid-cols-3">
          <PanelInset title="不能過度解讀">
            <InfoList
              items={[
                marketScan?.is_full_market ? "市場掃描標示為全市場，但仍要注意資料失敗檔。" : "目前候選不是完整全市場結論。",
                hasTrustedFundamentalData(analysis) ? "基本面來源可信，可以看 EPS、ROE、營收。" : "基本面不可信時，不採用 PE、PB、ROE 結論。",
                hasTrustedPriceData(analysis) ? "價格來源可信，可以使用支撐、壓力與失效價。" : "價格不可信時，K 線與停損價不應作為行動依據。"
              ]}
            />
          </PanelInset>
          <PanelInset title="優先修復">
            <InfoList
              items={sourceRows.filter((row) => !row.trusted).map((row) => `${row.label}：${row.detail}`).slice(0, 5)}
              fallback="核心來源目前沒有明顯缺口。"
            />
          </PanelInset>
          <PanelInset title="原始來源">
            <dl className="space-y-2 text-xs font-semibold text-[#526174]">
              {Object.entries(analysis?.data_sources ?? {}).map(([key, value]) => (
                <div key={key} className="flex justify-between gap-3 border-b border-[#eef2f6] pb-2">
                  <dt className="font-black text-[#0c1b2a]">{key}</dt>
                  <dd className="text-right">{String(value)}</dd>
                </div>
              ))}
            </dl>
          </PanelInset>
        </div>
      </Panel>
    </div>
  );
}

function PositionDecisionCard({
  decision,
  onClose,
  onSelectSymbol
}: {
  decision: PositionDecisionItem;
  onClose: (id: number, symbol: string) => void;
  onSelectSymbol: (symbol: string, view?: ViewKey) => void;
}) {
  const tone = positionActionTone(decision.action);
  return (
    <article className="stockai-panel rounded-lg border border-[#d7e0e8] bg-white p-4 shadow-[0_8px_22px_rgba(15,33,52,0.06)]">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <button className="text-left text-xl font-black text-[#0c1b2a]" type="button" onClick={() => onSelectSymbol(decision.position.symbol, "research")}>
              {decision.position.symbol} {displayStockName(decision.position.symbol, decision.position.name)}
            </button>
            <StatusPill tone={tone}>{decision.action_label}</StatusPill>
            <span className="text-xs font-black text-[#64748b]">信心 {decision.confidence}</span>
          </div>
          <p className="mt-2 text-sm font-semibold leading-6 text-[#526174]">{decision.headline}</p>
        </div>
        <div className="grid min-w-[260px] grid-cols-3 gap-2 text-right">
          <MiniStat label="均價" value={formatNumber(decision.position.entry_price, 2)} />
          <MiniStat label="現價" value={formatNumber(decision.latest_close, 2)} />
          <MiniStat label="損益" tone={pnlTone(decision.unrealized_pnl)} value={formatSignedPercentValue(decision.unrealized_pnl_percent)} />
        </div>
      </div>
      <div className="mt-4 grid gap-3 xl:grid-cols-[1.2fr_0.8fr]">
        <div>
          <div className="text-xs font-black uppercase tracking-[0.08em] text-[#64748b]">優先因子</div>
          <div className="mt-2 grid gap-2 md:grid-cols-2 2xl:grid-cols-4">
            {decision.priority_factors.slice(0, 4).map((signal) => (
              <SignalBox key={`${signal.kind}-${signal.label}`} signal={signal} />
            ))}
          </div>
          <p className="mt-3 text-sm font-semibold leading-6 text-[#526174]">{decision.rationale}</p>
        </div>
        <div className="rounded-lg border border-[#d7e0e8] bg-[#fbfdff] p-3">
          <div className="text-xs font-black uppercase tracking-[0.08em] text-[#64748b]">下次檢查</div>
          <InfoList items={decision.next_review_triggers.slice(0, 4)} compact />
        </div>
      </div>
      {decision.future_outlook ? <FutureOutlookPanel outlook={decision.future_outlook} /> : null}
      <div className="mt-4 flex justify-end gap-2">
        <button className="focus-ring rounded-lg border border-[#cbd7e2] bg-[#fbfdff] px-4 py-2 text-sm font-black text-[#1f3349] hover:bg-[#eef4f8]" type="button" onClick={() => onSelectSymbol(decision.position.symbol, "research")}>檢視研究</button>
        <button className="focus-ring rounded-lg border border-[#f3b6bb] bg-[#fff7f7] px-4 py-2 text-sm font-black text-[#b4232c] hover:bg-[#fff1f2]" type="button" onClick={() => onClose(decision.position.id, decision.position.symbol)}>標記結清</button>
      </div>
    </article>
  );
}

function CandidateFutureSummary({ candidate }: { candidate: MarketScanCandidate }) {
  const outlook = candidate.future_outlook;
  if (!outlook) {
    return <EmptyLine text="等待重新掃描後建立未來劇本。" />;
  }

  const tone = futureOutlookTone(outlook);
  const scenarios = outlook.scenarios.slice(0, 3);

  return (
    <div className="min-w-[280px] space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <StatusPill tone={tone}>{outlook.label}</StatusPill>
        <span className="text-xs font-black text-[#0c1b2a]">{outlook.swing_plan.stance}</span>
      </div>
      <div className="grid grid-cols-3 gap-1.5">
        {scenarios.map((scenario) => {
          const scenarioToneValue = scenarioTone(scenario.tone);
          return (
            <div key={scenario.name} className={`rounded-md border px-2 py-1.5 ${toneSoftClass(scenarioToneValue)}`}>
              <div className="truncate text-[11px] font-black">{scenario.name}</div>
              <div className="text-sm font-black">{Math.max(0, Math.min(100, scenario.probability))}%</div>
            </div>
          );
        })}
      </div>
      <div className="rounded-md border border-[#e2e8f0] bg-white p-2 text-xs font-semibold leading-5 text-[#526174]">
        {outlook.expectation_gap}
      </div>
      <div className="text-[11px] font-bold leading-5 text-[#64748b]">{outlook.swing_plan.position_size_hint}</div>
    </div>
  );
}

function FutureOutlookPanel({ outlook }: { outlook: PositionFutureOutlook }) {
  const plan = outlook.swing_plan;
  const planRows = [
    { label: "進場區", value: plan.entry_zone },
    { label: "加碼規則", value: plan.add_rule },
    { label: "減碼規則", value: plan.trim_rule },
    { label: "失效條件", value: plan.stop_rule },
    { label: "下次重算", value: plan.review_rule },
    { label: "部位", value: plan.position_size_hint }
  ];

  return (
    <div className="mt-4 grid gap-3 xl:grid-cols-[1.25fr_0.75fr]">
      <div className="rounded-lg border border-[#d7e0e8] bg-[#fbfdff] p-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <div className="text-xs font-black uppercase tracking-[0.08em] text-[#64748b]">未來劇本</div>
            <div className="mt-1 text-lg font-black text-[#0c1b2a]">{outlook.label}</div>
          </div>
          <StatusPill tone="warn">{outlook.horizon}</StatusPill>
        </div>
        <div className="mt-2 rounded-md border border-[#e2e8f0] bg-white p-2 text-xs font-semibold leading-5 text-[#526174]">{outlook.expectation_gap}</div>
        <div className="mt-3 grid gap-2 lg:grid-cols-3">
          {outlook.scenarios.map((scenario) => (
            <ScenarioBox key={scenario.name} scenario={scenario} />
          ))}
        </div>
        <div className="mt-3">
          <div className="text-xs font-black text-[#64748b]">領先觀察</div>
          <InfoList items={outlook.leading_indicators.slice(0, 4)} compact />
        </div>
      </div>
      <div className="rounded-lg border border-[#d7e0e8] bg-[#fbfdff] p-3">
        <div className="text-xs font-black uppercase tracking-[0.08em] text-[#64748b]">波段計畫</div>
        <div className="mt-1 flex flex-wrap items-center gap-2">
          <div className="text-lg font-black text-[#0c1b2a]">{plan.stance}</div>
          <StatusPill tone="neutral">{plan.horizon}</StatusPill>
        </div>
        <div className="mt-3 space-y-2">
          {planRows.map((row) => (
            <div key={row.label} className="rounded-md border border-[#e2e8f0] bg-white p-2">
              <div className="text-[11px] font-black text-[#64748b]">{row.label}</div>
              <div className="mt-1 text-xs font-semibold leading-5 text-[#263445]">{row.value}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function ScenarioBox({ scenario }: { scenario: PositionFutureOutlook["scenarios"][number] }) {
  const tone = scenarioTone(scenario.tone);
  const probability = Math.max(0, Math.min(100, scenario.probability));
  return (
    <div className={`rounded-lg border p-3 ${toneSoftClass(tone)}`}>
      <div className="flex items-center justify-between gap-2">
        <div className="text-sm font-black">{scenario.name}</div>
        <div className="text-lg font-black">{probability}%</div>
      </div>
      <div className="mt-2 h-1.5 rounded-full bg-[#e2e8f0]">
        <div className={`h-1.5 rounded-full ${toneBarClass(tone)}`} style={{ width: `${probability}%` }} />
      </div>
      <div className="mt-2 space-y-2 text-xs font-semibold leading-5">
        <div><span className="font-black">條件：</span>{scenario.condition}</div>
        <div><span className="font-black">操作：</span>{scenario.action}</div>
        <div><span className="font-black">觸發：</span>{scenario.trigger}</div>
      </div>
    </div>
  );
}

function CandidateSnapshot({ scan, onOpenSymbol }: { scan: MarketScanResponse | null; onOpenSymbol: (symbol: string, view?: ViewKey) => void }) {
  const candidates = scan?.top_candidates.slice(0, 5) ?? [];
  if (!candidates.length) {
    return <EmptyState icon="radar" title="尚未有候選快照" detail="執行市場掃描後，這裡會顯示值得研究、等便宜價與只觀察的標的。" />;
  }
  return (
    <div className="space-y-2">
      {candidates.map((candidate) => {
        const outlook = candidate.future_outlook;
        const detail = outlook
          ? `${outlook.label} · ${outlook.swing_plan.stance}`
          : candidate.research_decision.next_action || candidate.why_ranked[0] || "等待研究理由";
        return (
          <button key={`${candidate.rank}-${candidate.symbol}`} className="flex w-full items-center gap-3 rounded-lg border border-[#e2e8f0] bg-[#fbfdff] p-3 text-left hover:border-[#b9c9d7]" type="button" onClick={() => onOpenSymbol(candidate.symbol, "research")}>
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[#08233a] text-sm font-black text-white">#{candidate.rank}</div>
            <div className="min-w-0 flex-1">
              <div className="font-black text-[#0c1b2a]">{candidate.symbol} {displayStockName(candidate.symbol, candidate.name)}</div>
              <div className="truncate text-xs font-semibold text-[#64748b]">{detail}</div>
              {outlook ? (
                <div className="mt-1 flex flex-wrap gap-1">
                  {outlook.scenarios.slice(0, 3).map((scenario) => (
                    <span key={scenario.name} className={`rounded border px-1.5 py-0.5 text-[10px] font-black ${tonePillClass(scenarioTone(scenario.tone))}`}>
                      {scenario.name} {Math.max(0, Math.min(100, scenario.probability))}%
                    </span>
                  ))}
                </div>
              ) : null}
            </div>
            <StatusPill tone={candidateStatusTone(candidate.candidate_status)}>{candidateStatusLabel(candidate.candidate_status)}</StatusPill>
          </button>
        );
      })}
    </div>
  );
}

function GateSummary({ analysis }: { analysis: AnalysisResponse | null }) {
  const gates = [
    { label: "基本面", status: analysis?.fundamental_gate.status ?? "unknown", detail: analysis?.fundamental_gate.failed_reasons?.[0] ?? "看 EPS、ROE、營收是否可信" },
    { label: "估值面", status: analysis?.valuation_gate.status ?? "unknown", detail: analysis?.valuation_gate.warning ?? analysis?.valuation_gate.pe_band ?? "等待估值資料" },
    { label: "時機面", status: analysis?.timing_gate.status ?? "unknown", detail: analysis?.timing_gate.entry_conditions?.[0] ?? analysis?.timing_gate.support_zone ?? "等待 K 線條件" }
  ];
  return (
    <div className="grid gap-3 md:grid-cols-3">
      {gates.map((gate) => (
        <div key={gate.label} className="rounded-lg border border-[#d7e0e8] bg-[#fbfdff] p-4">
          <div className="flex items-center justify-between gap-2">
            <div className="text-sm font-black text-[#0c1b2a]">{gate.label}</div>
            <StatusPill tone={gateTone(gate.status)}>{formatGateStatus(gate.status)}</StatusPill>
          </div>
          <div className="mt-3 text-sm font-semibold leading-6 text-[#526174]">{gate.detail}</div>
        </div>
      ))}
    </div>
  );
}

function PricePlanCard({ analysis }: { analysis: AnalysisResponse | null }) {
  const trusted = hasTrustedPriceData(analysis);
  const plan = analysis?.price_plan;
  return (
    <PanelInset title="價格計畫">
      <div className="grid grid-cols-3 gap-2">
        <MiniStat label="研究價" value={trusted ? formatNumber(plan?.research_price, 2) : "-"} />
        <MiniStat label="觀察價" value={trusted ? formatNumber(plan?.watch_price, 2) : "-"} />
        <MiniStat label="失效價" tone="loss" value={trusted ? formatNumber(plan?.invalidation_price, 2) : "-"} />
      </div>
      <p className="mt-3 text-xs font-semibold leading-5 text-[#526174]">{trusted ? plan?.position_size_hint ?? "等待部位建議" : "價格不是可信來源時，不建立研究價、觀察價與失效價。"}</p>
    </PanelInset>
  );
}

function KlineNotes({ analysis }: { analysis: AnalysisResponse | null }) {
  return (
    <PanelInset title="K 線策略">
      <div className="text-sm font-black text-[#0c1b2a]">{analysis?.kline_analysis.headline ?? "等待 K 線分析"}</div>
      <div className="mt-1 text-xs font-semibold text-[#64748b]">{analysis?.kline_analysis.trend ?? "趨勢尚未同步"}</div>
      <InfoList items={[...(analysis?.kline_analysis.strategy_notes ?? []), ...(analysis?.kline_analysis.invalidation ?? [])].slice(0, 5)} fallback="等待支撐、壓力與失效條件。" compact />
    </PanelInset>
  );
}

function GateColumn({
  metrics,
  status,
  title,
  trusted
}: {
  metrics: Array<{ detail: string; label: string; tone?: Tone; value: string }>;
  status: GateStatus;
  title: string;
  trusted: boolean;
}) {
  return (
    <div className="rounded-lg border border-[#d7e0e8] bg-[#fbfdff] p-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-black text-[#0c1b2a]">{title}</h3>
        <StatusPill tone={trusted ? gateTone(status) : "warn"}>{trusted ? formatGateStatus(status) : "不採用"}</StatusPill>
      </div>
      <div className="mt-3 space-y-2">
        {metrics.map((metric) => (
          <div key={metric.label} className="rounded-md border border-[#e2e8f0] bg-white p-3">
            <div className="text-xs font-bold text-[#64748b]">{metric.label}</div>
            <div className={toneTextClass(metric.tone ?? "neutral")}>{metric.value}</div>
            <div className="mt-1 text-[11px] font-semibold leading-4 text-[#64748b]">{metric.detail}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function MiniPriceChart({ chart, loading, theme }: { chart: ChartResponse | null; loading: boolean; theme: Theme }) {
  const closes = useMemo(() => extractCloseSeries(chart).slice(-80), [chart]);
  if (!closes.length) {
    return (
      <div className="flex h-[220px] items-center justify-center rounded-lg border border-[#d7e0e8] bg-[#fbfdff] text-sm font-bold text-[#64748b]">
        {loading ? "K 線同步中" : "等待 K 線資料"}
      </div>
    );
  }
  const min = Math.min(...closes);
  const max = Math.max(...closes);
  const width = 420;
  const height = 220;
  const path = closes
    .map((value, index) => {
      const x = (index / Math.max(1, closes.length - 1)) * (width - 24) + 12;
      const y = height - 20 - ((value - min) / Math.max(1e-9, max - min)) * (height - 44);
      return `${index === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(" ");
  const last = closes[closes.length - 1];
  const first = closes[0];
  const tone = last >= first ? (theme === "dark" ? "#fb7185" : "#dc2626") : (theme === "dark" ? "#7ee6a2" : "#168447");
  const chartBackground = theme === "dark" ? "#0f1722" : "#fbfdff";
  const chartLine = theme === "dark" ? "#334155" : "#e2e8f0";
  const chartLabel = theme === "dark" ? "#a7b5c6" : "#64748b";
  return (
    <div className="rounded-lg border border-[#d7e0e8] bg-white p-3">
      <svg className="block h-auto w-full" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="價格趨勢摘要">
        <rect x="0" y="0" width={width} height={height} rx="8" fill={chartBackground} />
        {[0.25, 0.5, 0.75].map((ratio) => (
          <line key={ratio} x1="12" x2={width - 12} y1={20 + ratio * (height - 44)} y2={20 + ratio * (height - 44)} stroke={chartLine} strokeDasharray="4 5" />
        ))}
        <path d={path} fill="none" stroke={tone} strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" />
        <circle cx={width - 12} cy={height - 20 - ((last - min) / Math.max(1e-9, max - min)) * (height - 44)} r="4" fill={tone} />
        <text x="14" y="22" fill={chartLabel} fontSize="12" fontWeight="800">近 80 根日 K 收盤</text>
        <text x={width - 14} y="22" fill={tone} fontSize="13" fontWeight="900" textAnchor="end">{formatNumber(last, 2)}</text>
      </svg>
    </div>
  );
}

function SectionHeader({
  actions,
  description,
  eyebrow,
  title
}: {
  actions?: React.ReactNode;
  description: string;
  eyebrow: string;
  title: string;
}) {
  return (
    <div className="stockai-panel rounded-lg border border-[#d7e0e8] bg-white p-5 shadow-[0_8px_22px_rgba(15,33,52,0.07)]">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="text-xs font-black uppercase tracking-[0.12em] text-[#1d5f8f]">{eyebrow}</div>
          <h1 className="mt-1 text-[26px] font-black leading-tight text-[#0c1b2a]">{title}</h1>
          <p className="mt-1 max-w-3xl text-sm font-semibold leading-6 text-[#526174]">{description}</p>
        </div>
        {actions ? <div className="shrink-0">{actions}</div> : null}
      </div>
    </div>
  );
}

function Panel({ action, children, title }: { action?: React.ReactNode; children: React.ReactNode; title: string }) {
  return (
    <section className="stockai-panel min-w-0 rounded-lg border border-[#d7e0e8] bg-white p-4 shadow-[0_8px_22px_rgba(15,33,52,0.06)]">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="text-lg font-black text-[#0c1b2a]">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

function PanelInset({ children, title }: { children: React.ReactNode; title: string }) {
  return (
    <div className="rounded-lg border border-[#d7e0e8] bg-[#fbfdff] p-3">
      <div className="mb-2 text-xs font-black uppercase tracking-[0.08em] text-[#64748b]">{title}</div>
      {children}
    </div>
  );
}

function MetricCard({ detail, label, tone = "neutral", value }: { detail: string; label: string; tone?: Tone; value: string }) {
  return (
    <div className="stockai-card rounded-lg border border-[#d7e0e8] bg-white p-4 shadow-[0_6px_16px_rgba(15,33,52,0.05)]">
      <div className="text-xs font-black text-[#64748b]">{label}</div>
      <div className={`mt-2 text-2xl font-black leading-tight ${toneTextClass(tone)}`}>{value}</div>
      <div className="mt-2 text-xs font-semibold leading-5 text-[#526174]">{detail}</div>
    </div>
  );
}

function ExecutionPanel({ items }: { items: ExecutionItem[] }) {
  return (
    <div className="rounded-lg border border-[#cbd7e2] bg-[#fbfdff] p-3">
      <div className="flex flex-col gap-1 sm:flex-row sm:items-baseline sm:justify-between">
        <h2 className="text-sm font-black text-[#0c1b2a]">現在先做這 3 件事</h2>
        <span className="text-xs font-bold text-[#64748b]">依持股風險、資料品質、候選範圍排序</span>
      </div>
      <div className="mt-3 grid gap-2 lg:grid-cols-3">
        {items.map((item, index) => (
          <div key={`${item.label}-${index}`} className={`rounded-lg border p-3 ${toneSoftClass(item.tone)}`}>
            <div className="flex items-center gap-2">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-white text-xs font-black shadow-sm">{index + 1}</span>
              <span className="text-xs font-black">{item.label}</span>
            </div>
            <div className="mt-2 text-sm font-black leading-5">{item.action}</div>
            <div className="mt-1 text-xs font-semibold leading-5">{item.detail}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function PriorityCard({
  actionLabel,
  children,
  icon,
  kicker,
  title,
  tone,
  onAction
}: {
  actionLabel: string;
  children: React.ReactNode;
  icon: IconName;
  kicker: string;
  title: string;
  tone: Tone;
  onAction: () => void;
}) {
  return (
    <article className="stockai-panel flex min-h-[300px] flex-col rounded-lg border border-[#d7e0e8] bg-white p-4 shadow-[0_8px_22px_rgba(15,33,52,0.06)]">
      <div className="flex items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-full bg-[#08233a] text-sm font-black text-white">{kicker}</div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 text-sm font-black text-[#0c1b2a]">
            <Icon className="h-4 w-4" name={icon} />
            {title}
          </div>
          <div className={`mt-1 h-1.5 w-16 rounded-full ${toneBarClass(tone)}`} />
        </div>
      </div>
      <div className="mt-4 flex-1">{children}</div>
      <button className="focus-ring mt-4 flex h-10 items-center justify-center gap-2 rounded-lg border border-[#cbd7e2] bg-[#fbfdff] text-sm font-black text-[#1f3349] hover:bg-[#eef4f8]" type="button" onClick={onAction}>
        {actionLabel}
        <Icon className="h-4 w-4" name="arrowRight" />
      </button>
    </article>
  );
}

function PositionField({
  label,
  onChange,
  placeholder,
  type = "text",
  value
}: {
  label: string;
  onChange: (value: string) => void;
  placeholder?: string;
  type?: string;
  value: string;
}) {
  return (
    <label className="block">
      <span className="text-xs font-black text-[#526174]">{label}</span>
      <input
        className="focus-ring mt-1 h-11 w-full rounded-lg border border-[#cbd7e2] bg-white px-3 text-sm font-bold text-[#0c1b2a]"
        inputMode={type === "number" ? "decimal" : undefined}
        placeholder={placeholder}
        type={type}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}

function CompactDecisionRow({ decision, onOpenSymbol }: { decision: PositionDecisionItem; onOpenSymbol: (symbol: string) => void }) {
  return (
    <button className="w-full rounded-lg border border-[#e2e8f0] bg-[#fbfdff] p-2 text-left hover:border-[#b9c9d7]" type="button" onClick={() => onOpenSymbol(decision.position.symbol)}>
      <div className="flex items-center justify-between gap-2">
        <span className="font-black text-[#0c1b2a]">{decision.position.symbol}</span>
        <StatusPill tone={positionActionTone(decision.action)}>{decision.action_label}</StatusPill>
      </div>
      <div className="mt-1 line-clamp-2 text-xs font-semibold leading-5 text-[#526174]">{decision.headline}</div>
    </button>
  );
}

function SignalBox({ signal }: { signal: PositionDecisionItem["priority_factors"][number] }) {
  const tone = signal.tone === "positive" ? "gain" : signal.tone === "risk" ? "loss" : "neutral";
  return (
    <div className={`rounded-lg border p-3 ${toneSoftClass(tone)}`}>
      <div className="text-xs font-black">{signal.label}</div>
      <div className="mt-1 text-xs font-semibold leading-5">{signal.detail}</div>
    </div>
  );
}

function SourceMiniRow({ row }: { row: SourceRow }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border border-[#e2e8f0] bg-[#fbfdff] px-3 py-2">
      <div className="min-w-0">
        <div className="truncate text-xs font-black text-[#0c1b2a]">{row.label}</div>
        <div className="truncate text-[11px] font-semibold text-[#64748b]">{sourceQualityLabel(row.source)}</div>
      </div>
      <StatusPill tone={row.trusted ? "gain" : "warn"}>{row.trusted ? "良好" : "降信心"}</StatusPill>
    </div>
  );
}

function LevelBox({ fallback, label, tone, values }: { fallback: string; label: string; tone: Tone; values: string[] }) {
  return (
    <div className={`rounded-lg border p-3 ${toneSoftClass(tone)}`}>
      <div className="text-xs font-black">{label}</div>
      <div className="mt-2 space-y-1 text-sm font-black">
        {(values.length ? values : [fallback]).slice(0, 2).map((value) => <div key={value}>{value}</div>)}
      </div>
    </div>
  );
}

function GateMini({ label, status }: { label: string; status: GateStatus }) {
  return (
    <div className="rounded-lg border border-[#d7e0e8] bg-[#fbfdff] p-3">
      <div className="text-xs font-black text-[#64748b]">{label}</div>
      <div className={`mt-1 text-sm font-black ${toneTextClass(gateTone(status))}`}>{formatGateStatus(status)}</div>
    </div>
  );
}

function DisciplineLine({ icon, label, value }: { icon: IconName; label: string; value: string }) {
  return (
    <div className="flex gap-2 rounded-md bg-white p-2">
      <Icon className="mt-0.5 h-4 w-4 shrink-0 text-[#1d5f8f]" name={icon} />
      <div>
        <div className="text-[11px] font-black text-[#64748b]">{label}</div>
        <div className="text-xs font-semibold leading-5 text-[#263445]">{value}</div>
      </div>
    </div>
  );
}

function MiniStat({ label, tone = "neutral", value }: { label: string; tone?: Tone; value: string }) {
  return (
    <div className="rounded-md border border-[#e2e8f0] bg-white p-2">
      <div className="text-[11px] font-black text-[#64748b]">{label}</div>
      <div className={`mt-1 truncate text-sm font-black ${toneTextClass(tone)}`}>{value}</div>
    </div>
  );
}

function TickerValue({ label, subValue, tone = "neutral", value }: { label: string; subValue?: string; tone?: Tone; value: string }) {
  return (
    <div className="flex items-baseline gap-2">
      <span className="text-xs font-black text-[#526174]">{label}</span>
      <span className={`text-base font-black ${toneTextClass(tone)}`}>{value}</span>
      {subValue ? <span className={`text-xs font-black ${toneTextClass(tone)}`}>{subValue}</span> : null}
    </div>
  );
}

function InfoList({ compact = false, fallback, items }: { compact?: boolean; fallback?: string; items: string[] }) {
  const values = items.map((item) => item.trim()).filter(Boolean);
  if (!values.length) return <EmptyLine text={fallback ?? "等待資料。"} />;
  return (
    <ul className={compact ? "mt-2 space-y-1" : "mt-3 space-y-2"}>
      {values.map((item) => (
        <li key={item} className="flex gap-2 text-xs font-semibold leading-5 text-[#526174]">
          <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-[#1d5f8f]" />
          <span>{item}</span>
        </li>
      ))}
    </ul>
  );
}

function StatusPill({ children, tone }: { children: React.ReactNode; tone: Tone }) {
  return <span className={`inline-flex shrink-0 items-center rounded-md border px-2 py-1 text-[11px] font-black ${tonePillClass(tone)}`}>{children}</span>;
}

function Notice({ message, onDismiss }: { message: string; onDismiss?: () => void }) {
  return (
    <div className="stockai-notice flex items-start gap-3 rounded-lg border border-[#f1c673] bg-[#fff8e8] p-3 text-sm font-bold text-[#7a4b00]">
      <Icon className="mt-0.5 h-5 w-5 shrink-0" name="alert" />
      <div className="flex-1 leading-6">{message}</div>
      {onDismiss ? (
        <button className="rounded p-1 hover:bg-black/5" type="button" onClick={onDismiss} aria-label="關閉通知">
          <Icon className="h-4 w-4" name="x" />
        </button>
      ) : null}
    </div>
  );
}

function EmptyState({ detail, icon, title }: { detail: string; icon: IconName; title: string }) {
  return (
    <div className="rounded-lg border border-dashed border-[#cbd7e2] bg-[#fbfdff] p-8 text-center">
      <Icon className="mx-auto h-8 w-8 text-[#94a3b8]" name={icon} />
      <div className="mt-3 text-lg font-black text-[#0c1b2a]">{title}</div>
      <div className="mx-auto mt-2 max-w-md text-sm font-semibold leading-6 text-[#64748b]">{detail}</div>
    </div>
  );
}

function EmptyLine({ text }: { text: string }) {
  return <div className="rounded-lg border border-dashed border-[#cbd7e2] bg-[#fbfdff] p-3 text-xs font-semibold leading-5 text-[#64748b]">{text}</div>;
}

function buildSourceRows(analysis: AnalysisResponse | null): SourceRow[] {
  return SOURCE_LABELS.map((item) => {
    const source = String(analysis?.data_sources?.[item.key] ?? "unavailable");
    const trusted = hasTrustedSource(source, item.kind);
    return {
      key: item.key,
      label: item.label,
      source,
      trusted,
      detail: trusted ? `${sourceQualityLabel(source)} 可納入判斷` : `${sourceQualityLabel(source)} 不足以支撐高信心結論`
    };
  });
}

function buildDataQuality(rows: SourceRow[]) {
  const total = rows.length;
  const trusted = rows.filter((row) => row.trusted).length;
  if (trusted >= 5) return { label: "良好", tone: "gain" as Tone, total, trusted };
  if (trusted >= 3) return { label: "部分可用", tone: "warn" as Tone, total, trusted };
  return { label: "低信任", tone: "loss" as Tone, total, trusted };
}

function buildExecutionItems({
  candidateCount,
  dataQuality,
  marketScan,
  positionSummary,
  priorityPositions,
  risk,
  todayPlan
}: {
  candidateCount: number;
  dataQuality: ReturnType<typeof buildDataQuality>;
  marketScan: MarketScanResponse | null;
  positionSummary: PositionSummary;
  priorityPositions: PositionDecisionItem[];
  risk: MarketOverviewResponse["risk"] | null;
  todayPlan: ReturnType<typeof buildTodayActionPlan>;
}): ExecutionItem[] {
  const firstRiskPosition = priorityPositions.find((item) => item.action === "sell" || item.action === "reduce");
  const riskCount = positionSummary.sellCount + positionSummary.reduceCount;
  const execution: ExecutionItem[] = [];

  if (riskCount > 0) {
    execution.push({
      label: "持股先處理",
      action: `先檢查 ${riskCount} 檔減碼 / 離場`,
      detail: firstRiskPosition
        ? `${firstRiskPosition.position.symbol}：${firstRiskPosition.headline}`
        : "重大事件、營收或失效條件偏弱時，先降風險，不急著找新標的。",
      tone: "loss"
    });
  } else if (positionSummary.holdCount > 0 || positionSummary.addCount > 0) {
    execution.push({
      label: "持股維持紀律",
      action: "續抱，但只在條件成立才加碼",
      detail: "沒有優先減碼訊號時，先守失效價與重大消息；加碼只能小幅、分批、等支撐。",
      tone: "gain"
    });
  } else {
    execution.push({
      label: "先建立庫存基準",
      action: "輸入均價與股數",
      detail: "沒有庫存資料時，系統只能做個股研究，無法判斷你該續抱、減碼或加碼。",
      tone: "warn"
    });
  }

  execution.push({
    label: "選定股票",
    action: todayPlan.headline,
    detail: todayPlan.primaryAction || todayPlan.noChase,
    tone: todayPlan.tone
  });

  if (dataQuality.trusted < 5) {
    execution.push({
      label: "資料先補齊",
      action: `${dataQuality.label}，不要下重判斷`,
      detail: `${dataQuality.trusted}/${dataQuality.total} 個來源可信；資料不足時只做觀察，不建立高信心結論。`,
      tone: dataQuality.tone
    });
  } else if (marketScan && !marketScan.is_full_market) {
    execution.push({
      label: "候選範圍有限",
      action: "不要把榜單當全市場結論",
      detail: `${universeSourceLabel(marketScan.universe_source)} · ${marketScan.completed_count}/${marketScan.universe_count}，適合縮小研究範圍，不適合直接排行買賣。`,
      tone: "warn"
    });
  } else if (candidateCount > 0) {
    execution.push({
      label: "候選研究",
      action: `只挑 ${candidateCount} 檔做深查`,
      detail: "候選要再通過基本面、估值、K 線與禁追條件；不是看到分數就行動。",
      tone: "gain"
    });
  } else {
    execution.push({
      label: "沒有好標的",
      action: "保留現金也是決策",
      detail: risk?.lights.composite === "red" ? "大盤偏弱時不要硬找股票。" : "候選條件不足時，等待比亂做更好。",
      tone: "neutral"
    });
  }

  return execution.slice(0, 3);
}

function summarizePositions(decisions: PositionDecisionItem[]): PositionSummary {
  const totalCost = decisions.reduce((sum, item) => sum + item.cost_basis, 0);
  const hasMarketValue = decisions.some((item) => item.market_value !== null && item.market_value !== undefined);
  const marketValue = hasMarketValue ? decisions.reduce((sum, item) => sum + (item.market_value ?? 0), 0) : null;
  const totalPnl = marketValue === null ? null : marketValue - totalCost;
  const totalPnlPercent = totalPnl === null || totalCost <= 0 ? null : (totalPnl / totalCost) * 100;
  return {
    addCount: decisions.filter((item) => item.action === "add").length,
    hasMarketValue,
    holdCount: decisions.filter((item) => item.action === "hold").length,
    marketValue,
    reduceCount: decisions.filter((item) => item.action === "reduce").length,
    sellCount: decisions.filter((item) => item.action === "sell").length,
    totalCost,
    totalPnl,
    totalPnlPercent,
    watchCount: decisions.filter((item) => item.action === "watch").length
  };
}

function comparePositionUrgency(a: PositionDecisionItem, b: PositionDecisionItem) {
  return positionActionRank(b.action) - positionActionRank(a.action);
}

function positionActionRank(action: PositionDecisionItem["action"]) {
  const ranks: Record<PositionDecisionItem["action"], number> = {
    sell: 5,
    reduce: 4,
    watch: 3,
    add: 2,
    hold: 1
  };
  return ranks[action] ?? 0;
}

function mergeWatchlist(current: WatchlistItem[], item: WatchlistItem) {
  const normalized = normalizeSymbol(item.symbol);
  const without = current.filter((row) => normalizeSymbol(row.symbol) !== normalized);
  return [item, ...without];
}

function extractCloseSeries(chart: ChartResponse | null): number[] {
  const traces = Array.isArray(chart?.figure.data) ? (chart.figure.data as PlotTrace[]) : [];
  const candleTrace = traces.find((trace) => trace.type === "candlestick" || toArray(trace.close).length > 0);
  if (candleTrace) return toNumericArray(candleTrace.close).filter(Number.isFinite);
  const lineTrace = traces.find((trace) => toArray(trace.y).length > 0);
  return lineTrace ? toNumericArray(lineTrace.y).filter(Number.isFinite) : [];
}

function sourceCoverageSummary(sources: Record<string, string>) {
  const rows = SOURCE_LABELS.map((item) => ({
    label: item.label,
    trusted: hasTrustedSource(sources[item.key], item.kind)
  }));
  const trusted = rows.filter((row) => row.trusted).length;
  const weak = rows
    .filter((row) => !row.trusted)
    .slice(0, 2)
    .map((row) => row.label);
  return weak.length ? `${trusted}/${rows.length} 可信；缺 ${weak.join("、")}` : `${trusted}/${rows.length} 可信`;
}

function toArray(value: unknown): unknown[] {
  if (isPlotlyBinaryArray(value)) return decodePlotlyBinaryArray(value);
  return Array.isArray(value) ? value : [];
}

function toNumericArray(value: unknown) {
  return toArray(value).map((item) => Number(item)).filter(Number.isFinite);
}

function isPlotlyBinaryArray(value: unknown): value is PlotlyBinaryArray {
  return Boolean(value && typeof value === "object" && "bdata" in value && typeof (value as PlotlyBinaryArray).bdata === "string");
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
      return Array.from(new Float64Array(buffer));
    case "f4":
      return Array.from(new Float32Array(buffer));
    case "i4":
      return Array.from(new Int32Array(buffer));
    case "u4":
      return Array.from(new Uint32Array(buffer));
    case "i2":
      return Array.from(new Int16Array(buffer));
    case "u2":
      return Array.from(new Uint16Array(buffer));
    case "i1":
      return Array.from(new Int8Array(buffer));
    case "u1":
      return Array.from(new Uint8Array(buffer));
    default:
      return [];
  }
}

function normalizeSymbol(value: string) {
  return value.toUpperCase().replace(/[^A-Z0-9.^-]/g, "").trim();
}

function parsePositiveNumber(value: string) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

function parseOptionalPositiveNumber(value: string) {
  if (!value.trim()) return null;
  return parsePositiveNumber(value);
}

function gateTone(status: GateStatus): Tone {
  if (status === "pass") return "gain";
  if (status === "fail") return "loss";
  if (status === "watch") return "warn";
  return "neutral";
}

function positionActionTone(action: PositionDecisionItem["action"]): Tone {
  if (action === "add" || action === "hold") return "gain";
  if (action === "sell" || action === "reduce") return "loss";
  return "warn";
}

function futureOutlookTone(outlook: PositionFutureOutlook): Tone {
  const upside = outlook.scenarios.find((scenario) => scenario.tone === "positive")?.probability ?? 0;
  const downside = outlook.scenarios.find((scenario) => scenario.tone === "risk")?.probability ?? 0;
  if (downside >= upside + 12) return "loss";
  if (upside >= downside + 12) return "gain";
  if (outlook.label.includes("資料不足") || outlook.label.includes("待重算")) return "neutral";
  return "warn";
}

function scenarioTone(tone: PositionFutureOutlook["scenarios"][number]["tone"]): Tone {
  if (tone === "positive") return "gain";
  if (tone === "risk") return "loss";
  return "neutral";
}

function pnlTone(value: number | null | undefined): Tone {
  if (value === null || value === undefined) return "neutral";
  return value >= 0 ? "gain" : "loss";
}

function marketLightTone(light?: Light): Tone {
  if (light === "green") return "gain";
  if (light === "red") return "loss";
  if (light === "yellow") return "warn";
  return "neutral";
}

function marketLightLabel(light?: Light) {
  if (light === "green") return "偏穩";
  if (light === "red") return "偏風險";
  if (light === "yellow") return "中性謹慎";
  return "等待資料";
}

function quoteTone(value: number): Tone {
  if (value > 0) return "loss";
  if (value < 0) return "gain";
  return "neutral";
}

function toneTextClass(tone: Tone) {
  const classes: Record<Tone, string> = {
    gain: "text-[#0f7a48]",
    warn: "text-[#d97706]",
    loss: "text-[#dc2626]",
    neutral: "text-[#0f3365]"
  };
  return classes[tone];
}

function tonePillClass(tone: Tone) {
  const classes: Record<Tone, string> = {
    gain: "border-[#b8dcc7] bg-[#f1fbf6] text-[#0f7a48]",
    warn: "border-[#f4d494] bg-[#fff8e8] text-[#b45309]",
    loss: "border-[#f3b6bb] bg-[#fff1f2] text-[#b4232c]",
    neutral: "border-[#d7e0e8] bg-[#f8fafc] text-[#475569]"
  };
  return classes[tone];
}

function toneSoftClass(tone: Tone) {
  const classes: Record<Tone, string> = {
    gain: "border-[#b8dcc7] bg-[#f1fbf6] text-[#075f3f]",
    warn: "border-[#f4d494] bg-[#fff8e8] text-[#8a5a00]",
    loss: "border-[#f3b6bb] bg-[#fff1f2] text-[#9f1f32]",
    neutral: "border-[#d7e0e8] bg-[#f8fafc] text-[#304256]"
  };
  return classes[tone];
}

function toneBarClass(tone: Tone) {
  const classes: Record<Tone, string> = {
    gain: "bg-[#16a34a]",
    warn: "bg-[#f59e0b]",
    loss: "bg-[#dc2626]",
    neutral: "bg-[#64748b]"
  };
  return classes[tone];
}

function qualityBadgeClass(tone: Tone) {
  return `rounded-md border px-2 py-1 text-[11px] font-black ${tonePillClass(tone)}`;
}

function formatMoney(value: number | null | undefined) {
  if (value === null || value === undefined || !Number.isFinite(value)) return "-";
  return value.toLocaleString("zh-TW", { maximumFractionDigits: 0 });
}

function formatSignedMoney(value: number | null | undefined) {
  if (value === null || value === undefined || !Number.isFinite(value)) return "-";
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${formatMoney(value)}`;
}

function formatSignedPercent(value: number | null | undefined) {
  if (value === null || value === undefined || !Number.isFinite(value)) return "-";
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${value.toLocaleString("zh-TW", { maximumFractionDigits: 2, minimumFractionDigits: 2 })}%`;
}

function formatSignedPercentValue(value: number | null | undefined) {
  return value === null || value === undefined ? "-" : formatSignedPercent(value);
}

function formatCompactNumber(value: number) {
  if (value >= 100_000_000) return `${formatNumber(value / 100_000_000, 1)}億`;
  if (value >= 10_000) return `${formatNumber(value / 10_000, 1)}萬`;
  return formatNumber(value, 0);
}

function formatDateTime(value: string | null | undefined) {
  if (!value) return "等待同步";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-TW", {
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    month: "2-digit",
    timeZone: "Asia/Taipei"
  }).format(date);
}

function LogoMark() {
  return (
    <svg aria-hidden="true" className="h-10 w-10 shrink-0" viewBox="0 0 48 48" fill="none">
      <rect width="48" height="48" rx="10" fill="#0f6b4f" />
      <path d="M12 30.5L18.8 23.7L23.5 27.8L35.5 15.5" stroke="white" strokeLinecap="round" strokeLinejoin="round" strokeWidth="3.6" />
      <path d="M30 15.5H35.5V21" stroke="white" strokeLinecap="round" strokeLinejoin="round" strokeWidth="3.6" />
    </svg>
  );
}

type IconName =
  | "activity"
  | "alert"
  | "arrowRight"
  | "briefcase"
  | "clock"
  | "expand"
  | "home"
  | "radar"
  | "refresh"
  | "search"
  | "shield"
  | "star"
  | "target"
  | "x";

function Icon({ className, name }: { className?: string; name: IconName }) {
  const common = {
    className,
    fill: "none",
    stroke: "currentColor",
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    strokeWidth: 2,
    viewBox: "0 0 24 24"
  };

  switch (name) {
    case "home":
      return <svg aria-hidden="true" {...common}><path d="M3 11.5 12 4l9 7.5" /><path d="M5.5 10.5V20h13v-9.5" /><path d="M9.5 20v-6h5v6" /></svg>;
    case "briefcase":
      return <svg aria-hidden="true" {...common}><path d="M9 7V5.5A1.5 1.5 0 0 1 10.5 4h3A1.5 1.5 0 0 1 15 5.5V7" /><path d="M4 8.5h16v10A1.5 1.5 0 0 1 18.5 20h-13A1.5 1.5 0 0 1 4 18.5v-10Z" /><path d="M4 13h16" /><path d="M10 13v1h4v-1" /></svg>;
    case "search":
      return <svg aria-hidden="true" {...common}><circle cx="11" cy="11" r="6.5" /><path d="m16 16 4 4" /></svg>;
    case "radar":
      return <svg aria-hidden="true" {...common}><circle cx="12" cy="12" r="8" /><circle cx="12" cy="12" r="3" /><path d="M12 12 18 6" /><path d="M12 4v2" /><path d="M20 12h-2" /><path d="M12 20v-2" /><path d="M4 12h2" /></svg>;
    case "shield":
      return <svg aria-hidden="true" {...common}><path d="M12 3 19 6v5c0 4.5-2.8 8-7 10-4.2-2-7-5.5-7-10V6l7-3Z" /><path d="m9 12 2 2 4-5" /></svg>;
    case "activity":
      return <svg aria-hidden="true" {...common}><path d="M3 12h4l2-6 4 12 2-6h6" /></svg>;
    case "clock":
      return <svg aria-hidden="true" {...common}><circle cx="12" cy="12" r="8" /><path d="M12 8v5l3 2" /></svg>;
    case "refresh":
      return <svg aria-hidden="true" {...common}><path d="M20 11a8 8 0 0 0-14.5-4.5L4 8" /><path d="M4 4v4h4" /><path d="M4 13a8 8 0 0 0 14.5 4.5L20 16" /><path d="M20 20v-4h-4" /></svg>;
    case "star":
      return <svg aria-hidden="true" {...common}><path d="m12 3 2.6 5.4 5.9.8-4.2 4.1 1 5.8-5.3-2.8-5.3 2.8 1-5.8-4.2-4.1 5.9-.8L12 3Z" /></svg>;
    case "target":
      return <svg aria-hidden="true" {...common}><circle cx="12" cy="12" r="8" /><circle cx="12" cy="12" r="3" /><path d="M12 2v4" /><path d="M12 18v4" /><path d="M2 12h4" /><path d="M18 12h4" /></svg>;
    case "alert":
      return <svg aria-hidden="true" {...common}><path d="M12 4 3 20h18L12 4Z" /><path d="M12 10v4" /><path d="M12 17h.01" /></svg>;
    case "expand":
      return <svg aria-hidden="true" {...common}><path d="M8 3H3v5" /><path d="M3 3l6 6" /><path d="M16 3h5v5" /><path d="m21 3-6 6" /><path d="M8 21H3v-5" /><path d="m3 21 6-6" /><path d="M16 21h5v-5" /><path d="m21 21-6-6" /></svg>;
    case "arrowRight":
      return <svg aria-hidden="true" {...common}><path d="M5 12h14" /><path d="m13 6 6 6-6 6" /></svg>;
    case "x":
      return <svg aria-hidden="true" {...common}><path d="M6 6l12 12" /><path d="M18 6 6 18" /></svg>;
    default:
      return null;
  }
}
