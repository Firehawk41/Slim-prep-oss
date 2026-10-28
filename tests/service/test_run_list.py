"""The host's run list call (P-13)."""

from slim_prep.domain.run_list import EntryKind
from slim_prep.persistence import books
from slim_prep.persistence.rules import publish_rules
from slim_prep.service.run_list import run_list_for
from tests.factories import ANALYST, QUALITY, RULES, SAMPLES, batch, chain


def test_run_list_for_recorded_batches(session):
    rules_id = publish_rules(session, RULES, QUALITY).id
    for standard in chain():
        books.save_standard(session, standard, rules_id, ANALYST)
    books.save_batch(session, batch(), rules_id, ANALYST)
    entries = run_list_for(session, ["PB-0001"], SAMPLES, rules_id)
    assert [e.kind for e in entries].count(EntryKind.CUP) == 2
