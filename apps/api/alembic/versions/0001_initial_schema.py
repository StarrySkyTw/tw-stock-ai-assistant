from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "instruments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=True),
        sa.Column("market", sa.String(length=32), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("asset_type", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("symbol"),
    )
    op.create_index("ix_instruments_symbol", "instruments", ["symbol"])

    op.create_table(
        "daily_prices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("instrument_id", sa.Integer(), sa.ForeignKey("instruments.id"), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("open", sa.Float(), nullable=False),
        sa.Column("high", sa.Float(), nullable=False),
        sa.Column("low", sa.Float(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("volume", sa.Float(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.UniqueConstraint("instrument_id", "trade_date", name="uq_daily_price"),
    )
    op.create_index("ix_daily_prices_instrument_id", "daily_prices", ["instrument_id"])
    op.create_index("ix_daily_prices_trade_date", "daily_prices", ["trade_date"])

    op.create_table(
        "institutional_flows",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("instrument_id", sa.Integer(), sa.ForeignKey("instruments.id"), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("foreign_net", sa.Float(), nullable=False),
        sa.Column("investment_trust_net", sa.Float(), nullable=False),
        sa.Column("dealer_net", sa.Float(), nullable=False),
        sa.Column("total_net", sa.Float(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.UniqueConstraint("instrument_id", "trade_date", name="uq_institutional_flow"),
    )
    op.create_index("ix_institutional_flows_instrument_id", "institutional_flows", ["instrument_id"])
    op.create_index("ix_institutional_flows_trade_date", "institutional_flows", ["trade_date"])

    for table_name in [
        "fundamentals",
        "monthly_revenues",
        "margin_balances",
        "shareholding_stats",
        "news_items",
        "sentiment_scores",
        "technical_snapshots",
        "analysis_results",
        "market_risk_snapshots",
        "positions",
        "watchlists",
        "notification_channels",
        "notification_events",
        "reports",
        "backtest_runs",
    ]:
        _create_remaining_table(table_name)


def downgrade() -> None:
    for table_name in [
        "backtest_runs",
        "reports",
        "notification_events",
        "notification_channels",
        "watchlists",
        "positions",
        "market_risk_snapshots",
        "analysis_results",
        "technical_snapshots",
        "sentiment_scores",
        "news_items",
        "shareholding_stats",
        "margin_balances",
        "monthly_revenues",
        "fundamentals",
        "institutional_flows",
        "daily_prices",
        "instruments",
    ]:
        op.drop_table(table_name)


def _json_type() -> sa.JSON:
    return sa.JSON()


def _create_remaining_table(table_name: str) -> None:
    common_ts = [
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    ]
    if table_name == "fundamentals":
        op.create_table(
            table_name,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("instrument_id", sa.Integer(), sa.ForeignKey("instruments.id"), nullable=False),
            sa.Column("fiscal_year", sa.Integer(), nullable=False),
            sa.Column("quarter", sa.Integer(), nullable=False),
            sa.Column("eps", sa.Float()),
            sa.Column("roe", sa.Float()),
            sa.Column("gross_margin", sa.Float()),
            sa.Column("operating_margin", sa.Float()),
            sa.Column("pe_ratio", sa.Float()),
            sa.Column("pb_ratio", sa.Float()),
            sa.Column("revenue_yoy", sa.Float()),
            sa.Column("revenue_mom", sa.Float()),
            sa.Column("source", sa.String(length=32), nullable=False),
            *common_ts,
        )
    elif table_name == "monthly_revenues":
        op.create_table(
            table_name,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("instrument_id", sa.Integer(), sa.ForeignKey("instruments.id"), nullable=False),
            sa.Column("revenue_month", sa.Date(), nullable=False),
            sa.Column("revenue", sa.Float(), nullable=False),
            sa.Column("revenue_yoy", sa.Float()),
            sa.Column("revenue_mom", sa.Float()),
            sa.Column("source", sa.String(length=32), nullable=False),
        )
    elif table_name == "margin_balances":
        op.create_table(
            table_name,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("instrument_id", sa.Integer(), sa.ForeignKey("instruments.id"), nullable=False),
            sa.Column("trade_date", sa.Date(), nullable=False),
            sa.Column("margin_purchase_balance", sa.Float()),
            sa.Column("short_sale_balance", sa.Float()),
            sa.Column("short_margin_ratio", sa.Float()),
            sa.Column("source", sa.String(length=32), nullable=False),
            sa.UniqueConstraint("instrument_id", "trade_date", name="uq_margin_balance"),
        )
    elif table_name == "shareholding_stats":
        op.create_table(
            table_name,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("instrument_id", sa.Integer(), sa.ForeignKey("instruments.id"), nullable=False),
            sa.Column("stat_date", sa.Date(), nullable=False),
            sa.Column("large_holder_ratio", sa.Float()),
            sa.Column("shareholder_count", sa.Integer()),
            sa.Column("source", sa.String(length=32), nullable=False),
        )
    elif table_name == "news_items":
        op.create_table(
            table_name,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("instrument_id", sa.Integer(), sa.ForeignKey("instruments.id"), nullable=True),
            sa.Column("published_at", sa.DateTime(), nullable=False),
            sa.Column("title", sa.String(length=256), nullable=False),
            sa.Column("url", sa.String(length=512)),
            sa.Column("source", sa.String(length=64), nullable=False),
            sa.Column("summary", sa.Text()),
            *common_ts,
        )
    elif table_name == "sentiment_scores":
        op.create_table(
            table_name,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("instrument_id", sa.Integer(), sa.ForeignKey("instruments.id"), nullable=True),
            sa.Column("target_date", sa.Date(), nullable=False),
            sa.Column("score", sa.Float(), nullable=False),
            sa.Column("label", sa.String(length=32), nullable=False),
            sa.Column("rationale", sa.Text()),
            sa.Column("model", sa.String(length=64)),
            *common_ts,
        )
    elif table_name in {"technical_snapshots", "market_risk_snapshots"}:
        op.create_table(
            table_name,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("instrument_id", sa.Integer(), sa.ForeignKey("instruments.id"), nullable=True),
            sa.Column("trade_date" if table_name == "technical_snapshots" else "target_date", sa.Date(), nullable=False),
            sa.Column("payload", _json_type(), nullable=False),
            *common_ts,
        )
    elif table_name == "analysis_results":
        op.create_table(
            table_name,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("instrument_id", sa.Integer(), sa.ForeignKey("instruments.id"), nullable=False),
            sa.Column("analysis_date", sa.Date(), nullable=False),
            sa.Column("raw_score", sa.Float(), nullable=False),
            sa.Column("adjusted_score", sa.Float(), nullable=False),
            sa.Column("recommendation", sa.String(length=32), nullable=False),
            sa.Column("payload", _json_type(), nullable=False),
            *common_ts,
        )
    elif table_name == "positions":
        op.create_table(
            table_name,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("instrument_id", sa.Integer(), sa.ForeignKey("instruments.id"), nullable=False),
            sa.Column("entry_date", sa.Date()),
            sa.Column("entry_price", sa.Float(), nullable=False),
            sa.Column("quantity", sa.Float(), nullable=False),
            sa.Column("highest_price", sa.Float()),
            sa.Column("status", sa.String(length=32), nullable=False),
            *common_ts,
        )
    elif table_name == "watchlists":
        op.create_table(
            table_name,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("symbol", sa.String(length=32), nullable=False),
            sa.Column("note", sa.String(length=256)),
            sa.Column("target_price", sa.Float()),
            sa.Column("stop_price", sa.Float()),
            *common_ts,
        )
    elif table_name == "notification_channels":
        op.create_table(
            table_name,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("channel_type", sa.String(length=32), nullable=False),
            sa.Column("enabled", sa.Integer(), nullable=False),
            sa.Column("config", _json_type()),
            *common_ts,
        )
    elif table_name == "notification_events":
        op.create_table(
            table_name,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("channel_type", sa.String(length=32), nullable=False),
            sa.Column("subject", sa.String(length=256), nullable=False),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("error", sa.Text()),
            *common_ts,
        )
    elif table_name == "reports":
        op.create_table(
            table_name,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("instrument_id", sa.Integer(), sa.ForeignKey("instruments.id"), nullable=True),
            sa.Column("symbol", sa.String(length=32), nullable=False),
            sa.Column("report_date", sa.Date(), nullable=False),
            sa.Column("file_path", sa.String(length=512), nullable=False),
            sa.Column("metadata_json", _json_type()),
            *common_ts,
        )
    elif table_name == "backtest_runs":
        op.create_table(
            table_name,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("symbol", sa.String(length=32), nullable=False),
            sa.Column("years", sa.Integer(), nullable=False),
            sa.Column("strategy", sa.String(length=64), nullable=False),
            sa.Column("metrics", _json_type(), nullable=False),
            sa.Column("trades", _json_type(), nullable=False),
            *common_ts,
        )

