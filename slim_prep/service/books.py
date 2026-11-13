"""What the host calls to keep the standards book and the prep book (P-11, P-14…P-16).

Each call loads what it needs (the published rules, the source, the standards a batch names), lets the
domain calculate and check, and records the result. They flush; the host commits.
"""

from datetime import date, datetime, timedelta

from slim_data.service.handoff import prepped_batch
from sqlalchemy.orm import Session

from slim_prep.domain.actor import Actor
from slim_prep.domain.ports import SampleLookup, StockLookup, sample_problems
from slim_prep.domain.prep import CupFigures, PrepBatch, figures
from slim_prep.domain.problems import PrepRefused, Problem
from slim_prep.domain.rules import PrepRules
from slim_prep.domain.standards import Standard, StandardRef, Stock, make_standard
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
    stocks: StockLookup | None = None,
) -> Recorded[Standard]:
    """Makes a standard from its recipe step and source (a standard, or a stock's (name, lot)): its
    concentration and expiry are calculated. A correction passes the version it corrects and a reason.

    With `stocks` (the host's register, P-28) a stock's lot is taken from it, refused if the register
    refuses it, and kept in the stock book as it was used (a new version when the register's copy moved,
    e.g. an opened lot's earlier expiry), so `verify` remakes the standard from what it was made from.
    Without, the stock book is the register, as before P-28."""
    rules = get_rules(session, rules_id).rules
    if isinstance(source, StandardRef):
        found = books.get_standard(session, source).item
    elif stocks is not None:
        found = _registered_stock(session, stocks, *source, prepared, actor)
    else:
        found = books.get_stock(session, *source).item
    standard = make_standard(rules, recipe, step, found, prepared, actor.display, pipettes, actor.id)
    return books.save_standard(session, standard, rules_id, actor, expected_version, reason)


def _registered_stock(
    session: Session, stocks: StockLookup, name: str, lot: str, on: date, actor: Actor
) -> Stock:
    found = stocks.stock(name, lot, on)
    if isinstance(found, str):
        raise PrepRefused([Problem(where="source", message=f"{name} lot {lot}: {found}")])
    try:
        kept = books.get_stock(session, found.name, found.lot)
    except NotFound:
        books.save_stock(session, found, actor)
    else:
        if kept.item != found:
            books.save_stock(session, found, actor, kept.version, "as the reference-material register has it")
    return found


def record_batch(
    session: Session,
    batch: PrepBatch,
    rules_id: int | None,
    actor: Actor,
    lookup: SampleLookup,
    now: datetime,
    expected_version: int = 0,
    reason: str | None = None,
) -> tuple[Recorded[PrepBatch], tuple[CupFigures, ...]]:
    """Checks the batch against its TR (P-23), its rules and the standards book, calculates its figures
    and records it. A new batch takes `rules_id` (the lab's current rules). A correction (`expected_version`
    > 0) keeps the batch's code, method, analysis and rules (P-24): pass None, or the batch's own rules;
    moving to other rules is `move_to_rules`. A correction checks against their TR only the samples the
    batch didn't hold before (P-29). `now` bounds the entered prep time (P-25)."""
    held: frozenset[str] = frozenset()
    if expected_version:
        before = books.get_batch(session, batch.code)
        problems = [
            Problem(where=what, message=f"a correction keeps the batch's {what} ({was!r})")
            for what, was, given in (
                ("method", before.item.method, batch.method),
                ("analysis", before.item.analysis, batch.analysis),
            )
            if was != given
        ]
        if rules_id is not None and rules_id != before.rules_id:
            problems.append(
                Problem(where="rules", message=f"the batch is under rules {before.rules_id}: move it first")
            )
        if problems:
            raise PrepRefused(problems)
        rules_id = before.rules_id
        held = _samples(before.item)
    elif rules_id is None:
        raise PrepRefused([Problem(where="rules", message="a new batch is recorded under the current rules")])
    return _record(session, batch, rules_id, actor, lookup, now, expected_version, reason, held)


def move_to_rules(
    session: Session,
    code: str,
    rules_id: int,
    actor: Actor,
    lookup: SampleLookup,
    now: datetime,
    expected_version: int,
    reason: str,
) -> tuple[Recorded[PrepBatch], tuple[CupFigures, ...]]:
    """The batch as it stands, rechecked and recorded under other rules: a recorded step with a reason
    (P-24; review B9), never a side effect of a correction. Its samples are already taken (P-29)."""
    before = books.get_batch(session, code)
    if before.rules_id == rules_id:
        raise PrepRefused([Problem(where="rules", message=f"batch {code} is already under rules {rules_id}")])
    return _record(
        session, before.item, rules_id, actor, lookup, now, expected_version, reason, _samples(before.item)
    )


def _samples(batch: PrepBatch) -> frozenset[str]:
    return frozenset(s.sample for s in batch.samples)


def next_batch_code(session: Session, rules: PrepRules) -> str | None:
    """The next free code in the lab's series (P-26), for the new-batch screen to offer; None when the
    rules give no prefix."""
    prefix = rules.batch_prefix
    if prefix is None:
        return None
    used = [b.item.code.removeprefix(prefix) for b in books.list_batches(session)]
    numbers = [int(n) for n in used if n.isascii() and n.isdigit()]
    return f"{prefix}{max(numbers, default=0) + 1:04d}"


def _record(session, batch, rules_id, actor, lookup, now, expected_version, reason, held=frozenset()):
    """`held`: samples the batch already held; their TR isn't asked again (P-29)."""
    rules = get_rules(session, rules_id).rules
    problems = sample_problems(
        (s.sample for s in batch.samples if s.sample not in held), batch.analysis, lookup
    )
    problems += _time_problems(batch, rules, now, new=not expected_version)
    if not expected_version:
        problems += _code_problems(session, batch.code, rules)
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


def _time_problems(batch: PrepBatch, rules: PrepRules, now: datetime, new: bool) -> list[Problem]:
    """Entered times (P-25): never in the future; a new batch's prep within the rules' window."""
    problems = [
        Problem(where=what, message=f"{step.at:%Y-%m-%d %H:%M} is in the future")
        for what, step in (("prep", batch.prep), ("pour_out", batch.pour_out))
        if step is not None and step.at > now
    ]
    window = rules.entry_window_days
    if new and window is not None and batch.prep.at < now - timedelta(days=window):
        problems.append(Problem(where="prep", message=f"more than {window} days ago: ask a supervisor"))
    return problems


def _code_problems(session: Session, code: str, rules: PrepRules) -> list[Problem]:
    """A new batch's code is in the lab's series and not already a batch in results (P-26; review B6)."""
    problems = []
    if not rules.batch_code_fits(code):
        problems.append(Problem(where="code", message=f"prep batch codes are {rules.batch_prefix}0001, …"))
    if prepped_batch(session, code) is not None:
        problems.append(
            Problem(where="code", message=f"{code} is already a batch in results: choose another")
        )
    return problems


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
