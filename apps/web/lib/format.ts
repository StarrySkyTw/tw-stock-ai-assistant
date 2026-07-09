export function formatNumber(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return value.toLocaleString("zh-TW", {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits
  });
}

export function scoreClass(score: number): string {
  if (score >= 75) return "text-gain";
  if (score >= 60) return "text-warn";
  return "text-loss";
}

export function formatGateStatus(status: string): string {
  const labels: Record<string, string> = {
    pass: "通過",
    watch: "觀察",
    fail: "未通過",
    not_applicable: "不適用",
    unknown: "資料不足"
  };
  return labels[status] ?? status;
}

export function formatResearchStance(stance: string): string {
  const labels: Record<string, string> = {
    worth_research: "值得研究",
    wait_better_price: "等便宜價",
    watch: "觀察",
    avoid: "避開",
    reduce_risk: "降低風險"
  };
  return labels[stance] ?? stance;
}

export function formatNoChase(reason?: string | null): string {
  return reason ? "禁止追高" : "未觸發禁追";
}
