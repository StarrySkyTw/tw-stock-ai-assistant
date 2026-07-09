import type { BreakoutStatus, CandidateStatus } from "./types";

export const MARKET_SCAN_STATUS_OPTIONS: Array<["all" | CandidateStatus, string]> = [
  ["all", "全部"],
  ["qualified_research", "合格研究"],
  ["wait_price", "等便宜價"],
  ["watch_only", "只觀察"],
  ["reject", "排除"]
];

export function candidateStatusLabel(status: CandidateStatus): string {
  const labels: Record<CandidateStatus, string> = {
    qualified_research: "合格研究",
    wait_price: "等便宜價",
    watch_only: "只觀察",
    reject: "排除"
  };
  return labels[status];
}

export function candidateStatusTone(status: CandidateStatus): "gain" | "warn" | "loss" | "neutral" {
  if (status === "qualified_research") return "gain";
  if (status === "wait_price") return "warn";
  if (status === "reject") return "loss";
  return "neutral";
}

export function candidateStatusDescription(status: CandidateStatus): string {
  const descriptions: Record<CandidateStatus, string> = {
    qualified_research: "基本面是真實資料且通過，估值合理，K 線沒有追高風險。",
    wait_price: "基本面品質可研究，但估值或價位還不夠有優勢。",
    watch_only: "資料不足、時機不乾淨或仍需人工複查。",
    reject: "基本面、趨勢或市場風險有明確阻擋。"
  };
  return descriptions[status];
}

export function breakoutStatusTone(status: BreakoutStatus): "gain" | "warn" | "loss" | "neutral" {
  if (status === "ready_setup") return "gain";
  if (status === "wait_confirmation" || status === "wait_pullback") return "warn";
  if (status === "too_extended" || status === "not_ready") return "loss";
  return "neutral";
}

export function breakoutStatusLabel(status: BreakoutStatus): string {
  const labels: Record<BreakoutStatus, string> = {
    ready_setup: "高潛力準備",
    wait_confirmation: "等待確認",
    wait_pullback: "等便宜價",
    too_extended: "過熱禁追",
    not_ready: "條件未齊",
    data_limited: "資料不足"
  };
  return labels[status];
}

export function sourceQualityLabel(source: string | undefined): string {
  if (!source) return "未知";
  const normalized = source.toLowerCase();
  if (normalized.includes("yahoo") && normalized.includes("twse")) return "Yahoo+TWSE";
  if (source === "finmind") return "FinMind";
  if (normalized === "twse-openapi") return "TWSE 官方";
  if (normalized === "tpex-openapi") return "TPEX 官方";
  if (normalized === "twse-t86") return "TWSE 法人";
  if (normalized === "tpex-insti") return "TPEX 法人";
  if (normalized === "twse-margin") return "TWSE 融資券";
  if (normalized === "tpex-margin") return "TPEX 融資券";
  if (normalized === "tdcc") return "TDCC 集保";
  if (normalized === "twse-material") return "TWSE 重大訊息";
  if (normalized === "tpex-material") return "TPEX 重大訊息";
  if (normalized.includes("twse")) return "TWSE";
  if (normalized.includes("tpex")) return "TPEX";
  if (normalized.includes("yahoo")) return "Yahoo";
  if (normalized === "unavailable") return "未接入";
  if (normalized.includes("sample")) return "示範資料";
  return source;
}

export function hasTrustedSource(source: string | undefined, kind: string): boolean {
  const normalized = source?.toLowerCase() ?? "";
  if (!normalized || normalized.includes("sample") || normalized === "unavailable") return false;
  if (kind === "fundamental") return ["finmind", "twse-openapi", "tpex-openapi"].some((item) => normalized.includes(item));
  if (kind === "institutional") return ["finmind", "twse-t86", "tpex-insti"].some((item) => normalized.includes(item));
  if (kind === "margin") return ["finmind", "twse-margin", "tpex-margin"].some((item) => normalized.includes(item));
  if (kind === "price") return ["finmind", "twse", "yahoo"].some((item) => normalized.includes(item));
  if (kind === "shareholding") return normalized.includes("finmind") || normalized.includes("tdcc");
  if (kind === "news") return normalized.includes("finmind") || normalized.includes("twse-material") || normalized.includes("tpex-material");
  return false;
}

export function universeSourceLabel(source: string | undefined): string {
  const labels: Record<string, string> = {
    custom: "自訂清單",
    default_watchlist: "預設觀察池",
    finmind_limited: "FinMind 限量清單",
    finmind_twse_otc: "TWSE/OTC 全市場",
    unknown: "未知範圍"
  };
  return labels[source || "unknown"] ?? source ?? "未知範圍";
}
