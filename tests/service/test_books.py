"""The host's calls: making standards from the book, recording a batch (P-11, P-14…P-16)."""

from datetime import timedelta

import pytest

from slim_prep.domain.prep import SpikeLine
from slim_prep.domain.problems import PrepRefused
from slim_prep.persistence import books
from slim_prep.persistence.rules import publish_rules
from slim_prep.service.books import record_batch, record_standard
from tests.factories import ANALYST, QUALITY, RULES, SPIKE_RECIPE, TODAY, batch, conc, evaporation_cup, stock

R = SPIKE_RECIPE.name


@pytest.fixture
def book(session):
    rules_id = publish_rules(session, RULES, QUALITY).id
    books.save_stock(session, stock(), ANALYST)
    twenty = record_standard(
        session, rules_id, R, "20 ppm", ("Multi-element stock A", "L-0042"), TODAY, ANALYST
    )
    fifty = record_standard(session, rules_id, R, "50 ppb", twenty.item.ref, TODAY, ANALYST, ("P100-1",))
    return rules_id, twenty.item, fifty.item


def test_standards_are_made_from_the_book(book):
    _, twenty, fifty = book
    assert twenty.concentration == conc("20") and fifty.concentration == conc("50", "ppb")
    assert twenty.analyst == ANALYST.id and fifty.pipettes == ("P100-1",)


def test_a_standard_correction_is_a_new_version(session, book):
    rules_id, twenty, _ = book
    fixed = record_standard(
        session, rules_id, R, "50 ppb", twenty.ref, TODAY, ANALYST, ("P1000-1",), 1, "wrong pipette"
    )
    assert fixed.version == 2 and fixed.item.pipettes == ("P1000-1",)


def test_a_batch_is_checked_calculated_and_recorded(session, book):
    rules_id, _, _ = book
    recorded, cups = record_batch(session, batch(), rules_id, ANALYST)
    assert recorded.version == 1 and len(cups) == 3 and str(cups[0].dilution) == "0.06"
    assert cups[2].added[0] == ("Cu", conc("50", "ppt"))


def test_a_spike_must_match_the_standards_book(session, book):
    rules_id, _, fifty = book
    forged = SpikeLine.of(
        fifty.model_copy(update={"expires": fifty.expires + timedelta(days=30)}), 10, "P100-1"
    )
    missing = SpikeLine.of(fifty.model_copy(update={"prepared": TODAY - timedelta(days=2)}), 10, "P100-1")
    sample = batch().samples[0]
    cups = (
        *sample.cups[:2],
        evaporation_cup(3, kind=sample.cups[2].kind, spikes=(forged,)),
        evaporation_cup(4, kind=sample.cups[2].kind, spikes=(missing,)),
    )
    with pytest.raises(PrepRefused) as refused:
        record_batch(session, batch(samples=(sample.model_copy(update={"cups": cups}),)), rules_id, ANALYST)
    assert [str(p) for p in refused.value.problems] == [
        "TR00042-01 cup 3: 50 ppb (2026-10-27): the line's concentration, elements or expiry differ from the "
        "standards book",
        "TR00042-01 cup 4: 50 ppb (2026-10-25) is not in the standards book",
    ]


def test_a_batch_that_fails_the_rules_is_not_recorded(session, book):
    rules_id, _, _ = book
    with pytest.raises(PrepRefused, match="records who poured out"):
        record_batch(session, batch(pour_out=None), rules_id, ANALYST)
    with pytest.raises(books.NotFound):
        books.get_batch(session, "PB-0001")
