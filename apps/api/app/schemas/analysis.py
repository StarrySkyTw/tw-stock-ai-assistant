from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Light = Literal["green", "yellow", "red"]
MarketPhase = Literal["pre_open", "regular", "post_close", "closed"]
GateStatus = Literal["pass", "watch", "fail", "not_applicable", "unknown"]
ResearchStance = Literal["worth_research", "wait_better_price", "watch", "avoid", "reduce_risk"]
CandidateStatus = Literal["qualified_research", "wait_price", "watch_only", "reject"]
BreakoutStatus = Literal[
    "ready_setup",
    "wait_confirmation",
    "wait_pullback",
    "too_extended",
    "not_ready",
    "data_limited",
]


class MarketRefreshInfo(BaseModel):
    now: datetime
    timezone: str
    market_phase: MarketPhase
    label: str
    is_trading_day: bool
    is_regular_session: bool
    is_live_refresh: bool
    refresh_interval_seconds: int
    next_refresh_at: datetime
    message: str


class TechnicalSummary(BaseModel):
    latest_close: float
    ma: dict[str, float | None]
    rsi: dict[str, float | None]
    kd: dict[str, float | None]
    macd: dict[str, float | None]
    bollinger: dict[str, float | None]
    atr14: float | None
    volume_ratio: float | None = None
    trend: str
    signals: list[str]


class InstitutionalSummary(BaseModel):
    five_day_total: float
    twenty_day_total: float
    sixty_day_total: float
    foreign_trend: str
    investment_trust_trend: str
    dealer_trend: str
    signals: list[str]


class MarginSummary(BaseModel):
    latest_balance: float | None
    five_day_change: float
    five_day_change_pct: float | None
    twenty_day_change: float
    twenty_day_change_pct: float | None
    short_margin_ratio: float | None
    status: str
    signals: list[str]


class FundamentalSummary(BaseModel):
    eps: float | None
    roe: float | None
    gross_margin: float | None
    operating_margin: float | None
    pe_ratio: float | None
    pb_ratio: float | None
    revenue_yoy: float | None
    revenue_mom: float | None
    signals: list[str]


class SentimentSummary(BaseModel):
    score: float
    label: str
    summary: str
    headlines: list[str]
    model: str | None = None
    error: str | None = None


class StopLossSummary(BaseModel):
    fixed_5_percent: float | None
    fixed_8_percent: float | None
    fixed_10_percent: float | None
    atr_stop: float | None
    ma20_stop_triggered: bool
    ma60_stop_triggered: bool
    notes: list[str]


class StrategyCheck(BaseModel):
    label: str
    status: Literal["pass", "watch", "fail"]
    detail: str


class StrategyJudgement(BaseModel):
    stance: Literal["prepare_entry", "hold_steady", "wait", "reduce_risk"]
    headline: str
    action: str
    timing_score: float
    chip_cleanliness: str
    margin_trend: str
    market_guard: str
    checks: list[StrategyCheck]
    entry_triggers: list[str]
    defensive_triggers: list[str]


class KlineAnalysis(BaseModel):
    headline: str
    trend: str
    support_levels: list[str]
    resistance_levels: list[str]
    strategy_notes: list[str]
    invalidation: list[str]


class TrailingTakeProfitSummary(BaseModel):
    current_take_profit_price: float | None
    atr_multiplier: float
    estimated_return_percent: float | None
    risk_reward_ratio: float | None
    highest_price_used: float | None
    is_estimated_highest_price: bool


class RiskLights(BaseModel):
    market_trend: Light
    institutional_flow: Light
    technical: Light
    risk_indicator: Light
    composite: Light
    table: list[dict[str, str]]


class DecisionScenario(BaseModel):
    name: str
    condition: str
    action: str
    invalidation: str


class DecisionPlan(BaseModel):
    headline: str
    bias: Literal["bullish", "neutral", "bearish"]
    action: str
    confidence: Literal["高", "中", "低"]
    research_position_size: str
    score_breakdown: dict[str, float]
    checklist: dict[str, list[str]]
    scenarios: list[DecisionScenario]
    next_review_triggers: list[str]
    data_quality: list[str]
    ai_snapshot_prompt: str


class FundamentalGate(BaseModel):
    status: GateStatus
    grade: str
    passed: bool
    failed_reasons: list[str]
    metrics: dict[str, float | None]


class ValuationGate(BaseModel):
    status: GateStatus
    pe_ratio: float | None
    pe_band: str
    sector_band: str
    is_low_valuation: bool
    warning: str | None = None


class TimingGate(BaseModel):
    status: GateStatus
    trend: str
    support_zone: str
    no_chase_zone: str
    entry_conditions: list[str]
    invalidation_price: float | None


class PricePlan(BaseModel):
    research_price: float | None
    watch_price: float | None
    invalidation_price: float | None
    position_size_hint: str


class ResearchDecision(BaseModel):
    stance: ResearchStance
    horizon: str
    confidence: Literal["高", "中", "低"]
    summary: str
    next_action: str
    do_not_chase_reason: str | None = None
    blockers: list[str]
    review_triggers: list[str]


class BreakoutPotential(BaseModel):
    status: BreakoutStatus
    label: str
    score: float
    confidence: Literal["高", "中", "低"]
    headline: str
    thesis: str
    leading_signals: list[str]
    missing_confirmations: list[str]
    trigger_conditions: list[str]
    invalidation: str
    no_chase_warning: str | None = None


class MarketIndexQuote(BaseModel):
    symbol: str
    name: str
    value: float
    change: float
    change_percent: float
    volume: float | None = None
    source: str
    updated_at: datetime


class MarketRiskResponse(BaseModel):
    status: str
    score: float
    lights: RiskLights
    indicators: dict[str, float | None]
    reasons: list[str]
    generated_at: datetime
    market_date: date
    refresh: MarketRefreshInfo


class MarketOverviewResponse(BaseModel):
    taiex_state: str
    otc_state: str
    market_status: str
    heavyweight_impact: dict[str, float]
    taiex_quote: MarketIndexQuote | None = None
    risk: MarketRiskResponse


class AiPickFactor(BaseModel):
    kind: str
    label: str
    detail: str
    tone: Literal["positive", "neutral", "risk"] = "positive"


class AiMarketSnapshot(BaseModel):
    status: str
    score: float
    light: Light
    reasons: list[str]
    indicators: dict[str, float | None]
    generated_at: datetime
    market_date: date
    refresh: MarketRefreshInfo


class AiStockPick(BaseModel):
    rank: int
    symbol: str
    name: str | None = None
    industry: str
    latest_close: float | None = None
    recommendation: str
    selection_score: float
    adjusted_score: float
    candidate_status: CandidateStatus = "watch_only"
    data_quality_score: float = 0
    score_cap_reason: str | None = None
    bias: Literal["bullish", "neutral", "bearish"]
    confidence: Literal["高", "中", "低"]
    strategy_judgement: StrategyJudgement
    research_decision: ResearchDecision
    fundamental_gate: FundamentalGate
    valuation_gate: ValuationGate
    timing_gate: TimingGate
    price_plan: PricePlan
    breakout_potential: BreakoutPotential
    thesis: str
    bullish_factors: list[AiPickFactor]
    risk_factors: list[AiPickFactor]
    score_breakdown: dict[str, float]
    data_quality: list[str]
    source_notes: list[str]
    data_sources: dict[str, str] = Field(default_factory=dict)
    blockers: list[str] = Field(default_factory=list)
    why_ranked: list[str] = Field(default_factory=list)
    no_chase_reason: str | None = None
    future_outlook: dict[str, Any] | None = None


class AiStockPicksResponse(BaseModel):
    generated_at: datetime
    universe: list[str]
    refresh: MarketRefreshInfo
    market_snapshot: AiMarketSnapshot
    top_picks: list[AiStockPick]
    selection_logic: list[str]
    watch_notes: list[str]
    disclaimer: str = "AI 盤勢選股僅供研究與篩選，不構成投資建議、保證獲利或下單指令。"


class MarketScanRequest(BaseModel):
    universe: list[str] | None = None
    limit: int = Field(default=50, ge=1, le=200)
    max_symbols: int | None = Field(default=None, ge=1, le=2500)


class MarketScanCandidate(BaseModel):
    rank: int
    symbol: str
    name: str | None = None
    industry: str
    latest_close: float | None = None
    candidate_status: CandidateStatus
    selection_score: float
    adjusted_score: float
    data_quality_score: float = 0
    score_cap_reason: str | None = None
    research_decision: ResearchDecision
    fundamental_gate: FundamentalGate
    valuation_gate: ValuationGate
    timing_gate: TimingGate
    price_plan: PricePlan
    breakout_potential: BreakoutPotential
    data_sources: dict[str, str]
    blockers: list[str]
    why_ranked: list[str]
    no_chase_reason: str | None = None
    future_outlook: dict[str, Any] | None = None


class MarketScanResponse(BaseModel):
    scan_id: int
    generated_at: datetime
    universe_count: int
    completed_count: int
    failed_count: int
    universe_source: str = "unknown"
    is_full_market: bool = False
    data_quality_summary: dict[str, int]
    top_candidates: list[MarketScanCandidate]
    failed_symbols: list[str] = Field(default_factory=list)


class AnalysisResponse(BaseModel):
    symbol: str
    name: str | None = None
    industry: str | None = None
    analysis_date: date
    generated_at: datetime
    refresh: MarketRefreshInfo
    data_sources: dict[str, str]
    raw_score: float
    adjusted_score: float
    recommendation: str
    reasons: list[str]
    risks: list[str]
    technical: TechnicalSummary
    institutional: InstitutionalSummary
    margin: MarginSummary
    fundamental: FundamentalSummary
    sentiment: SentimentSummary
    stop_loss: StopLossSummary
    trailing_take_profit: TrailingTakeProfitSummary
    risk_lights: RiskLights
    decision_plan: DecisionPlan
    research_decision: ResearchDecision
    fundamental_gate: FundamentalGate
    valuation_gate: ValuationGate
    timing_gate: TimingGate
    price_plan: PricePlan
    strategy_judgement: StrategyJudgement
    breakout_potential: BreakoutPotential
    kline_analysis: KlineAnalysis
    disclaimer: str = "本系統僅供研究與紀律化決策輔助，不構成投資建議或下單指令。"


class ChartResponse(BaseModel):
    symbol: str
    name: str | None = None
    range: str
    figure: dict[str, Any]


class IntradayPoint(BaseModel):
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class IntradayResponse(BaseModel):
    symbol: str
    name: str | None = None
    source: str
    interval: str = "1m"
    trade_date: date | None = None
    previous_close: float | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    latest: float | None = None
    change: float | None = None
    change_percent: float | None = None
    volume: float | None = None
    updated_at: datetime
    points: list[IntradayPoint]


class BacktestRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=16)
    years: Literal[1, 3, 5] = 1
    strategy: str = "score_ma_atr"
    initial_capital: float = 100000


class BacktestResponse(BaseModel):
    symbol: str
    years: int
    strategy: str
    win_rate: float
    max_drawdown: float
    annualized_return: float
    sharpe_ratio: float
    trades: list[dict[str, Any]]
    equity_curve: list[dict[str, float | str]]


class RadarItem(BaseModel):
    symbol: str
    name: str | None = None
    score: float
    reason: str
    latest_close: float


class RadarResponse(BaseModel):
    kind: str
    items: list[RadarItem]


class WatchlistCreate(BaseModel):
    symbol: str = Field(min_length=1, max_length=16)
    note: str | None = None
    target_price: float | None = None
    stop_price: float | None = None


class WatchlistItem(WatchlistCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str | None = None
    lookup_status: Literal["verified", "unknown_symbol"] = "unknown_symbol"
    created_at: datetime


class PositionCreate(BaseModel):
    symbol: str = Field(min_length=1, max_length=16)
    entry_price: float = Field(gt=0)
    quantity: float = Field(default=0, ge=0)
    highest_price: float | None = Field(default=None, gt=0)
    entry_date: date | None = None


class PositionUpdate(BaseModel):
    entry_price: float | None = Field(default=None, gt=0)
    quantity: float | None = Field(default=None, ge=0)
    highest_price: float | None = Field(default=None, gt=0)
    entry_date: date | None = None
    status: Literal["open", "closed"] | None = None


class PositionItem(BaseModel):
    id: int
    symbol: str
    name: str | None = None
    entry_date: date | None = None
    entry_price: float
    quantity: float
    highest_price: float | None = None
    status: str
    created_at: datetime
    updated_at: datetime


class PositionDecisionSignal(BaseModel):
    kind: str
    label: str
    detail: str
    tone: Literal["positive", "neutral", "risk"] = "neutral"
    priority: int = 3


class PositionFutureScenario(BaseModel):
    name: str
    probability: int
    condition: str
    action: str
    trigger: str
    invalidation: str
    tone: Literal["positive", "neutral", "risk"] = "neutral"


class PositionSwingPlan(BaseModel):
    stance: str
    horizon: str
    entry_zone: str
    add_rule: str
    trim_rule: str
    stop_rule: str
    review_rule: str
    position_size_hint: str


class PositionFutureOutlook(BaseModel):
    label: str
    horizon: str
    expectation_gap: str
    leading_indicators: list[str]
    scenarios: list[PositionFutureScenario]
    swing_plan: PositionSwingPlan


class PositionDecisionItem(BaseModel):
    position: PositionItem
    latest_close: float | None = None
    cost_basis: float
    market_value: float | None = None
    unrealized_pnl: float | None = None
    unrealized_pnl_percent: float | None = None
    action: Literal["sell", "reduce", "hold", "add", "watch"]
    action_label: str
    confidence: Literal["高", "中", "低"]
    headline: str
    rationale: str
    priority_factors: list[PositionDecisionSignal]
    bullish_factors: list[PositionDecisionSignal]
    risk_factors: list[PositionDecisionSignal]
    future_outlook: PositionFutureOutlook | None = None
    next_review_triggers: list[str]
    data_quality: list[str]


class PdfReportResponse(BaseModel):
    symbol: str
    file_path: str
    generated_at: datetime


class NotificationTestRequest(BaseModel):
    channel: Literal["gmail", "telegram", "line"] = "gmail"
    subject: str = "台股 AI 投資決策助手測試通知"
    message: str = "這是一則測試通知。"


class NotificationTestResponse(BaseModel):
    channel: str
    status: str
    detail: str
