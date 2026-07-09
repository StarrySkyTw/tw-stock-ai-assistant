import { formatNumber } from "./format";
import { hasTrustedSource, sourceQualityLabel } from "./market-scan";
import type { AnalysisResponse, GateStatus, ResearchStance } from "./types";

export type GateMetricTone = "gain" | "warn" | "loss" | "neutral";

export type GateMetric = {
  label: string;
  value: string;
  detail: string;
  tone?: GateMetricTone;
};

export type ResearchSummary = {
  headline: string;
  horizon: string;
  nextActions: string[];
  noChase: string;
};

export type TodayActionPlan = {
  label: string;
  headline: string;
  detail: string;
  tone: GateMetricTone;
  primaryAction: string;
  waitFor: string;
  invalidation: string;
  noChase: string;
};

const WAITING_SUMMARY: ResearchSummary = {
  headline: "等待分析資料",
  horizon: "尚未同步",
  nextActions: ["先更新分析資料", "確認價格、基本面與新聞來源", "資料不足前不要把結論當成實盤依據"],
  noChase: "資料尚未同步前不判斷買點；先確認真實資料來源與關鍵支撐。"
};

const SAMPLE_DETAIL = "未接入可驗證資料，不採用";
const WAITING_DETAIL = "等待真實資料";

export function buildResearchSummary(analysis: AnalysisResponse | null): ResearchSummary {
  if (!analysis) return WAITING_SUMMARY;

  if (!hasTrustedFundamentalData(analysis)) {
    return {
      headline: "只觀察：待真實基本面",
      horizon: analysis.research_decision.horizon || "3個月 - 2年",
      nextActions: normalizeList(analysis.research_decision.review_triggers, [
        "補上官方或 FinMind 基本面後再判斷",
        "只檢查價位與 K 線，不採用 EPS、PE、ROE",
        "等資料可信度提高後再進入研究清單"
      ]),
      noChase:
        analysis.research_decision.do_not_chase_reason ||
        "基本面不是可信資料時，不追價、不用估值倍數下結論。"
    };
  }

  const stance = researchStanceLabel(analysis.research_decision.stance);
  return {
    headline: analysis.research_decision.stance === "worth_research" ? "值得研究 / 等便宜價" : stance,
    horizon: analysis.research_decision.horizon || "3個月 - 2年",
    nextActions: normalizeList(analysis.research_decision.review_triggers, [
      "持續追蹤基本面與營收變化",
      "等待估值進入合理區間",
      "觀察均線結構與量能變化"
    ]),
    noChase:
      analysis.research_decision.do_not_chase_reason ||
      "目前估值與技術面若未出現具備優勢的買點，避免追高，耐心等待更好的風報比時機。"
  };
}

export function buildTodayActionPlan(analysis: AnalysisResponse | null): TodayActionPlan {
  if (!analysis) {
    return {
      label: "等資料",
      headline: "今天先不判斷",
      detail: "價格、基本面、估值與 K 線尚未同步，先不要把任何結論當成研究依據。",
      tone: "neutral",
      primaryAction: "先按重新整理或確認資料來源，等核心資料回來後再看。",
      waitFor: "等待價格、基本面、估值、K 線四個核心資料同步。",
      invalidation: "尚未建立失效條件。",
      noChase: "資料不足時不追價、不建立研究假設。"
    };
  }

  const trustedFundamental = hasTrustedFundamentalData(analysis);
  const trustedPrice = hasTrustedPriceData(analysis);
  const decision = analysis.research_decision;
  const timing = analysis.timing_gate;
  const plan = analysis.price_plan;

  if (!trustedFundamental) {
    return {
      label: "只觀察",
      headline: "只觀察，先補真實基本面",
      detail: decision.summary || "基本面來源不是可驗證資料，估值與品質結論先不採用。",
      tone: "warn",
      primaryAction: decision.next_action || "先確認 EPS、ROE、營收成長是否來自官方或 FinMind。",
      waitFor: "等官方或 FinMind 基本面接上後，再判斷是否值得研究。",
      invalidation: trustedPrice ? formatInvalidation(timing.invalidation_price) : "等待真實日 K 後再設定失效價。",
      noChase: decision.do_not_chase_reason || "基本面未驗證前，不用 PE、PB 或 ROE 當行動理由。"
    };
  }

  const stance = decision.stance;
  const waitFor = trustedPrice
    ? firstNonEmpty(timing.entry_conditions) ||
      firstNonEmpty([formatResearchPrice(plan?.research_price), timing.support_zone]) ||
      "等待支撐、估值與量價條件同時改善。"
    : "等待真實日 K，同步支撐、壓力與失效價。";

  return {
    label: todayActionLabel(stance),
    headline: todayActionHeadline(stance),
    detail: decision.summary || todayActionDetail(stance),
    tone: todayActionTone(stance),
    primaryAction: decision.next_action || todayActionPrimaryAction(stance),
    waitFor,
    invalidation: trustedPrice ? formatInvalidation(timing.invalidation_price) : "等待真實日 K 後再設定失效價。",
    noChase:
      decision.do_not_chase_reason ||
      (trustedPrice && timing.no_chase_zone && timing.no_chase_zone !== "未觸發禁追條件"
        ? `不要追到 ${timing.no_chase_zone}。`
        : "沒有接近支撐或估值優勢時，只觀察不追高。")
  };
}

export function buildFundamentalMetrics(analysis: AnalysisResponse | null): GateMetric[] {
  const trusted = hasTrustedFundamentalData(analysis);
  const eps = trusted ? readNumericMetric(analysis?.fundamental, ["eps_ttm", "eps", "EPS"]) : null;
  const roe = trusted ? readNumericMetric(analysis?.fundamental, ["roe_ttm", "roe", "ROE"]) : null;
  const revenueGrowth = trusted
    ? readNumericMetric(analysis?.fundamental, ["revenue_growth_yoy", "revenue_yoy", "sales_growth_yoy"])
    : null;
  const fallbackDetail = analysis ? SAMPLE_DETAIL : WAITING_DETAIL;
  const sourceDetail = trusted ? `${sourceQualityLabel(analysis?.data_sources?.fundamental)}真實資料` : fallbackDetail;

  return [
    {
      label: "EPS (TTM)",
      value: eps === null ? "-" : formatNumber(eps, 2),
      detail: eps === null ? fallbackDetail : sourceDetail,
      tone: eps === null ? "neutral" : eps > 0 ? "gain" : "loss"
    },
    {
      label: "ROE (TTM)",
      value: roe === null ? "-" : `${formatNumber(roe, 1)}%`,
      detail: roe === null ? fallbackDetail : sourceDetail,
      tone: roe === null ? "neutral" : roe >= 10 ? "gain" : "warn"
    },
    {
      label: "營收成長 YoY",
      value: revenueGrowth === null ? "-" : signedPercent(revenueGrowth),
      detail: revenueGrowth === null ? fallbackDetail : sourceDetail,
      tone: revenueGrowth === null ? "neutral" : revenueGrowth > 0 ? "gain" : "loss"
    }
  ];
}

export function buildValuationMetrics(analysis: AnalysisResponse | null): GateMetric[] {
  const trusted = hasTrustedFundamentalData(analysis);
  const pe = trusted ? analysis?.valuation_gate.pe_ratio ?? null : null;
  const fallbackDetail = analysis ? SAMPLE_DETAIL : WAITING_DETAIL;
  const bandText =
    trusted && analysis?.valuation_gate.pe_band && analysis.valuation_gate.pe_band !== "unknown"
      ? analysis.valuation_gate.pe_band
      : fallbackDetail;
  const sectorBand = trusted && analysis?.valuation_gate.sector_band ? analysis.valuation_gate.sector_band : fallbackDetail;
  const warning = trusted ? analysis?.valuation_gate.warning || valuationStatusLabel(analysis?.valuation_gate.status) : fallbackDetail;

  return [
    { label: "本益比 (TTM)", value: pe === null ? "-" : `${formatNumber(pe, 1)}x`, detail: bandText, tone: pe === null ? "neutral" : undefined },
    { label: "產業估值區間", value: trusted ? sectorBand : "-", detail: trusted ? "用來比較是否偏貴" : fallbackDetail },
    { label: "估值結論", value: trusted ? valuationStatusLabel(analysis?.valuation_gate.status) : "不採用", detail: warning }
  ];
}

export function buildTimingMetrics(analysis: AnalysisResponse | null): GateMetric[] {
  const trusted = hasTrustedPriceData(analysis);
  const close = trusted ? analysis?.technical.latest_close ?? null : null;
  const ma60 = trusted ? readMa(analysis, 60) : null;
  const ma120 = trusted ? readMa(analysis, 120) : null;
  const fallbackDetail = analysis ? "價格為示範資料，不採用" : WAITING_DETAIL;

  return [
    { label: "收盤價", value: close === null ? "-" : formatNumber(close, 1), detail: close === null ? fallbackDetail : "最新日 K 收盤" },
    {
      label: "MA60",
      value: ma60 === null ? "-" : formatNumber(ma60, 1),
      detail: close !== null && ma60 !== null ? percentDistance(close, ma60) : fallbackDetail
    },
    {
      label: "MA120",
      value: ma120 === null ? "-" : formatNumber(ma120, 1),
      detail: close !== null && ma120 !== null ? percentDistance(close, ma120) : fallbackDetail
    },
    {
      label: "趨勢判斷",
      value: trusted ? analysis?.timing_gate.trend || analysis?.technical.trend || "-" : "不採用",
      detail: trusted ? "搭配支撐、壓力與失效價" : fallbackDetail
    }
  ];
}

export function hasTrustedFundamentalData(analysis: AnalysisResponse | null): boolean {
  return hasTrustedSource(analysis?.data_sources?.fundamental, "fundamental");
}

export function hasTrustedPriceData(analysis: AnalysisResponse | null): boolean {
  return hasTrustedSource(analysis?.data_sources?.price, "price");
}

function readNumericMetric(source: AnalysisResponse["fundamental"] | undefined, keys: string[]) {
  if (!source) return null;
  const metrics = source as Record<string, unknown>;
  for (const key of keys) {
    const value = metrics[key];
    if (typeof value === "number" && Number.isFinite(value)) return value;
    if (typeof value === "string") {
      const parsed = Number(value.replace("%", ""));
      if (Number.isFinite(parsed)) return parsed;
    }
  }
  return null;
}

function readMa(analysis: AnalysisResponse | null, period: number) {
  const ma = analysis?.technical.ma;
  if (!ma) return null;
  return ma[`ma${period}`] ?? ma[String(period)] ?? ma[`MA${period}`] ?? null;
}

function normalizeList(value: string[], fallback: string[]) {
  const cleaned = value.map((item) => item.trim()).filter(Boolean).slice(0, 3);
  return cleaned.length ? cleaned : fallback;
}

function todayActionLabel(stance: ResearchStance) {
  const labels: Record<ResearchStance, string> = {
    worth_research: "可研究",
    wait_better_price: "等便宜",
    watch: "觀察",
    avoid: "排除",
    reduce_risk: "降風險"
  };
  return labels[stance];
}

function todayActionHeadline(stance: ResearchStance) {
  const labels: Record<ResearchStance, string> = {
    worth_research: "可研究，但等條件到位",
    wait_better_price: "等便宜價，不追高",
    watch: "先觀察，等待條件改善",
    avoid: "排除，暫不投入研究",
    reduce_risk: "降低風險，重算假設"
  };
  return labels[stance];
}

function todayActionDetail(stance: ResearchStance) {
  const labels: Record<ResearchStance, string> = {
    worth_research: "基本面與估值可列入研究，但仍要等 K 線與風報比確認。",
    wait_better_price: "標的可追蹤，但目前價格或估值還沒有給出足夠安全邊際。",
    watch: "條件還不完整，今天先觀察資料變化。",
    avoid: "核心條件不符合，先把研究資源留給更清楚的標的。",
    reduce_risk: "已有假設轉弱訊號，先降低風險並重新檢查關鍵條件。"
  };
  return labels[stance];
}

function todayActionPrimaryAction(stance: ResearchStance) {
  const labels: Record<ResearchStance, string> = {
    worth_research: "加入研究候選，等支撐、估值或量價條件確認。",
    wait_better_price: "保留觀察，不追價，等估值或價格回到計畫區。",
    watch: "維持觀察，等基本面、估值或 K 線其中一項轉強。",
    avoid: "先排除，除非基本面或風險條件明顯改善。",
    reduce_risk: "先檢查失效條件與部位風險，避免擴大研究假設。"
  };
  return labels[stance];
}

function todayActionTone(stance: ResearchStance): GateMetricTone {
  if (stance === "worth_research") return "gain";
  if (stance === "avoid" || stance === "reduce_risk") return "loss";
  return "warn";
}

function researchStanceLabel(stance: ResearchStance) {
  const labels: Record<ResearchStance, string> = {
    worth_research: "值得研究",
    wait_better_price: "等待便宜價",
    watch: "觀察",
    avoid: "避開",
    reduce_risk: "降低風險"
  };
  return labels[stance];
}

function firstNonEmpty(values: Array<string | null | undefined>) {
  return values.find((value) => typeof value === "string" && value.trim())?.trim() ?? "";
}

function formatResearchPrice(value: number | null | undefined) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "";
  return `等研究價 ${formatNumber(value, 2)} 附近再評估。`;
}

function formatInvalidation(value: number | null | undefined) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "尚未建立失效價，先不做進一步假設。";
  return `跌破 ${formatNumber(value, 2)} 需要重算研究假設。`;
}

function valuationStatusLabel(status: GateStatus | undefined) {
  const labels: Record<GateStatus, string> = {
    pass: "合理",
    watch: "待觀察",
    fail: "偏貴或風險高",
    not_applicable: "不適用",
    unknown: "資料不足"
  };
  return status ? labels[status] : "資料不足";
}

function signedPercent(value: number) {
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${formatNumber(value, 2)}%`;
}

function percentDistance(value: number, base: number) {
  if (!base) return "-";
  return signedPercent(((value - base) / base) * 100);
}
