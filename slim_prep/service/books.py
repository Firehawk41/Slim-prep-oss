"""What the host calls to keep the standards book and the prep book (P-11, P-14…P-16).

Each call loads what it needs (the published rules, the source, the standards a batch names), lets the
domain calculate and check, and records the result. They flush; the host commits.
"""

from datetime import date

from sqlalchemy.orm import Session

from slim_prep.domain.actor import Actor
from slim_prep.domain.prep import CupFigures, PrepBatch, figures
from slim_prep.domain.problems import PrepRefused, Problem
from slim_prep.domain.standards import Standard, StandardRef, make_standard
from slim_prep.persistence import books
from slim_prep.persistence._rows import NotFound
from slim_prep.persistence.books import Recorded
from slim_prep.persistence.rules import get_rules


def record_standard(
    session: Session,
    rules_id: int,
    recipe: str,
    step: str,
    source: StandardRef | tuple[str, str],
    prepared: date,
    actor: Actor,
    pipettes: tuple[str, ...] = (),
    expected_version: int = 0,
    reason: str | None = None,
) -> Recorded[Standard]:
    """Makes a standard from its recipe step and source (a standard, or a stock's (name, lot)): its
    concentration and expiry are calculated. A correction passes the version it corrects and a reason."""
    rules = get_rules(session, rules_id).rules
    if isinstance(source, StandardRef):
        found = books.get_standard(session, source).item
    else:
        found = books.get_stock(session, *source).item
    standard = make_standard(rules, recipe, step, found, prepared, actor.id, pipettes)
    return books.save_standard(session, standard, rules_id, actor, expected_version, reason)


def record_batch(
    session: Session,
    batch: PrepBatch,
    rules_id: int,
    actor: Actor,
    expected_version: int = 0,
    reason: str | None = None,
) -> tuple[Recorded[PrepBatch], tuple[CupFigures, ...]]:
    """Checks the batch against the rules and the standards book, calculates its figures and records it."""
    rules = get_rules(session, rules_id).rules
    problems = []
    for sample in batch.samples:
        for cup in sample.cups:
            for line in cup.spikes:
                problem = _spike_matches_book(session, line)
                if problem:
                    problems.append(Problem(where=f"{sample.sample} cup {cup.number}", message=problem))
    if problems:
        raise PrepRefused(problems)
    result = figures(batch, rules)
    return books.save_batch(session, batch, rules_id, actor, expected_version, reason), result


def _spike_matches_book(session: Session, line) -> str | None:
    """A spike line snapshots its standard; the snapshot must be what the book says now."""
    try:
        standard = books.get_standard(session, line.standard).item
    except NotFound:
        return f"{line.standard} is not in the standards book"
    if (standard.concentration, standard.elements, standard.expires) != (
        line.concentration,
        line.elements,
        line.expires,
    ):
        return f"{line.standard}: the line's concentration, elements or expiry differ from the standards book"
    return None
