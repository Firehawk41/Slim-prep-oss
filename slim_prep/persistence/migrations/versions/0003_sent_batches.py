"""Which batch versions were handed to slim-data (P-11), and corrections sent after (P-20).

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from slim_prep.persistence import append_only, types

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "prep_book_sent_batches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by_id", sa.String(100), nullable=False),
        sa.Column("created_by", sa.JSON(), nullable=False),
        sa.Column("created_at", types.UtcDateTime(), nullable=False, server_default=types.db_now()),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_prep_book_sent_batches")),
        sa.UniqueConstraint("code", "version", name=op.f("uq_prep_book_sent_batches_code")),
    )
    append_only.install(op.get_bind(), ("prep_book_sent_batches",))


def downgrade() -> None:
    op.drop_table("prep_book_sent_batches")
