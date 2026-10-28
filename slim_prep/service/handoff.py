"""Handing a ready batch to slim-data (P-11, P-12; slim-data D-95).

`results_batch` turns a prep batch and its figures into slim-data's `PrepBatch`: the samples, the spike
amounts in the analysis's unit (elements the analysis doesn't measure are left out), and each cup's
dilution. Sample cups become CUP replicates 1, 2… and spike cups SPIKE replicates, in cup-number order.
`send_to_results` registers it in slim-data and records which version was sent. After that, a corrected
batch goes with `send_correction` (P-20, slim-data D-96): its changed dilutions and spike amounts become
the next versions there; the host then re-evaluates. Both sends check the samples against their TR
again (P-23): a request cancelled since the batch was recorded stops it. The host commits.
"""

from collections.abc import Collection

from slim_data.domain.actor import Actor as ResultsActor
from slim_data.domain.enums import ReadingRole
from slim_data.domain.observations import CupDilution, SpikeAddition
from slim_data.domain.observations import PrepBatch as ResultsBatch
from slim_data.domain.values import AnalyteRef, Quantity, SampleRef
from slim_data.persistence.observations import correct_prep, register_batch
from slim_data.persistence.observations import get_batch as results_get_batch
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from slim_prep.domain.actor import Actor
from slim_prep.domain.ports import SampleLookup, sample_problems
from slim_prep.domain.prep import CupFigures, CupKind, PrepBatch, figures
from slim_prep.domain.problems import PrepRefused, Problem
from slim_prep.domain.units import UNITS
from slim_prep.persistence import books
from slim_prep.persistence.audit import set_change_context
from slim_prep.persistence.rules import get_rules
from slim_prep.persistence.tables import sent_batches

_ROLE = {CupKind.SAMPLE: ReadingRole.CUP, CupKind.SPIKE: ReadingRole.SPIKE}


def results_batch(
    batch: PrepBatch, cups: tuple[CupFigures, ...], analysis_id: int, analytes: Collection[str], unit: str
) -> ResultsBatch:
    if unit not in UNITS:
        raise PrepRefused([Problem(where="unit", message=f"spike amounts can't be given in {unit!r}")])
    problems, spikes, dilutions = [], [], []
    for sample in batch.samples:
        ref = SampleRef.parse(sample.sample)
        mine = sorted((c for c in cups if c.sample == sample.sample), key=lambda c: c.cup)
        for kind in CupKind:
            for replicate, cup in enumerate((c for c in mine if c.kind == kind), start=1):
                dilutions.append(
                    CupDilution(sample=ref, role=_ROLE[kind], replicate=replicate, dilution=cup.dilution)
                )
        seen = set()
        for cup in (c for c in mine if c.kind == CupKind.SPIKE):
            for element, added in cup.added:
                if element not in analytes:
                    continue
                if element in seen:
                    problems.append(
                        Problem(
                            where=sample.sample, message=f"{element} is spiked in two cups: results takes one"
                        )
                    )
                    continue
                seen.add(element)
                amount = Quantity(value=added.to(unit).value, unit=unit)
                spikes.append(
                    SpikeAddition(
                        sample=ref, analyte=AnalyteRef(analysis_id=analysis_id, code=element), added=amount
                    )
                )
    if problems:
        raise PrepRefused(problems)
    return ResultsBatch(
        code=batch.code,
        analysis_id=analysis_id,
        prep_method=batch.method,
        samples=tuple(SampleRef.parse(s.sample) for s in batch.samples),
        spikes=tuple(spikes),
        dilutions=tuple(dilutions),
    )


def send_to_results(
    session: Session,
    code: str,
    actor: ResultsActor,
    lookup: SampleLookup,
    analysis_id: int,
    analytes: Collection[str],
    unit: str,
) -> ResultsBatch:
    """Registers the batch's current version in slim-data, once; corrections go with `send_correction`."""
    if sent_version(session, code) is not None:
        raise PrepRefused([Problem(where=code, message="already sent to results: send the correction")])
    recorded = books.get_batch(session, code)
    _check_samples(recorded.item, lookup)
    rules = get_rules(session, recorded.rules_id).rules
    sent = results_batch(recorded.item, figures(recorded.item, rules), analysis_id, analytes, unit)
    try:
        registered = register_batch(session, sent, actor)
    except ValueError:  # an instrument file registered the code first (P-26)
        message = "results already has a batch with this code, from an instrument file: prep a new batch"
        raise PrepRefused([Problem(where=code, message=message)]) from None
    _record_sent(session, code, recorded.version, actor, f"send batch {code} to results")
    return registered


def send_correction(
    session: Session,
    code: str,
    actor: ResultsActor,
    lookup: SampleLookup,
    analysis_id: int,
    analytes: Collection[str],
    unit: str,
) -> tuple[ResultsBatch, int]:
    """Sends a batch corrected since it was sent: changed cup dilutions and spike amounts become their
    next versions in slim-data, with the correction's reason (P-20, D-96). Same samples, cups and spiked
    elements as sent: anything else is a new batch. Returns slim-data's batch and how many entries
    changed (0: nothing to send). The host then re-evaluates the batch in slim-data."""
    sent = sent_version(session, code)
    if sent is None:
        raise PrepRefused([Problem(where=code, message="not sent to results yet")])
    recorded = books.get_batch(session, code)
    current = results_get_batch(session, code)
    if recorded.version == sent:
        return current, 0
    _check_samples(recorded.item, lookup)
    rules = get_rules(session, recorded.rules_id).rules
    new = results_batch(recorded.item, figures(recorded.item, rules), analysis_id, analytes, unit)
    shapes = (
        ("samples", set(current.samples), set(new.samples)),
        ("cups", _cups(current), _cups(new)),
        ("spiked elements", _spiked(current), _spiked(new)),
    )
    problems = [
        Problem(where=code, message=f"the {what} changed since it was sent: prep a new batch")
        for what, before, after in shapes
        if before != after
    ]
    if problems:
        raise PrepRefused(problems)
    reason = recorded.reason or f"prep batch {code} corrected"
    corrected, changed = correct_prep(session, code, actor, reason, new.dilutions, new.spikes)
    _record_sent(session, code, recorded.version, actor, reason)
    return corrected, changed


def sent_version(session: Session, code: str) -> int | None:
    """The latest batch version slim-data received, or None if it hasn't been sent."""
    return session.scalar(select(func.max(sent_batches.c.version)).where(sent_batches.c.code == code))


def _check_samples(batch: PrepBatch, lookup: SampleLookup) -> None:
    problems = sample_problems((s.sample for s in batch.samples), batch.analysis, lookup)
    if problems:
        raise PrepRefused(problems)


def _cups(batch: ResultsBatch) -> set:
    return {(d.sample, d.role, d.replicate) for d in batch.dilutions}


def _spiked(batch: ResultsBatch) -> set:
    return {(s.sample, s.analyte) for s in batch.spikes}


def _record_sent(session: Session, code: str, version: int, actor: ResultsActor, reason: str) -> None:
    set_change_context(session, Actor(id=actor.id, display=actor.display), reason)
    session.execute(
        sent_batches.insert().values(
            code=code, version=version, created_by_id=actor.id, created_by=actor.model_dump(mode="json")
        )
    )
