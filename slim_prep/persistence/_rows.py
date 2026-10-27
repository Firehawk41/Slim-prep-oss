"""Small helpers shared by the repositories."""

from datetime import datetime

from sqlalchemy import Column, select
from sqlalchemy.orm import Session

from slim_prep.domain.actor import Actor
from slim_prep.persistence.types import db_now


class NotFound(LookupError):
    pass


class ConcurrentChange(RuntimeError):
    """Someone else wrote that version first; reload and retry."""


class NotAllowed(PermissionError):
    pass


def actor_json(actor: Actor) -> dict:
    data = actor.model_dump(mode="json")
    data["roles"] = sorted(data["roles"])
    return data


def as_of_filter(column: Column, as_of: datetime | None):
    """`created_at <= as_of`; None reads the present."""
    if as_of is not None and as_of.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")
    return column <= as_of if as_of is not None else column.isnot(None)


def database_time(session: Session) -> datetime:
    """Now, by the database clock: what an `as_of` read compares against."""
    return session.scalar(select(db_now()))
