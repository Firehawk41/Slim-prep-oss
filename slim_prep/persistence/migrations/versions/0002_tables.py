"""slim-prep's tables (P-10) and the append-only triggers on every one of them.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from slim_prep.persistence import append_only, types

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Frozen here, not read from the models: this migration must keep meaning what it meant.
TABLES = ("prep_rules", "stocks", "standards", "prep_batches", "batch_standards")


def _created() -> list[sa.Column]:
    return [
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_by_id", sa.String(100), nullable=False),
        sa.Column("created_by", sa.JSON(), nullable=False),
        sa.Column("created_at", types.UtcDateTime(), nullable=False, server_default=types.db_now()),
    ]


def upgrade() -> None:
    op.create_table(
        "prep_rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("body", sa.JSON(), nullable=False),
        sa.Column("published_by_id", sa.String(100), nullable=False),
        sa.Column("published_by", sa.JSON(), nullable=False),
        sa.Column("created_at", types.UtcDateTime(), nullable=False, server_default=types.db_now()),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_prep_rules")),
        sa.UniqueConstraint("content_hash", name=op.f("uq_prep_rules_content_hash")),
    )
    op.create_table(
        "stocks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("lot", sa.String(50), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("body", sa.JSON(), nullable=False),
        *_created(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stocks")),
        sa.UniqueConstraint("name", "lot", "version", name=op.f("uq_stocks_name")),
    )
    op.create_table(
        "standards",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("prepared", sa.Date(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("rules_id", sa.Integer(), nullable=False),
        sa.Column("source_kind", sa.Integer(), nullable=False),
        sa.Column("source_name", sa.String(100), nullable=False),
        sa.Column("source_key", sa.String(50), nullable=False),
        sa.Column("body", sa.JSON(), nullable=False),
        *_created(),
        sa.ForeignKeyConstraint(
            ["rules_id"], ["prep_rules.id"], name=op.f("fk_standards_rules_id_prep_rules")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_standards")),
        sa.UniqueConstraint("name", "prepared", "version", name=op.f("uq_standards_name")),
    )
    op.create_table(
        "prep_batches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("rules_id", sa.Integer(), nullable=False),
        sa.Column("body", sa.JSON(), nullable=False),
        *_created(),
        sa.ForeignKeyConstraint(
            ["rules_id"], ["prep_rules.id"], name=op.f("fk_prep_batches_rules_id_prep_rules")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_prep_batches")),
        sa.UniqueConstraint("code", "version", name=op.f("uq_prep_batches_code")),
    )
    op.create_table(
        "batch_standards",
        sa.Column("batch_row_id", sa.Integer(), nullable=False),
        sa.Column("standard_name", sa.String(100), nullable=False),
        sa.Column("standard_prepared", sa.Date(), nullable=False),
        sa.ForeignKeyConstraint(
            ["batch_row_id"], ["prep_batches.id"], name=op.f("fk_batch_standards_batch_row_id_prep_batches")
        ),
        sa.PrimaryKeyConstraint(
            "batch_row_id", "standard_name", "standard_prepared", name=op.f("pk_batch_standards")
        ),
    )
    append_only.install(op.get_bind(), TABLES)


def downgrade() -> None:
    append_only.uninstall(op.get_bind())
    for table in reversed(TABLES):
        op.drop_table(table)
