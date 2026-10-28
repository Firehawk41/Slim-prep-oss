"""Published rules and the versioned books (P-10, P-17), on SQLite and Postgres."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from slim_prep.domain.standards import StandardRef
from slim_prep.persistence import books
from slim_prep.persistence._rows import ConcurrentChange, NotAllowed, NotFound, database_time
from slim_prep.persistence.rules import current_rules, get_rules, publish_rules
from tests.factories import ANALYST, QUALITY, RULES, batch, chain, stock


def test_quality_publishes_rules_once_per_content(session):
    first = publish_rules(session, RULES, QUALITY)
    assert publish_rules(session, RULES, QUALITY).id == first.id
    assert get_rules(session, first.id).rules == RULES
    changed = publish_rules(session, RULES.model_copy(update={"cap_expiry_at_source": False}), QUALITY)
    assert changed.id != first.id and current_rules(session, RULES.name).id == changed.id
    assert current_rules(session, RULES.name, as_of=first.published_at).id == first.id
    assert current_rules(session, "other") is None
    with pytest.raises(NotFound):
        get_rules(session, 999)


def test_an_analyst_may_not_publish_rules(session):
    with pytest.raises(NotAllowed, match="quality sets them"):
        publish_rules(session, RULES, ANALYST)


def test_versions_corrections_and_as_of(session):
    first = books.save_stock(session, stock(), ANALYST)
    assert first.version == 1 and first.reason is None and first.created_by == ANALYST
    before = database_time(session)
    with pytest.raises(ValueError, match="needs a reason"):
        books.save_stock(session, stock(lot="L-0042"), ANALYST, expected_version=1)
    fixed = books.save_stock(
        session, stock(expires=first.item.expires - timedelta(days=30)), QUALITY, 1, "typo"
    )
    assert fixed.version == 2 and fixed.reason == "typo"
    assert books.get_stock(session, "Multi-element stock A", "L-0042").version == 2
    assert books.get_stock(session, "Multi-element stock A", "L-0042", as_of=before).version == 1
    with pytest.raises(ConcurrentChange, match="you edited version 1, the latest is 2"):
        books.save_stock(session, stock(), ANALYST, expected_version=1, reason="again")
    with pytest.raises(NotFound, match="as of"):
        books.get_stock(session, "Multi-element stock A", "L-0042", as_of=datetime(2000, 1, 1, tzinfo=UTC))
    with pytest.raises(ValueError, match="timezone-aware"):
        books.get_stock(session, "Multi-element stock A", "L-0042", as_of=datetime(2030, 1, 1))


def test_standards_trace_their_chain_and_batches(session):
    rules_id = publish_rules(session, RULES, QUALITY).id
    twenty, fifty = chain()
    books.save_standard(session, twenty, rules_id, ANALYST)
    books.save_standard(session, fifty, rules_id, ANALYST)
    assert books.get_standard(session, fifty.ref).item == fifty
    assert books.get_standard(session, twenty.ref).item.source == stock()
    assert books.made_from(session, twenty.ref) == [fifty.ref]
    assert books.made_from(session, fifty.ref) == []
    saved = books.save_batch(session, batch(), rules_id, ANALYST)
    assert saved.rules_id == rules_id and books.get_batch(session, "PB-0001").item == batch()
    assert books.batches_using(session, fifty.ref) == ["PB-0001"]
    assert books.batches_using(session, twenty.ref) == []
    # a correction that no longer uses the standard drops the batch from the list, history keeps it
    sample = batch().samples[0]
    no_spike = sample.model_copy(update={"cups": sample.cups[:2]})
    books.save_batch(session, batch(samples=(no_spike,)), rules_id, ANALYST, 1, "spike cup spilled")
    assert books.batches_using(session, fifty.ref) == []
    assert [r.version for r in books.history_batch(session, "PB-0001")] == [1, 2]


def test_a_standard_corrected_to_another_source_leaves_the_old_chain(session):
    rules_id = publish_rules(session, RULES, QUALITY).id
    twenty, fifty = chain()
    other = twenty.model_copy(update={"prepared": twenty.prepared - timedelta(days=1)})
    for standard in (twenty, other, fifty):
        books.save_standard(session, standard, rules_id, ANALYST)
    moved = fifty.model_copy(update={"source": other.ref})
    books.save_standard(session, moved, rules_id, ANALYST, 1, "made from yesterday's 20 ppm")
    assert books.made_from(session, twenty.ref) == []
    assert books.made_from(session, other.ref) == [fifty.ref]


def test_a_race_on_the_same_version_is_a_concurrent_change(session, monkeypatch):
    books.save_stock(session, stock(), ANALYST)
    monkeypatch.setattr(books, "_latest_version", lambda *a: 0)  # as if read before the other write
    with pytest.raises(ConcurrentChange, match="written by someone else"):
        books.save_stock(session, stock(), ANALYST)


@pytest.mark.parametrize(
    "statement", ["UPDATE prep_book_stocks SET lot = 'x'", "DELETE FROM prep_book_stocks"]
)
def test_the_database_refuses_updates_and_deletes(session, statement):
    books.save_stock(session, stock(), ANALYST)
    session.flush()
    with pytest.raises(DBAPIError, match="append-only"):
        with session.begin_nested():
            session.execute(text(statement))


def test_unknown_standard_is_not_found(session):
    with pytest.raises(NotFound):
        books.get_standard(session, StandardRef(name="x", prepared=datetime(2026, 1, 1).date()))


def test_lists_show_each_records_latest_version(session):
    rules_id = publish_rules(session, RULES, QUALITY).id
    books.save_stock(session, stock(), ANALYST)
    books.save_stock(session, stock(), ANALYST, 1, "typo")
    twenty, fifty = chain()
    books.save_standard(session, twenty, rules_id, ANALYST)
    books.save_standard(session, fifty, rules_id, ANALYST)
    books.save_batch(session, batch(), rules_id, ANALYST)
    assert [r.version for r in books.list_stocks(session)] == [2]
    assert [r.item.name for r in books.list_standards(session)] == ["50 ppb", "20 ppm"]
    assert [r.item.code for r in books.list_batches(session)] == ["PB-0001"]


def test_the_demo_rules_and_stock_are_valid():
    from datetime import date

    from slim_prep.demo import DEMO_RULES, demo_stock
    from slim_prep.domain.standards import make_standard

    stock_ = demo_stock(date(2027, 12, 31))
    twenty = make_standard(DEMO_RULES, "multi-element spike", "20 ppm", stock_, date(2026, 10, 27), "ana")
    assert str(twenty.concentration) == "20 ppm" and len(twenty.elements) == 10
