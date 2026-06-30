"""add economic event country

Revision ID: 0002_add_economic_event_country
Revises: 0001_initial_schema
Create Date: 2026-06-30 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_add_economic_event_country"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("economic_events", sa.Column("country", sa.String(length=80), nullable=True))
    op.create_index(op.f("ix_economic_events_country"), "economic_events", ["country"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_economic_events_country"), table_name="economic_events")
    op.drop_column("economic_events", "country")
