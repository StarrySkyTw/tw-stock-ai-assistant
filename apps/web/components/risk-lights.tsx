import type { RiskLights } from "@/lib/types";

const colorClass = {
  green: "border-gain/40 bg-gain/10 text-gain",
  yellow: "border-warn/40 bg-warn/10 text-warn",
  red: "border-loss/40 bg-loss/10 text-loss"
};

export function RiskLightBadges({ lights }: { lights: RiskLights }) {
  const items = [
    ["大盤趨勢", lights.market_trend],
    ["法人籌碼", lights.institutional_flow],
    ["技術面", lights.technical],
    ["風險", lights.risk_indicator],
    ["綜合", lights.composite]
  ] as const;

  return (
    <div className="grid grid-cols-2 gap-2 md:grid-cols-5">
      {items.map(([label, light]) => (
        <div key={label} className={`rounded-md border px-3 py-2 ${colorClass[light]}`}>
          <div className="text-xs text-muted">{label}</div>
          <div className="mt-1 text-lg font-semibold">{lightLabel(light)}</div>
        </div>
      ))}
    </div>
  );
}

function lightLabel(light: keyof typeof colorClass) {
  if (light === "green") return "綠燈";
  if (light === "red") return "紅燈";
  return "黃燈";
}
