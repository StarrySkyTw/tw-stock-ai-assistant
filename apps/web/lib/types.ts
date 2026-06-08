export type Light = "green" | "yellow" | "red";

export type RiskLights = {
  market_trend: Light;
  institutional_flow: Light;
  technical: Light;
  risk_indicator: Light;
  composite: Light;
  table: Array<{ item: string; status: string }>;
};

export type DecisionScenario = {
  name: string;
  condition: string;
  action: string;
  invalidation: string;
};

export type DecisionPlan = {
  headline: string;
  bias: "bullish" | "neutral" | "bearish";
  action: string;
  confidence: "高" | "中" | "低";
  research_position_size: string;
  score_breakdown: Record<string, number>;
  checklist: Record<string, string[]>;
  scenarios: DecisionScenario[];
  next_review_triggers: string[];
  data_quality: string[];
  ai_snapshot_prompt: string;
};

export type AnalysisResponse = {
  symbol: string;
  name?: string | null;
  analysis_date: string;
  raw_score: number;
  adjusted_score: number;
  recommendation: string;
  reasons: string[];
  risks: string[];
  technical: {
    latest_close: number;
    ma: Record<string, number | null>;
    rsi: Record<string, number | null>;
    kd: Record<string, number | null>;
    macd: Record<string, number | null>;
    bollinger: Record<string, number | null>;
    atr14: number | null;
    trend: string;
    signals: string[];
  };
  institutional: {
    five_day_total: number;
    twenty_day_total: number;
    sixty_day_total: number;
    foreign_trend: string;
    investment_trust_trend: string;
    dealer_trend: string;
    signals: string[];
  };
  fundamental: Record<string, number | string[] | null>;
  sentiment: {
    score: number;
    label: string;
    summary: string;
    headlines: string[];
    model?: string | null;
  };
  stop_loss: {
    fixed_5_percent: number | null;
    fixed_8_percent: number | null;
    fixed_10_percent: number | null;
    atr_stop: number | null;
    ma20_stop_triggered: boolean;
    ma60_stop_triggered: boolean;
    notes: string[];
  };
  trailing_take_profit: {
    current_take_profit_price: number | null;
    atr_multiplier: number;
    estimated_return_percent: number | null;
    risk_reward_ratio: number | null;
    highest_price_used: number | null;
    is_estimated_highest_price: boolean;
  };
  risk_lights: RiskLights;
  decision_plan: DecisionPlan;
  disclaimer: string;
};

export type ChartResponse = {
  symbol: string;
  name?: string | null;
  range: string;
  figure: Record<string, unknown>;
};
