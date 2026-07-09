import { describe, expect, it } from "vitest";
import { formatGateStatus, formatNoChase, formatNumber, formatResearchStance, scoreClass } from "../lib/format";

describe("format helpers", () => {
  it("formats nullable numbers", () => {
    expect(formatNumber(null)).toBe("-");
    expect(formatNumber(12.345, 1)).toBe("12.3");
  });

  it("maps score classes", () => {
    expect(scoreClass(80)).toBe("text-gain");
    expect(scoreClass(65)).toBe("text-warn");
    expect(scoreClass(30)).toBe("text-loss");
  });

  it("formats research gate labels", () => {
    expect(formatGateStatus("pass")).toBe("通過");
    expect(formatGateStatus("not_applicable")).toBe("不適用");
    expect(formatResearchStance("wait_better_price")).toBe("等便宜價");
  });

  it("formats no-chase status", () => {
    expect(formatNoChase("RSI 過熱")).toBe("禁止追高");
    expect(formatNoChase(null)).toBe("未觸發禁追");
  });
});
