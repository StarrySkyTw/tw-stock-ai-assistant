export type Light = "green" | "yellow" | "red";
export type MarketPhase = "pre_open" | "regular" | "post_close" | "closed";
export type GateStatus = "pass" | "watch" | "fail" | "not_applicable" | "unknown";
export type ResearchStance = "worth_research" | "wait_better_price" | "watch" | "avoid" | "reduce_risk";
export type CandidateStatus = "qualified_research" | "wait_price" | "watch_only" | "reject";
export type BreakoutStatus =
  | "ready_setup"
  | "wait_confirmation"
  | "wait_pullback"
  | "too_extended"
  | "not_ready"
  | "data_limited";

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

export type MarketIndexQuote = {
  symbol: string;
  name: string;
  value: number;
  change: number;
  change_percent: number;
  volume?: number | null;
  source: string;
  updated_at: string;
};

export type MarketRiskResponse = {
  status: string;
  score: number;
  lights: RiskLights;
  indicators: Record<string, number | null>;
  reasons: string[];
  generated_at: string;
  market_date: string;
  refresh: MarketRefreshInfo;
};

export type MarketOverviewResponse = {
  taiex_state: string;
  otc_state: string;
  market_status: string;
  heavyweight_impact: Record<string, number>;
  taiex_quote?: MarketIndexQuote | null;
  risk: MarketRiskResponse;
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

export type FundamentalGate = {
  status: GateStatus;
  grade: string;
  passed: boolean;
  failed_reasons: string[];
  metrics: Record<string, number | null>;
};

export type ValuationGate = {
  status: GateStatus;
  pe_ratio: number | null;
  pe_band: string;
  sector_band: string;
  is_low_valuation: boolean;
  warning?: string | null;
};

export type TimingGate = {
  status: GateStatus;
  trend: string;
  support_zone: string;
  no_chase_zone: string;
  entry_conditions: string[];
  invalidation_price: number | null;
};

export type PricePlan = {
  research_price: number | null;
  watch_price: number | null;
  invalidation_price: number | null;
  position_size_hint: string;
};

export type ResearchDecision = {
  stance: ResearchStance;
  horizon: string;
  confidence: "高" | "中" | "低";
  summary: string;
  next_action: string;
  do_not_chase_reason?: string | null;
  blockers: string[];
  review_triggers: string[];
};

export type BreakoutPotential = {
  status: BreakoutStatus;
  label: string;
  score: number;
  confidence: "高" | "中" | "低";
  headline: string;
  thesis: string;
  leading_signals: string[];
  missing_confirmations: string[];
  trigger_conditions: string[];
  invalidation: string;
  no_chase_warning?: string | null;
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

export type KlineAnalysis = {
  headline: string;
  trend: string;
  support_levels: string[];
  resistance_levels: string[];
  strategy_notes: string[];
  invalidation: string[];
};

export type AnalysisResponse = {
  symbol: string;
  name?: string | null;
  industry?: string | null;
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
    error?: string | null;
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
  research_decision: ResearchDecision;
  fundamental_gate: FundamentalGate;
  valuation_gate: ValuationGate;
  timing_gate: TimingGate;
  price_plan: PricePlan;
  strategy_judgement: StrategyJudgement;
  breakout_potential: BreakoutPotential;
  kline_analysis: KlineAnalysis;
  disclaimer: string;
};

export type ChartResponse = {
  symbol: string;
  name?: string | null;
  range: string;
  figure: Record<string, unknown>;
};

export type IntradayPoint = {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

export type IntradayResponse = {
  symbol: string;
  name?: string | null;
  source: string;
  interval: string;
  trade_date?: string | null;
  previous_close?: number | null;
  open?: number | null;
  high?: number | null;
  low?: number | null;
  latest?: number | null;
  change?: number | null;
  change_percent?: number | null;
  volume?: number | null;
  updated_at: string;
  points: IntradayPoint[];
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
  latest_close?: number | null;
  recommendation: string;
  selection_score: number;
  adjusted_score: number;
  candidate_status: CandidateStatus;
  data_quality_score: number;
  score_cap_reason?: string | null;
  bias: "bullish" | "neutral" | "bearish";
  confidence: string;
  strategy_judgement: StrategyJudgement;
  research_decision: ResearchDecision;
  fundamental_gate: FundamentalGate;
  valuation_gate: ValuationGate;
  timing_gate: TimingGate;
  price_plan: PricePlan;
  breakout_potential: BreakoutPotential;
  thesis: string;
  bullish_factors: AiPickFactor[];
  risk_factors: AiPickFactor[];
  score_breakdown: Record<string, number>;
  data_quality: string[];
  source_notes: string[];
  data_sources: Record<string, string>;
  blockers: string[];
  why_ranked: string[];
  no_chase_reason?: string | null;
  future_outlook?: PositionFutureOutlook | null;
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

export type MarketScanCandidate = {
  rank: number;
  symbol: string;
  name?: string | null;
  industry: string;
  latest_close?: number | null;
  candidate_status: CandidateStatus;
  selection_score: number;
  adjusted_score: number;
  data_quality_score: number;
  score_cap_reason?: string | null;
  research_decision: ResearchDecision;
  fundamental_gate: FundamentalGate;
  valuation_gate: ValuationGate;
  timing_gate: TimingGate;
  price_plan: PricePlan;
  breakout_potential: BreakoutPotential;
  data_sources: Record<string, string>;
  blockers: string[];
  why_ranked: string[];
  no_chase_reason?: string | null;
  future_outlook?: PositionFutureOutlook | null;
};

export type MarketScanResponse = {
  scan_id: number;
  generated_at: string;
  universe_count: number;
  completed_count: number;
  failed_count: number;
  universe_source: string;
  is_full_market: boolean;
  data_quality_summary: Record<string, number>;
  top_candidates: MarketScanCandidate[];
  failed_symbols: string[];
};

export type MarketScanRequest = {
  universe?: string[];
  limit?: number;
  max_symbols?: number;
};

export type WatchlistItem = {
  id: number;
  symbol: string;
  name?: string | null;
  lookup_status?: "verified" | "unknown_symbol";
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

export type PositionDecisionAction = "sell" | "reduce" | "hold" | "add" | "watch";

export type PositionDecisionSignal = {
  kind: string;
  label: string;
  detail: string;
  tone: "positive" | "neutral" | "risk";
  priority: number;
};

export type PositionFutureScenario = {
  name: string;
  probability: number;
  condition: string;
  action: string;
  trigger: string;
  invalidation: string;
  tone: "positive" | "neutral" | "risk";
};

export type PositionSwingPlan = {
  stance: string;
  horizon: string;
  entry_zone: string;
  add_rule: string;
  trim_rule: string;
  stop_rule: string;
  review_rule: string;
  position_size_hint: string;
};

export type PositionFutureOutlook = {
  label: string;
  horizon: string;
  expectation_gap: string;
  leading_indicators: string[];
  scenarios: PositionFutureScenario[];
  swing_plan: PositionSwingPlan;
};

export type PositionDecisionItem = {
  position: PositionItem;
  latest_close?: number | null;
  cost_basis: number;
  market_value?: number | null;
  unrealized_pnl?: number | null;
  unrealized_pnl_percent?: number | null;
  action: PositionDecisionAction;
  action_label: string;
  confidence: "高" | "中" | "低";
  headline: string;
  rationale: string;
  priority_factors: PositionDecisionSignal[];
  bullish_factors: PositionDecisionSignal[];
  risk_factors: PositionDecisionSignal[];
  future_outlook?: PositionFutureOutlook | null;
  next_review_triggers: string[];
  data_quality: string[];
};
