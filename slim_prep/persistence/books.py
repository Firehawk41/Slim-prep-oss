"""The stocks, standards and prep batches, versioned (P-10).

Each record is a domain object stored whole. Saving is `save_*(…, expected_version)`: 0 for a new
record, else the version the person was looking at. The new row is that + 1; if someone else wrote it
first the unique key says no and it's a `ConcurrentChange`. From version 2 a reason is required (a
correction). `get_*` reads the version current `as_of` any moment; `history_*` lists them all.
"""

from datetime import datetime
from typing import Generic, TypeVar

from sqlalchemy import Table, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from slim_prep.domain.actor import Actor
from slim_prep.domain.base import Frozen
from slim_prep.domain.prep import PrepBatch
from slim_prep.domain.standards import Standard, StandardRef, Stock
from slim_prep.persistence._rows import ConcurrentChange, NotFound, actor_json, as_of_filter
from slim_prep.persistence.audit import set_change_context
from slim_prep.persistence.tables import (
    SOURCE_STANDARD,
    SOURCE_STOCK,
    batch_standards,
    prep_batches,
    standards,
    stocks,
)

T = TypeVar("T", Stock, Standard, PrepBatch)


class Recorded(Frozen, Generic[T]):
    """One stored version of a record, with who wrote it, when and why."""

    row_id: int
    version: int
    item: T
    rules_id: int | None = None
    reason: str | None
    created_by: Actor
    created_at: datetime


def save_stock(
    session: Session, stock: Stock, actor: Actor, expected_version: int = 0, reason: str | None = None
) -> Recorded[Stock]:
    key = {"name": stock.name, "lot": stock.lot}
    return _save(session, stocks, key, stock, actor, expected_version, reason, f"stock {stock}")


def get_stock(session: Session, name: str, lot: str, as_of: datetime | None = None) -> Recorded[Stock]:
    return _get(session, stocks, {"name": name, "lot": lot}, Stock, as_of, f"stock {name} lot {lot}")


def save_standard(
    session: Session,
    standard: Standard,
    rules_id: int,
    actor: Actor,
    expected_version: int = 0,
    reason: str | None = None,
) -> Recorded[Standard]:
    source = standard.source
    if isinstance(source, Stock):
        columns = {"source_kind": SOURCE_STOCK, "source_name": source.name, "source_key": source.lot}
    else:
        columns = {
            "source_kind": SOURCE_STANDARD,
            "source_name": source.name,
            "source_key": source.prepared.isoformat(),
        }
    key = {"name": standard.name, "prepared": standard.prepared}
    what = f"standard {standard.ref}"
    return _save(
        session, standards, key, standard, actor, expected_version, reason, what, rules_id=rules_id, **columns
    )


def get_standard(session: Session, ref: StandardRef, as_of: datetime | None = None) -> Recorded[Standard]:
    key = {"name": ref.name, "prepared": ref.prepared}
    return _get(session, standards, key, Standard, as_of, f"standard {ref}")


def made_from(session: Session, ref: StandardRef) -> list[StandardRef]:
    """The standards made from this one (latest versions): following the chain down (P-14)."""
    rows = session.execute(
        select(standards.c.name, standards.c.prepared)
        .where(
            standards.c.source_kind == SOURCE_STANDARD,
            standards.c.source_name == ref.name,
            standards.c.source_key == ref.prepared.isoformat(),
        )
        .distinct()
        .order_by(standards.c.prepared, standards.c.name)
    ).all()
    return [StandardRef(name=r.name, prepared=r.prepared) for r in rows if _still_from(session, r, ref)]


def _still_from(session: Session, row, ref: StandardRef) -> bool:
    latest = get_standard(session, StandardRef(name=row.name, prepared=row.prepared)).item.source
    return isinstance(latest, StandardRef) and latest == ref


def save_batch(
    session: Session,
    batch: PrepBatch,
    rules_id: int,
    actor: Actor,
    expected_version: int = 0,
    reason: str | None = None,
) -> Recorded[PrepBatch]:
    recorded = _save(
        session,
        prep_batches,
        {"code": batch.code},
        batch,
        actor,
        expected_version,
        reason,
        f"batch {batch.code}",
        rules_id=rules_id,
    )
    used = {line.standard for s in batch.samples for c in s.cups for line in c.spikes}
    for ref in sorted(used, key=lambda r: (r.name, r.prepared)):
        session.execute(
            batch_standards.insert().values(
                batch_row_id=recorded.row_id, standard_name=ref.name, standard_prepared=ref.prepared
            )
        )
    return recorded


def get_batch(session: Session, code: str, as_of: datetime | None = None) -> Recorded[PrepBatch]:
    return _get(session, prep_batches, {"code": code}, PrepBatch, as_of, f"batch {code}")


def history_batch(session: Session, code: str) -> list[Recorded[PrepBatch]]:
    rows = session.execute(
        select(prep_batches).where(prep_batches.c.code == code).order_by(prep_batches.c.version)
    ).all()
    return [_recorded(row, PrepBatch) for row in rows]


def batches_using(session: Session, ref: StandardRef) -> list[str]:
    """Codes of the batches whose current version used this standard: when a standard turns out bad."""
    codes = session.scalars(
        select(prep_batches.c.code)
        .join(batch_standards, batch_standards.c.batch_row_id == prep_batches.c.id)
        .where(
            batch_standards.c.standard_name == ref.name, batch_standards.c.standard_prepared == ref.prepared
        )
        .distinct()
        .order_by(prep_batches.c.code)
    ).all()
    current = []
    for code in codes:
        batch = get_batch(session, code).item
        if any(line.standard == ref for s in batch.samples for c in s.cups for line in c.spikes):
            current.append(code)
    return current


def _save(session, table: Table, key: dict, item, actor, expected_version, reason, what, **columns):
    reason = (reason or "").strip() or None
    if expected_version > 0 and reason is None:
        raise ValueError(f"{what}: a correction needs a reason")
    latest = _latest_version(session, table, key)
    if latest != expected_version:
        raise ConcurrentChange(f"{what}: you edited version {expected_version}, the latest is {latest}")
    set_change_context(session, actor, reason or f"record {what}")
    try:
        with session.begin_nested():
            row_id = session.execute(
                table.insert().values(
                    **key,
                    **columns,
                    version=expected_version + 1,
                    body=item.model_dump(mode="json"),
                    reason=reason,
                    created_by_id=actor.id,
                    created_by=actor_json(actor),
                )
            ).inserted_primary_key[0]
    except IntegrityError as error:
        raise ConcurrentChange(
            f"{what} version {expected_version + 1} was written by someone else"
        ) from error
    return _recorded(session.execute(select(table).where(table.c.id == row_id)).one(), type(item))


def _latest_version(session, table: Table, key: dict) -> int:
    version = session.scalar(
        select(table.c.version).where(*_match(table, key)).order_by(table.c.version.desc()).limit(1)
    )
    return version or 0


def _get(session, table: Table, key: dict, model, as_of: datetime | None, what: str):
    row = session.execute(
        select(table)
        .where(*_match(table, key), as_of_filter(table.c.created_at, as_of))
        .order_by(table.c.version.desc())
        .limit(1)
    ).one_or_none()
    if row is None:
        raise NotFound(f"no {what}" + (f" as of {as_of.isoformat()}" if as_of else ""))
    return _recorded(row, model)


def _match(table: Table, key: dict) -> list:
    return [table.c[name] == value for name, value in key.items()]


def _recorded(row, model) -> Recorded:
    mapping = row._mapping
    return Recorded[model](
        row_id=row.id,
        version=row.version,
        item=model.model_validate(row.body),
        rules_id=mapping.get("rules_id"),
        reason=row.reason,
        created_by=Actor.model_validate(row.created_by),
        created_at=row.created_at,
    )


def list_batches(session: Session, as_of: datetime | None = None) -> list[Recorded[PrepBatch]]:
    """Every batch's latest version (as of `as_of`), newest first."""
    return _list(session, prep_batches, ("code",), PrepBatch, as_of)


def list_standards(session: Session, as_of: datetime | None = None) -> list[Recorded[Standard]]:
    """Every standard's latest version (as of `as_of`), newest first."""
    return _list(session, standards, ("name", "prepared"), Standard, as_of)


def list_stocks(session: Session, as_of: datetime | None = None) -> list[Recorded[Stock]]:
    return _list(session, stocks, ("name", "lot"), Stock, as_of)


def _list(session, table: Table, key: tuple[str, ...], model, as_of) -> list:
    rows = session.execute(
        select(table).where(as_of_filter(table.c.created_at, as_of)).order_by(table.c.id)
    ).all()
    latest = {}
    for row in rows:
        latest[tuple(getattr(row, k) for k in key)] = row  # ordered by id: the last one wins
    return [_recorded(row, model) for row in sorted(latest.values(), key=lambda r: r.id, reverse=True)]


def every_version(session: Session, kind: str) -> list[Recorded]:
    """Every stored version of every stock, standard or batch (`kind`), oldest first: what `verify` checks."""
    table, model = {
        "stock": (stocks, Stock),
        "standard": (standards, Standard),
        "batch": (prep_batches, PrepBatch),
    }[kind]
    return [_recorded(row, model) for row in session.execute(select(table).order_by(table.c.id)).all()]
