"""slim-prep's own tables (P-10). Every one is append-only: rows are inserted, never updated or deleted,
enforced by the repositories (no update path) and by triggers (`append_only.py`).

The rules are published once per content (hash). Stocks, standards and batches are versioned: a
correction is the next version with a reason, and `as_of` reads the version current at any moment.
The domain object is stored whole as JSON (Decimals as strings, never floats); the columns beside it
are what queries need: the key, the version, and for traceability which standards each batch used
and what each standard was made from.

Every name starts `prep_book_`: the database is shared, and slim-data already has `prep_batches`.

Portable: enums as ints, JSON via `JSON`, no ARRAY, no foreign keys into other modules' tables.
"""

from sqlalchemy import (
    JSON,
    Column,
    Date,
    ForeignKey,
    Integer,
    PrimaryKeyConstraint,
    String,
    Table,
    Text,
    UniqueConstraint,
)

from slim_prep.persistence.db import Base
from slim_prep.persistence.types import UtcDateTime, db_now

metadata = Base.metadata


def _created() -> list[Column]:
    return [
        Column("reason", Text, nullable=True),  # required from version 2: why it was corrected
        Column("created_by_id", String(100), nullable=False),
        Column("created_by", JSON, nullable=False),
        Column("created_at", UtcDateTime(), nullable=False, server_default=db_now()),
    ]


prep_rules = Table(
    "prep_book_rules",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(100), nullable=False),
    Column("content_hash", String(64), nullable=False, unique=True),
    Column("body", JSON, nullable=False),
    Column("published_by_id", String(100), nullable=False),
    Column("published_by", JSON, nullable=False),
    Column("created_at", UtcDateTime(), nullable=False, server_default=db_now()),
)

stocks = Table(
    "prep_book_stocks",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(100), nullable=False),
    Column("lot", String(50), nullable=False),
    Column("version", Integer, nullable=False),
    Column("body", JSON, nullable=False),
    *_created(),
    UniqueConstraint("name", "lot", "version"),
)

SOURCE_STOCK, SOURCE_STANDARD = 1, 2

standards = Table(
    "prep_book_standards",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(100), nullable=False),
    Column("prepared", Date, nullable=False),
    Column("version", Integer, nullable=False),
    Column("rules_id", Integer, ForeignKey("prep_book_rules.id"), nullable=False),
    Column("source_kind", Integer, nullable=False),  # SOURCE_STOCK or SOURCE_STANDARD
    Column("source_name", String(100), nullable=False),
    Column("source_key", String(50), nullable=False),  # the stock's lot, or the standard's prep date
    Column("body", JSON, nullable=False),
    *_created(),
    UniqueConstraint("name", "prepared", "version"),
)

prep_batches = Table(
    "prep_book_batches",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("code", String(50), nullable=False),
    Column("version", Integer, nullable=False),
    Column("rules_id", Integer, ForeignKey("prep_book_rules.id"), nullable=False),
    Column("body", JSON, nullable=False),
    *_created(),
    UniqueConstraint("code", "version"),
)

batch_standards = Table(
    "prep_book_batch_standards",
    metadata,
    Column("batch_row_id", Integer, ForeignKey("prep_book_batches.id"), nullable=False),
    Column("standard_name", String(100), nullable=False),
    Column("standard_prepared", Date, nullable=False),
    PrimaryKeyConstraint("batch_row_id", "standard_name", "standard_prepared"),
)

sent_batches = Table(
    "prep_book_sent_batches",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("code", String(50), nullable=False, unique=True),  # sent once (P-11); corrections: a later slice
    Column("version", Integer, nullable=False),  # the batch version slim-data received
    Column("created_by_id", String(100), nullable=False),
    Column("created_by", JSON, nullable=False),
    Column("created_at", UtcDateTime(), nullable=False, server_default=db_now()),
)
