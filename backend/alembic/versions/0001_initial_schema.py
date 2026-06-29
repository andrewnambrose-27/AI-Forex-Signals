"""initial schema

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-06-29 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.create_index(op.f("ix_users_id"), "users", ["id"], unique=False)

    op.create_table(
        "app_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_app_settings_id"), "app_settings", ["id"], unique=False)
    op.create_index(op.f("ix_app_settings_key"), "app_settings", ["key"], unique=True)

    op.create_table(
        "economic_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("external_id", sa.String(length=128), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("impact", sa.String(length=16), nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("forecast", sa.String(length=100), nullable=True),
        sa.Column("previous", sa.String(length=100), nullable=True),
        sa.Column("actual", sa.String(length=100), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("raw_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "external_id", name="uq_economic_event_provider_external_id"),
    )
    op.create_index(op.f("ix_economic_events_currency"), "economic_events", ["currency"], unique=False)
    op.create_index(op.f("ix_economic_events_event_time"), "economic_events", ["event_time"], unique=False)
    op.create_index(op.f("ix_economic_events_external_id"), "economic_events", ["external_id"], unique=False)
    op.create_index(op.f("ix_economic_events_id"), "economic_events", ["id"], unique=False)
    op.create_index(op.f("ix_economic_events_impact"), "economic_events", ["impact"], unique=False)
    op.create_index(op.f("ix_economic_events_provider"), "economic_events", ["provider"], unique=False)

    op.create_table(
        "watched_markets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("pair", sa.String(length=32), nullable=False),
        sa.Column("epic", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "epic", name="uq_watched_market_user_epic"),
    )
    op.create_index(op.f("ix_watched_markets_epic"), "watched_markets", ["epic"], unique=False)
    op.create_index(op.f("ix_watched_markets_id"), "watched_markets", ["id"], unique=False)
    op.create_index(op.f("ix_watched_markets_pair"), "watched_markets", ["pair"], unique=False)
    op.create_index(op.f("ix_watched_markets_provider"), "watched_markets", ["provider"], unique=False)
    op.create_index(op.f("ix_watched_markets_user_id"), "watched_markets", ["user_id"], unique=False)

    op.create_table(
        "candles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=128), nullable=False),
        sa.Column("timeframe", sa.String(length=8), nullable=False),
        sa.Column("epic", sa.String(length=128), nullable=True),
        sa.Column("resolution", sa.String(length=16), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("high", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("low", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("close", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("volume", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("raw_data", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("epic", "resolution", "opened_at", name="uq_candle_epic_resolution_opened"),
        sa.UniqueConstraint("symbol", "timeframe", "opened_at", name="uq_candle_symbol_timeframe_opened"),
    )
    op.create_index(op.f("ix_candles_epic"), "candles", ["epic"], unique=False)
    op.create_index(op.f("ix_candles_id"), "candles", ["id"], unique=False)
    op.create_index(op.f("ix_candles_opened_at"), "candles", ["opened_at"], unique=False)
    op.create_index(op.f("ix_candles_provider"), "candles", ["provider"], unique=False)
    op.create_index(op.f("ix_candles_resolution"), "candles", ["resolution"], unique=False)
    op.create_index(op.f("ix_candles_symbol"), "candles", ["symbol"], unique=False)
    op.create_index(op.f("ix_candles_timeframe"), "candles", ["timeframe"], unique=False)

    op.create_table(
        "signals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("pair", sa.String(length=32), nullable=False),
        sa.Column("epic", sa.String(length=128), nullable=True),
        sa.Column("direction", sa.String(length=8), nullable=False),
        sa.Column("timeframe", sa.String(length=16), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("entry_reference_price", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("suggested_stop", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("suggested_target", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("risk_reward_ratio", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("reasons", sa.JSON(), nullable=False),
        sa.Column("filters_passed", sa.JSON(), nullable=False),
        sa.Column("filters_failed", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("direction in ('BUY', 'SELL')", name="ck_signals_direction_buy_sell"),
        sa.CheckConstraint("status in ('active', 'expired', 'filtered')", name="ck_signals_status"),
    )
    op.create_index(op.f("ix_signals_created_at"), "signals", ["created_at"], unique=False)
    op.create_index(op.f("ix_signals_direction"), "signals", ["direction"], unique=False)
    op.create_index(op.f("ix_signals_epic"), "signals", ["epic"], unique=False)
    op.create_index(op.f("ix_signals_id"), "signals", ["id"], unique=False)
    op.create_index(op.f("ix_signals_pair"), "signals", ["pair"], unique=False)
    op.create_index(op.f("ix_signals_status"), "signals", ["status"], unique=False)
    op.create_index(op.f("ix_signals_timeframe"), "signals", ["timeframe"], unique=False)
    op.create_index(op.f("ix_signals_user_id"), "signals", ["user_id"], unique=False)

    op.create_table(
        "signal_components",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("signal_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("score_impact", sa.Integer(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("raw_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["signal_id"], ["signals.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_signal_components_category"), "signal_components", ["category"], unique=False)
    op.create_index(op.f("ix_signal_components_id"), "signal_components", ["id"], unique=False)
    op.create_index(op.f("ix_signal_components_name"), "signal_components", ["name"], unique=False)
    op.create_index(op.f("ix_signal_components_passed"), "signal_components", ["passed"], unique=False)
    op.create_index(op.f("ix_signal_components_signal_id"), "signal_components", ["signal_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_signal_components_signal_id"), table_name="signal_components")
    op.drop_index(op.f("ix_signal_components_passed"), table_name="signal_components")
    op.drop_index(op.f("ix_signal_components_name"), table_name="signal_components")
    op.drop_index(op.f("ix_signal_components_id"), table_name="signal_components")
    op.drop_index(op.f("ix_signal_components_category"), table_name="signal_components")
    op.drop_table("signal_components")
    op.drop_index(op.f("ix_signals_user_id"), table_name="signals")
    op.drop_index(op.f("ix_signals_timeframe"), table_name="signals")
    op.drop_index(op.f("ix_signals_status"), table_name="signals")
    op.drop_index(op.f("ix_signals_pair"), table_name="signals")
    op.drop_index(op.f("ix_signals_id"), table_name="signals")
    op.drop_index(op.f("ix_signals_epic"), table_name="signals")
    op.drop_index(op.f("ix_signals_direction"), table_name="signals")
    op.drop_index(op.f("ix_signals_created_at"), table_name="signals")
    op.drop_table("signals")
    op.drop_index(op.f("ix_candles_timeframe"), table_name="candles")
    op.drop_index(op.f("ix_candles_symbol"), table_name="candles")
    op.drop_index(op.f("ix_candles_resolution"), table_name="candles")
    op.drop_index(op.f("ix_candles_provider"), table_name="candles")
    op.drop_index(op.f("ix_candles_opened_at"), table_name="candles")
    op.drop_index(op.f("ix_candles_id"), table_name="candles")
    op.drop_index(op.f("ix_candles_epic"), table_name="candles")
    op.drop_table("candles")
    op.drop_index(op.f("ix_watched_markets_user_id"), table_name="watched_markets")
    op.drop_index(op.f("ix_watched_markets_provider"), table_name="watched_markets")
    op.drop_index(op.f("ix_watched_markets_pair"), table_name="watched_markets")
    op.drop_index(op.f("ix_watched_markets_id"), table_name="watched_markets")
    op.drop_index(op.f("ix_watched_markets_epic"), table_name="watched_markets")
    op.drop_table("watched_markets")
    op.drop_index(op.f("ix_economic_events_provider"), table_name="economic_events")
    op.drop_index(op.f("ix_economic_events_impact"), table_name="economic_events")
    op.drop_index(op.f("ix_economic_events_id"), table_name="economic_events")
    op.drop_index(op.f("ix_economic_events_external_id"), table_name="economic_events")
    op.drop_index(op.f("ix_economic_events_event_time"), table_name="economic_events")
    op.drop_index(op.f("ix_economic_events_currency"), table_name="economic_events")
    op.drop_table("economic_events")
    op.drop_index(op.f("ix_app_settings_key"), table_name="app_settings")
    op.drop_index(op.f("ix_app_settings_id"), table_name="app_settings")
    op.drop_table("app_settings")
    op.drop_index(op.f("ix_users_id"), table_name="users")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
