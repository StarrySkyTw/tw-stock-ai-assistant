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

