from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Light = Literal["green", "yellow", "red"]
MarketPhase = Literal["pre_open", "regular", "post_close", "closed"]


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
    latest_close: float
    recommendation: str
    selection_score: float
    adjusted_score: float
    bias: Literal["bullish", "neutral", "bearish"]
    confidence: Literal["高", "中", "低"]
    strategy_judgement: StrategyJudgement
    thesis: str
    bullish_factors: list[AiPickFactor]
    risk_factors: list[AiPickFactor]
    score_breakdown: dict[str, float]
    data_quality: list[str]
    source_notes: list[str]


class AiStockPicksResponse(BaseModel):
    generated_at: datetime
    universe: list[str]
    refresh: MarketRefreshInfo
    market_snapshot: AiMarketSnapshot
    top_picks: list[AiStockPick]
    selection_logic: list[str]
    watch_notes: list[str]
    disclaimer: str = "AI 盤勢選股僅供研究與篩選，不構成投資建議、保證獲利或下單指令。"


class AnalysisResponse(BaseModel):
    symbol: str
    name: str | None = None
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
    strategy_judgement: StrategyJudgement
    disclaimer: str = "本系統僅供研究與紀律化決策輔助，不構成投資建議或下單指令。"


class ChartResponse(BaseModel):
    symbol: str
    name: str | None = None
    range: str
    figure: dict[str, Any]


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
