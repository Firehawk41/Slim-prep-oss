"""Publishing the prep rules (P-17): numbered, content-hashed, immutable. Publishing the same content
again returns the existing row. Only quality (or a supervisor, until the host has a quality role)."""

import hashlib
import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from slim_prep.domain.actor import Actor
from slim_prep.domain.base import Frozen
from slim_prep.domain.rules import PrepRules
from slim_prep.persistence._rows import NotAllowed, NotFound, actor_json, as_of_filter
from slim_prep.persistence.audit import set_change_context
from slim_prep.persistence.tables import prep_rules


class PublishedRules(Frozen):
    id: int
    rules: PrepRules
    published_at: datetime


def content_hash(rules: PrepRules) -> str:
    canonical = json.dumps(rules.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def publish_rules(session: Session, rules: PrepRules, actor: Actor) -> PublishedRules:
    if not actor.may_publish_rules:
        raise NotAllowed(f"{actor.display} may not publish prep rules: quality sets them (P-17)")
    digest = content_hash(rules)
    if session.scalar(select(prep_rules.c.id).where(prep_rules.c.content_hash == digest)) is None:
        set_change_context(session, actor, f"publish prep rules {rules.name}")
        session.execute(
            prep_rules.insert().values(
                name=rules.name,
                content_hash=digest,
                body=rules.model_dump(mode="json"),
                published_by_id=actor.id,
                published_by=actor_json(actor),
            )
        )
    return _published(session.execute(select(prep_rules).where(prep_rules.c.content_hash == digest)).one())


def get_rules(session: Session, id: int) -> PublishedRules:
    row = session.execute(select(prep_rules).where(prep_rules.c.id == id)).one_or_none()
    if row is None:
        raise NotFound(f"no published prep rules {id}")
    return _published(row)


def current_rules(session: Session, name: str, as_of: datetime | None = None) -> PublishedRules | None:
    """The latest rules of that name published by `as_of` (default: now)."""
    row = session.execute(
        select(prep_rules)
        .where(prep_rules.c.name == name, as_of_filter(prep_rules.c.created_at, as_of))
        .order_by(prep_rules.c.created_at.desc(), prep_rules.c.id.desc())
        .limit(1)
    ).one_or_none()
    return None if row is None else _published(row)


def _published(row) -> PublishedRules:
    return PublishedRules(id=row.id, rules=PrepRules.model_validate(row.body), published_at=row.created_at)
