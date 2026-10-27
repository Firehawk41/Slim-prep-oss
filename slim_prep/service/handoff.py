"""Handing a ready batch to slim-data (P-11, P-12; slim-data D-95).

`results_batch` turns a prep batch and its figures into slim-data's `PrepBatch`: the samples, the spike
amounts in the analysis's unit (elements the analysis doesn't measure are left out), and each cup's
dilution. Sample cups become CUP replicates 1, 2… and spike cups SPIKE replicates, in cup-number order.
`send_to_results` registers it in slim-data and records which version was sent. The host commits.
"""

from collections.abc import Collection

from slim_data.domain.actor import Actor as ResultsActor
from slim_data.domain.enums import ReadingRole
from slim_data.domain.observations import CupDilution, SpikeAddition
from slim_data.domain.observations import PrepBatch as ResultsBatch
from slim_data.domain.values import AnalyteRef, Quantity, SampleRef
from slim_data.persistence.observations import register_batch
from sqlalchemy import select
from sqlalchemy.orm import Session

from slim_prep.domain.actor import Actor
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
    analysis_id: int,
    analytes: Collection[str],
    unit: str,
) -> ResultsBatch:
    """Registers the batch's current version in slim-data. Once per batch: a correction after that is a
    later slice (slim-data D-95 point 4)."""
    if sent_version(session, code) is not None:
        raise PrepRefused([Problem(where=code, message="already sent to results")])
    recorded = books.get_batch(session, code)
    rules = get_rules(session, recorded.rules_id).rules
    sent = results_batch(recorded.item, figures(recorded.item, rules), analysis_id, analytes, unit)
    registered = register_batch(session, sent, actor)
    set_change_context(session, Actor(id=actor.id, display=actor.display), f"send batch {code} to results")
    session.execute(
        sent_batches.insert().values(
            code=code,
            version=recorded.version,
            created_by_id=actor.id,
            created_by=actor.model_dump(mode="json"),
        )
    )
    return registered


def sent_version(session: Session, code: str) -> int | None:
    """The batch version slim-data received, or None if it hasn't been sent."""
    return session.scalar(select(sent_batches.c.version).where(sent_batches.c.code == code))
