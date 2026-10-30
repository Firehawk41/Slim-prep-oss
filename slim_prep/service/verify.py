"""`verify` (P7): the prep book checks itself, as slim-data's `verify` does for results (D-76).

  - every standard version is remade from its recipe step and its source as they stood when it was
    recorded: the same concentration, elements and expiry;
  - every batch version still passes its rules (the figures can be worked out) and its spike lines say
    what the standards book said then;
  - every batch sent to results: slim-data holds the cup dilutions of the version last sent.
Nothing is written. The host's `cli verify` runs it beside slim-data's.
"""

from datetime import timedelta

from slim_data.domain.enums import ReadingRole
from slim_data.domain.values import SampleRef
from slim_data.service.handoff import prepped_batch
from sqlalchemy import select
from sqlalchemy.orm import Session

from slim_prep.domain.base import Frozen
from slim_prep.domain.prep import CupKind, figures
from slim_prep.domain.problems import PrepRefused
from slim_prep.domain.standards import Stock, make_standard
from slim_prep.persistence import books
from slim_prep.persistence._rows import NotFound
from slim_prep.persistence.rules import get_rules
from slim_prep.persistence.tables import sent_batches

_EPSILON = timedelta(microseconds=1)  # "as it stood when recorded": the row itself included


class PrepVerifyReport(Frozen):
    standards: int
    batches: int
    sent: int
    problems: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.problems


def verify(session: Session) -> PrepVerifyReport:
    problems: list[str] = []
    standards = books.every_version(session, "standard")
    for recorded in standards:
        problem = _remake(session, recorded)
        if problem:
            problems.append(f"standard {recorded.item.ref} version {recorded.version}: {problem}")
    batches = books.every_version(session, "batch")
    for recorded in batches:
        for problem in _recheck(session, recorded):
            problems.append(f"batch {recorded.item.code} version {recorded.version}: {problem}")
    sent = session.execute(
        select(sent_batches.c.code, sent_batches.c.version).order_by(sent_batches.c.id)
    ).all()
    latest = {row.code: row.version for row in sent}
    for code, version in latest.items():
        problem = _in_results(session, code, version)
        if problem:
            problems.append(f"batch {code} as sent (version {version}): {problem}")
    return PrepVerifyReport(
        standards=len(standards), batches=len(batches), sent=len(latest), problems=tuple(problems)
    )


def _remake(session: Session, recorded) -> str | None:
    stored = recorded.item
    then = recorded.created_at + _EPSILON
    try:
        rules = get_rules(session, recorded.rules_id).rules
        if isinstance(stored.source, Stock):
            source = books.get_stock(session, stored.source.name, stored.source.lot, as_of=then).item
        else:
            source = books.get_standard(session, stored.source, as_of=then).item
        again = make_standard(
            rules, stored.recipe, stored.name, source, stored.prepared, stored.analyst, stored.pipettes,
            stored.analyst_id,
        )  # fmt: skip
    except (PrepRefused, NotFound) as error:
        return f"can't be remade: {error}"
    fields = ("concentration", "elements", "expires")
    differ = [f for f in fields if getattr(again, f) != getattr(stored, f)]
    return f"differs from a remake in {', '.join(differ)}" if differ else None


def _recheck(session: Session, recorded) -> list[str]:
    batch = recorded.item
    then = recorded.created_at + _EPSILON
    problems = []
    try:
        figures(batch, get_rules(session, recorded.rules_id).rules)
    except PrepRefused as error:
        problems.append(f"no longer passes its rules: {error}")
    for line in (line for s in batch.samples for c in s.cups for line in c.spikes):
        try:
            standard = books.get_standard(session, line.standard, as_of=then).item
        except NotFound:
            problems.append(f"{line.standard} was not in the standards book")
            continue
        if (standard.concentration, standard.elements, standard.expires) != (
            line.concentration,
            line.elements,
            line.expires,
        ):
            problems.append(f"{line.standard} differs from the standards book")
    return problems


def _in_results(session: Session, code: str, version: int) -> str | None:
    recorded = next((r for r in books.history_batch(session, code) if r.version == version), None)
    if recorded is None:
        return "that version isn't in the prep book"
    held = prepped_batch(session, code)
    if held is None:
        return "slim-data has no such batch"
    cups = figures(recorded.item, get_rules(session, recorded.rules_id).rules)
    role = {CupKind.SAMPLE: ReadingRole.CUP, CupKind.SPIKE: ReadingRole.SPIKE}
    for sample in {c.sample for c in cups}:
        mine = sorted((c for c in cups if c.sample == sample), key=lambda c: c.cup)
        for kind in CupKind:
            for replicate, cup in enumerate((c for c in mine if c.kind == kind), start=1):
                there = held.prep_dilution(SampleRef.parse(sample), role[kind], replicate)
                if there != cup.dilution:
                    which = f"{sample} {role[kind].name} {replicate}"
                    return f"{which}: slim-data holds {there}, the prep book {cup.dilution}"
    return None
