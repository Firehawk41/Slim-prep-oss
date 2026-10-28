"""The planned run list for a set of prep batches (P-13), as the host asks for it."""

from collections.abc import Sequence

from sqlalchemy.orm import Session

from slim_prep.domain.ports import SampleLookup
from slim_prep.domain.prep import figures
from slim_prep.domain.problems import PrepRefused, Problem
from slim_prep.domain.run_list import RunEntry, plan_run
from slim_prep.persistence import books
from slim_prep.persistence.rules import get_rules


def run_list_for(
    session: Session, codes: Sequence[str], lookup: SampleLookup, rules_id: int
) -> tuple[RunEntry, ...]:
    """The run list for these batches in this order, sequenced by the given rules (the lab's current
    ones, usually); each batch's figures come from the rules it was recorded under. Each sample's matrix
    is its TR's chemical, the matched SLIM chemical where there is one (P-23)."""
    batches, matrices, missing = [], {}, []
    for code in codes:
        recorded = books.get_batch(session, code)
        batches.append((recorded.item, figures(recorded.item, get_rules(session, recorded.rules_id).rules)))
        for sample in recorded.item.samples:
            info = lookup.sample(sample.sample)
            if info is None:
                missing.append(Problem(where=sample.sample, message="no such sample"))
            else:
                matrices[sample.sample] = info.matrix
    if missing:
        raise PrepRefused(missing)
    return plan_run(batches, matrices, get_rules(session, rules_id).rules)
