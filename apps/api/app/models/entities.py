from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.core.database import Base

JsonType = JSON().with_variant(JSONB, "postgresql")


def utc_now() -> datetime:
    return datetime.now(UTC)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )


class Instrument(Base, TimestampMixin):
    __tablename__ = "instruments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(128))
    market: Mapped[str] = mapped_column(String(32), default="TWSE")
    currency: Mapped[str] = mapped_column(String(8), default="TWD")
    asset_type: Mapped[str] = mapped_column(String(32), default="stock")

    prices: Mapped[list["DailyPrice"]] = relationship(back_populates="instrument")


class DailyPrice(Base):
    __tablename__ = "daily_prices"
    __table_args__ = (UniqueConstraint("instrument_id", "trade_date", name="uq_daily_price"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), index=True)
    trade_date: Mapped[date] = mapped_column(Date, index=True)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(32), default="finmind")

    instrument: Mapped[Instrument] = relationship(back_populates="prices")


class InstitutionalFlow(Base):
    __tablename__ = "institutional_flows"
    __table_args__ = (UniqueConstraint("instrument_id", "trade_date", name="uq_institutional_flow"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), index=True)
    trade_date: Mapped[date] = mapped_column(Date, index=True)
    foreign_net: Mapped[float] = mapped_column(Float, default=0)
    investment_trust_net: Mapped[float] = mapped_column(Float, default=0)
    dealer_net: Mapped[float] = mapped_column(Float, default=0)
    total_net: Mapped[float] = mapped_column(Float, default=0)
    source: Mapped[str] = mapped_column(String(32), default="finmind")


class Fundamental(Base, TimestampMixin):
    __tablename__ = "fundamentals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), index=True)
    fiscal_year: Mapped[int] = mapped_column(Integer)
    quarter: Mapped[int] = mapped_column(Integer)
    eps: Mapped[float | None] = mapped_column(Float)
    roe: Mapped[float | None] = mapped_column(Float)
    gross_margin: Mapped[float | None] = mapped_column(Float)
    operating_margin: Mapped[float | None] = mapped_column(Float)
    pe_ratio: Mapped[float | None] = mapped_column(Float)
    pb_ratio: Mapped[float | None] = mapped_column(Float)
    revenue_yoy: Mapped[float | None] = mapped_column(Float)
    revenue_mom: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(32), default="finmind")


class MonthlyRevenue(Base):
    __tablename__ = "monthly_revenues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), index=True)
    revenue_month: Mapped[date] = mapped_column(Date, index=True)
    revenue: Mapped[float] = mapped_column(Float)
    revenue_yoy: Mapped[float | None] = mapped_column(Float)
    revenue_mom: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(32), default="finmind")


class MarginBalance(Base):
    __tablename__ = "margin_balances"
    __table_args__ = (UniqueConstraint("instrument_id", "trade_date", name="uq_margin_balance"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), index=True)
    trade_date: Mapped[date] = mapped_column(Date, index=True)
    margin_purchase_balance: Mapped[float | None] = mapped_column(Float)
    short_sale_balance: Mapped[float | None] = mapped_column(Float)
    short_margin_ratio: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(32), default="finmind")


class ShareholdingStat(Base):
    __tablename__ = "shareholding_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), index=True)
    stat_date: Mapped[date] = mapped_column(Date, index=True)
    large_holder_ratio: Mapped[float | None] = mapped_column(Float)
    shareholder_count: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(32), default="finmind")


class NewsItem(Base, TimestampMixin):
    __tablename__ = "news_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instrument_id: Mapped[int | None] = mapped_column(ForeignKey("instruments.id"), index=True)
    published_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    title: Mapped[str] = mapped_column(String(256))
    url: Mapped[str | None] = mapped_column(String(512))
    source: Mapped[str] = mapped_column(String(64), default="finmind")
    summary: Mapped[str | None] = mapped_column(Text)


class SentimentScore(Base, TimestampMixin):
    __tablename__ = "sentiment_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instrument_id: Mapped[int | None] = mapped_column(ForeignKey("instruments.id"), index=True)
    target_date: Mapped[date] = mapped_column(Date, index=True)
    score: Mapped[float] = mapped_column(Float)
    label: Mapped[str] = mapped_column(String(32))
    rationale: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(String(64))


class TechnicalSnapshot(Base, TimestampMixin):
    __tablename__ = "technical_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), index=True)
    trade_date: Mapped[date] = mapped_column(Date, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JsonType)


class AnalysisResult(Base, TimestampMixin):
    __tablename__ = "analysis_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), index=True)
    analysis_date: Mapped[date] = mapped_column(Date, index=True)
    raw_score: Mapped[float] = mapped_column(Float)
    adjusted_score: Mapped[float] = mapped_column(Float)
    recommendation: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict[str, Any]] = mapped_column(JsonType)


class MarketRiskSnapshot(Base, TimestampMixin):
    __tablename__ = "market_risk_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    target_date: Mapped[date] = mapped_column(Date, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JsonType)


class MarketScanResult(Base, TimestampMixin):
    __tablename__ = "market_scan_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    universe_count: Mapped[int] = mapped_column(Integer)
    completed_count: Mapped[int] = mapped_column(Integer)
    failed_count: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict[str, Any]] = mapped_column(JsonType)


class Position(Base, TimestampMixin):
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), index=True)
    entry_date: Mapped[date | None] = mapped_column(Date)
    entry_price: Mapped[float] = mapped_column(Float)
    quantity: Mapped[float] = mapped_column(Float, default=0)
    highest_price: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(32), default="open")


class WatchlistItem(Base, TimestampMixin):
    __tablename__ = "watchlists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    note: Mapped[str | None] = mapped_column(String(256))
    target_price: Mapped[float | None] = mapped_column(Float)
    stop_price: Mapped[float | None] = mapped_column(Float)


class NotificationChannel(Base, TimestampMixin):
    __tablename__ = "notification_channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel_type: Mapped[str] = mapped_column(String(32))
    enabled: Mapped[int] = mapped_column(Integer, default=1)
    config: Mapped[dict[str, Any] | None] = mapped_column(JsonType)


class NotificationEvent(Base, TimestampMixin):
    __tablename__ = "notification_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel_type: Mapped[str] = mapped_column(String(32))
    subject: Mapped[str] = mapped_column(String(256))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    error: Mapped[str | None] = mapped_column(Text)


class Report(Base, TimestampMixin):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instrument_id: Mapped[int | None] = mapped_column(ForeignKey("instruments.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    report_date: Mapped[date] = mapped_column(Date, index=True)
    file_path: Mapped[str] = mapped_column(String(512))
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JsonType)


class BacktestRun(Base, TimestampMixin):
    __tablename__ = "backtest_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    years: Mapped[int] = mapped_column(Integer)
    strategy: Mapped[str] = mapped_column(String(64))
    metrics: Mapped[dict[str, Any]] = mapped_column(JsonType)
    trades: Mapped[list[dict[str, Any]]] = mapped_column(JsonType)
