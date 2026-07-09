import { describe, expect, it } from "vitest";
import {
  buildFundamentalMetrics,
  buildResearchSummary,
  buildTimingMetrics,
  buildTodayActionPlan,
  buildValuationMetrics,
  hasTrustedFundamentalData,
  hasTrustedPriceData
} from "../lib/research-metrics";
import type { AnalysisResponse } from "../lib/types";

function makeAnalysis(overrides: Partial<AnalysisResponse> = {}): AnalysisResponse {
  const base = {
    data_sources: {
      price: "finmind",
      fundamental: "finmind",
      news: "finmind"
    },
    research_decision: {
      stance: "worth_research",
      horizon: "3個月 - 2年",
      confidence: "中",
      summary: "基本面可研究，等待合理價。",
      next_action: "等待支撐附近再評估。",
      do_not_chase_reason: "",
      blockers: [],
      review_triggers: []
    },
    fundamental: {
      eps_ttm: 7.62,
      roe_ttm: 14.2,
      revenue_growth_yoy: 12.6
    },
    valuation_gate: {
      status: "watch",
      pe_ratio: 17.8,
      pe_band: "歷史分位 58%",
      sector_band: "同業中段",
      is_low_valuation: false,
      warning: "估值尚未便宜。"
    },
    timing_gate: {
      status: "watch",
      trend: "弱勢整理",
      support_zone: "100-102",
      no_chase_zone: "110 以上",
      entry_conditions: [],
      invalidation_price: 98
    },
    technical: {
      latest_close: 101.5,
      ma: {
        ma60: 103.2,
        ma120: 99.1
      },
      trend: "弱勢整理"
    }
  } as AnalysisResponse;

  return {
    ...base,
    ...overrides,
    data_sources: { ...base.data_sources, ...overrides.data_sources },
    research_decision: { ...base.research_decision, ...overrides.research_decision },
    valuation_gate: { ...base.valuation_gate, ...overrides.valuation_gate },
    timing_gate: { ...base.timing_gate, ...overrides.timing_gate },
    technical: { ...base.technical, ...overrides.technical },
    fundamental: { ...base.fundamental, ...overrides.fundamental }
  } as AnalysisResponse;
}

describe("research metric helpers", () => {
  it("does not show demo numbers before analysis data is loaded", () => {
    expect(buildResearchSummary(null).headline).toBe("等待分析資料");
    expect(buildTodayActionPlan(null).headline).toBe("今天先不判斷");
    expect(buildFundamentalMetrics(null).map((metric) => metric.value)).toEqual(["-", "-", "-"]);
    expect(buildValuationMetrics(null).map((metric) => metric.value)).toEqual(["-", "-", "不採用"]);
    expect(buildTimingMetrics(null).map((metric) => metric.value)).toEqual(["-", "-", "-", "不採用"]);
  });

  it("suppresses sample fundamentals and sample prices in judgment cards", () => {
    const sampleAnalysis = makeAnalysis({
      data_sources: {
        price: "sample",
        fundamental: "sample",
        news: "sample"
      }
    });

    expect(buildResearchSummary(sampleAnalysis).headline).toBe("只觀察：待真實基本面");
    expect(buildTodayActionPlan(sampleAnalysis).label).toBe("只觀察");
    expect(buildFundamentalMetrics(sampleAnalysis).map((metric) => metric.value)).toEqual(["-", "-", "-"]);
    expect(buildValuationMetrics(sampleAnalysis).map((metric) => metric.value)).toEqual(["-", "-", "不採用"]);
    expect(buildTimingMetrics(sampleAnalysis).map((metric) => metric.value)).toEqual(["-", "-", "-", "不採用"]);
    expect(hasTrustedPriceData(sampleAnalysis)).toBe(false);
  });

  it("uses trusted provider values when the sources are real", () => {
    const trustedAnalysis = makeAnalysis();

    expect(buildResearchSummary(trustedAnalysis).headline).toBe("值得研究 / 等便宜價");
    expect(buildFundamentalMetrics(trustedAnalysis).map((metric) => metric.value)).toEqual(["7.62", "14.2%", "+12.60%"]);
    expect(buildValuationMetrics(trustedAnalysis)[0].value).toBe("17.8x");
    expect(buildTimingMetrics(trustedAnalysis).slice(0, 3).map((metric) => metric.value)).toEqual(["101.5", "103.2", "99.1"]);
    expect(hasTrustedPriceData(trustedAnalysis)).toBe(true);
  });

  it("accepts official exchange fundamentals as trusted real data", () => {
    const officialAnalysis = makeAnalysis({
      data_sources: {
        price: "yahoo+twse-realtime",
        fundamental: "twse-openapi",
        news: "unavailable"
      }
    });

    expect(hasTrustedFundamentalData(officialAnalysis)).toBe(true);
    expect(buildResearchSummary(officialAnalysis).headline).toBe("值得研究 / 等便宜價");
    expect(buildFundamentalMetrics(officialAnalysis)[0].detail).toBe("TWSE 官方真實資料");
  });

  it("summarizes wait-price and avoid decisions without buy wording", () => {
    const waitPrice = makeAnalysis({
      research_decision: {
        stance: "wait_better_price",
        horizon: "3個月 - 2年",
        confidence: "中",
        next_action: "等待支撐附近再研究。",
        summary: "估值還沒有便宜到足夠安全邊際。",
        do_not_chase_reason: "估值沒有安全邊際前不追高。",
        blockers: [],
        review_triggers: []
      },
      price_plan: {
        research_price: 98,
        watch_price: 92,
        invalidation_price: 88,
        position_size_hint: "0-10%，小部位研究"
      }
    });
    const avoid = makeAnalysis({
      research_decision: {
        stance: "avoid",
        horizon: "3個月 - 2年",
        confidence: "低",
        next_action: "先排除，等基本面改善再回頭看。",
        summary: "核心條件不符合。",
        do_not_chase_reason: "核心條件不符合時不追。",
        blockers: ["基本面不符合"],
        review_triggers: []
      }
    });

    expect(buildTodayActionPlan(waitPrice).label).toBe("等便宜");
    expect(buildTodayActionPlan(waitPrice).headline).toContain("不追高");
    expect(buildTodayActionPlan(waitPrice).invalidation).toContain("98.00");
    expect(buildTodayActionPlan(avoid).label).toBe("排除");
    expect(buildTodayActionPlan(avoid).tone).toBe("loss");
  });
});
