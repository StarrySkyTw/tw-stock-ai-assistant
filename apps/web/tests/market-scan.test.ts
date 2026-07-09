import { describe, expect, it } from "vitest";
import {
  breakoutStatusLabel,
  breakoutStatusTone,
  candidateStatusDescription,
  candidateStatusLabel,
  candidateStatusTone,
  sourceQualityLabel,
  universeSourceLabel
} from "../lib/market-scan";

describe("market scan helpers", () => {
  it("labels candidate statuses without buy-order wording", () => {
    expect(candidateStatusLabel("qualified_research")).toBe("合格研究");
    expect(candidateStatusLabel("wait_price")).toBe("等便宜價");
    expect(candidateStatusLabel("watch_only")).toBe("只觀察");
    expect(candidateStatusLabel("reject")).toBe("排除");
    expect(breakoutStatusLabel("ready_setup")).toBe("高潛力準備");
    expect(breakoutStatusTone("too_extended")).toBe("loss");
    expect(breakoutStatusTone("data_limited")).toBe("neutral");
  });

  it("keeps sample data visibly separate from trusted providers", () => {
    expect(sourceQualityLabel("finmind")).toBe("FinMind");
    expect(sourceQualityLabel("twse-openapi")).toBe("TWSE 官方");
    expect(sourceQualityLabel("tpex-insti")).toBe("TPEX 法人");
    expect(sourceQualityLabel("yahoo+twse-realtime")).toBe("Yahoo+TWSE");
    expect(sourceQualityLabel("tdcc")).toBe("TDCC 集保");
    expect(sourceQualityLabel("twse-material")).toBe("TWSE 重大訊息");
    expect(sourceQualityLabel("sample")).toBe("示範資料");
    expect(sourceQualityLabel("unavailable")).toBe("未接入");
    expect(candidateStatusTone("reject")).toBe("loss");
    expect(candidateStatusDescription("watch_only")).toContain("資料不足");
  });

  it("labels scan universe sources honestly", () => {
    expect(universeSourceLabel("default_watchlist")).toBe("預設觀察池");
    expect(universeSourceLabel("finmind_twse_otc")).toBe("TWSE/OTC 全市場");
  });
});
