from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Light = Literal["green", "yellow", "red"]


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


class MarketOverviewResponse(BaseModel):
    taiex_state: str
    otc_state: str
    market_status: str
    heavyweight_impact: dict[str, float]
    risk: MarketRiskResponse


class AnalysisResponse(BaseModel):
    symbol: str
    name: str | None = None
    analysis_date: date
    raw_score: float
    adjusted_score: float
    recommendation: str
    reasons: list[str]
    risks: list[str]
    technical: TechnicalSummary
    institutional: InstitutionalSummary
    fundamental: FundamentalSummary
    sentiment: SentimentSummary
    stop_loss: StopLossSummary
    trailing_take_profit: TrailingTakeProfitSummary
    risk_lights: RiskLights
    decision_plan: DecisionPlan
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
