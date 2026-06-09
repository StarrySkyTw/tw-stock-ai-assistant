export type Light = "green" | "yellow" | "red";
export type MarketPhase = "pre_open" | "regular" | "post_close" | "closed";

export type MarketRefreshInfo = {
  now: string;
  timezone: "Asia/Taipei" | string;
  market_phase: MarketPhase;
  label: string;
  is_trading_day: boolean;
  is_regular_session: boolean;
  is_live_refresh: boolean;
  refresh_interval_seconds: number;
  next_refresh_at: string;
  message: string;
};

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
  confidence: string;
  research_position_size: string;
  score_breakdown: Record<string, number>;
  checklist: Record<string, string[]>;
  scenarios: DecisionScenario[];
  next_review_triggers: string[];
  data_quality: string[];
  ai_snapshot_prompt: string;
};

export type MarginSummary = {
  latest_balance: number | null;
  five_day_change: number;
  five_day_change_pct: number | null;
  twenty_day_change: number;
  twenty_day_change_pct: number | null;
  short_margin_ratio: number | null;
  status: string;
  signals: string[];
};

export type StrategyCheck = {
  label: string;
  status: "pass" | "watch" | "fail";
  detail: string;
};

export type StrategyJudgement = {
  stance: "prepare_entry" | "hold_steady" | "wait" | "reduce_risk";
  headline: string;
  action: string;
  timing_score: number;
  chip_cleanliness: string;
  margin_trend: string;
  market_guard: string;
  checks: StrategyCheck[];
  entry_triggers: string[];
  defensive_triggers: string[];
};

export type AnalysisResponse = {
  symbol: string;
  name?: string | null;
  analysis_date: string;
  generated_at: string;
  refresh: MarketRefreshInfo;
  data_sources: Record<string, string>;
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
    volume_ratio?: number | null;
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
  margin: MarginSummary;
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
  strategy_judgement: StrategyJudgement;
  disclaimer: string;
};

export type ChartResponse = {
  symbol: string;
  name?: string | null;
  range: string;
  figure: Record<string, unknown>;
};

export type AiPickFactor = {
  kind: string;
  label: string;
  detail: string;
  tone: "positive" | "neutral" | "risk";
};

export type AiMarketSnapshot = {
  status: string;
  score: number;
  light: Light;
  reasons: string[];
  indicators: Record<string, number | null>;
  generated_at: string;
  market_date: string;
  refresh: MarketRefreshInfo;
};

export type AiStockPick = {
  rank: number;
  symbol: string;
  name?: string | null;
  industry: string;
  latest_close: number;
  recommendation: string;
  selection_score: number;
  adjusted_score: number;
  bias: "bullish" | "neutral" | "bearish";
  confidence: string;
  strategy_judgement: StrategyJudgement;
  thesis: string;
  bullish_factors: AiPickFactor[];
  risk_factors: AiPickFactor[];
  score_breakdown: Record<string, number>;
  data_quality: string[];
  source_notes: string[];
};

export type AiStockPicksResponse = {
  generated_at: string;
  universe: string[];
  refresh: MarketRefreshInfo;
  market_snapshot: AiMarketSnapshot;
  top_picks: AiStockPick[];
  selection_logic: string[];
  watch_notes: string[];
  disclaimer: string;
};

export type WatchlistItem = {
  id: number;
  symbol: string;
  note?: string | null;
  target_price?: number | null;
  stop_price?: number | null;
  created_at: string;
};

export type PositionItem = {
  id: number;
  symbol: string;
  name?: string | null;
  entry_date?: string | null;
  entry_price: number;
  quantity: number;
  highest_price?: number | null;
  status: "open" | "closed" | string;
  created_at: string;
  updated_at: string;
};
