"""production economic calendar fields

Revision ID: 0003_economic_calendar
Revises: 0002_add_economic_event_country
Create Date: 2026-07-22 00:00:00.000000
"""
from typing import Sequence, Union
from datetime import timezone
from hashlib import sha256
import re

from alembic import op
import sqlalchemy as sa


revision: str = "0003_economic_calendar"
down_revision: Union[str, None] = "0002_add_economic_event_country"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("economic_events", sa.Column("internal_id", sa.String(length=36), nullable=True))
    op.add_column("economic_events", sa.Column("provider_event_id", sa.String(length=160), nullable=True))
    op.add_column("economic_events", sa.Column("fallback_dedupe_key", sa.String(length=64), nullable=True))
    op.add_column("economic_events", sa.Column("revised_previous", sa.String(length=100), nullable=True))
    op.add_column("economic_events", sa.Column("unit", sa.String(length=40), nullable=True))
    op.add_column("economic_events", sa.Column("source", sa.String(length=255), nullable=True))
    op.add_column("economic_events", sa.Column("status", sa.String(length=16), server_default="scheduled", nullable=False))
    op.add_column("economic_events", sa.Column("raw_payload", sa.JSON(), nullable=True))
    op.add_column("economic_events", sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.execute("UPDATE economic_events SET internal_id = 'legacy-' || CAST(id AS VARCHAR)")
    op.execute("UPDATE economic_events SET provider_event_id = external_id WHERE external_id IS NOT NULL")
    connection = op.get_bind()
    rows = list(connection.execute(sa.text("SELECT id, external_id, title, country, event_time FROM economic_events")).mappings())
    for row in rows:
        if row.get("external_id"):
            continue
        title = re.sub(r"\s+", " ", str(row["title"]).strip().lower())
        country = str(row["country"] or "").strip().lower()
        event_time = row["event_time"]
        if getattr(event_time, "tzinfo", None) is None:
            event_time = event_time.replace(tzinfo=timezone.utc)
        event_time = event_time.astimezone(timezone.utc).replace(second=0, microsecond=0).isoformat()
        key = sha256(f"{title}|{country}|{event_time}".encode("utf-8")).hexdigest()
        connection.execute(sa.text("UPDATE economic_events SET fallback_dedupe_key = :key WHERE id = :id"), {"key": key, "id": row["id"]})
    op.execute("UPDATE economic_events SET raw_payload = raw_data WHERE raw_data IS NOT NULL")
    op.alter_column("economic_events", "internal_id", nullable=False)
    op.create_index(op.f("ix_economic_events_internal_id"), "economic_events", ["internal_id"], unique=True)
    op.create_index(op.f("ix_economic_events_provider_event_id"), "economic_events", ["provider_event_id"], unique=False)
    op.create_index(op.f("ix_economic_events_fallback_dedupe_key"), "economic_events", ["fallback_dedupe_key"], unique=False)
    op.create_index(op.f("ix_economic_events_status"), "economic_events", ["status"], unique=False)
    op.create_unique_constraint("uq_economic_event_provider_event_id", "economic_events", ["provider", "provider_event_id"])
    op.create_unique_constraint("uq_economic_event_provider_fallback_key", "economic_events", ["provider", "fallback_dedupe_key"])


def downgrade() -> None:
    op.drop_constraint("uq_economic_event_provider_fallback_key", "economic_events", type_="unique")
    op.drop_constraint("uq_economic_event_provider_event_id", "economic_events", type_="unique")
    op.drop_index(op.f("ix_economic_events_status"), table_name="economic_events")
    op.drop_index(op.f("ix_economic_events_fallback_dedupe_key"), table_name="economic_events")
    op.drop_index(op.f("ix_economic_events_provider_event_id"), table_name="economic_events")
    op.drop_index(op.f("ix_economic_events_internal_id"), table_name="economic_events")
    for column in ("updated_at", "raw_payload", "status", "source", "unit", "revised_previous", "fallback_dedupe_key", "provider_event_id", "internal_id"):
        op.drop_column("economic_events", column)
