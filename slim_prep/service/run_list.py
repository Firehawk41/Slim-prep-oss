"""The planned run list for a set of prep batches (P-13), as the host asks for it."""

from collections.abc import Mapping, Sequence

from sqlalchemy.orm import Session

from slim_prep.domain.prep import figures
from slim_prep.domain.run_list import RunEntry, plan_run
from slim_prep.persistence import books
from slim_prep.persistence.rules import get_rules


def run_list_for(
    session: Session, codes: Sequence[str], chemicals: Mapping[str, str], rules_id: int
) -> tuple[RunEntry, ...]:
    """The run list for these batches in this order, sequenced by the given rules (the lab's current
    ones, usually); each batch's figures come from the rules it was recorded under."""
    batches = []
    for code in codes:
        recorded = books.get_batch(session, code)
        batches.append((recorded.item, figures(recorded.item, get_rules(session, recorded.rules_id).rules)))
    return plan_run(batches, chemicals, get_rules(session, rules_id).rules)
