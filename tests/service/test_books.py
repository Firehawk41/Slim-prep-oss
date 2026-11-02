"""The host's calls: making standards from the book, recording a batch (P-11, P-14…P-16)."""

from datetime import timedelta

import pytest
from slim_data.persistence import migrate as results_migrate

from slim_prep.domain.prep import SpikeLine
from slim_prep.domain.problems import PrepRefused
from slim_prep.persistence import books
from slim_prep.persistence.rules import publish_rules
from slim_prep.service.books import record_batch, record_standard
from tests.factories import (
    ANALYST,
    NOW,
    QUALITY,
    RULES,
    SAMPLES,
    SPIKE_RECIPE,
    TODAY,
    batch,
    conc,
    evaporation_cup,
    stock,
)

R = SPIKE_RECIPE.name


@pytest.fixture
def book(session):
    results_migrate.upgrade(session.connection())  # slim-prep checks codes against slim-data's batches
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
    assert (twenty.analyst, twenty.analyst_id) == (ANALYST.display, ANALYST.id)  # P-27
    assert fifty.pipettes == ("P100-1",)


def test_a_standard_correction_is_a_new_version(session, book):
    rules_id, twenty, _ = book
    fixed = record_standard(
        session, rules_id, R, "50 ppb", twenty.ref, TODAY, ANALYST, ("P1000-1",), 1, "wrong pipette"
    )
    assert fixed.version == 2 and fixed.item.pipettes == ("P1000-1",)


def test_a_batch_is_checked_calculated_and_recorded(session, book):
    rules_id, _, _ = book
    recorded, cups = record_batch(session, batch(), rules_id, ANALYST, SAMPLES, NOW)
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
        record_batch(
            session,
            batch(samples=(sample.model_copy(update={"cups": cups}),)),
            rules_id,
            ANALYST,
            SAMPLES,
            NOW,
        )
    assert [str(p) for p in refused.value.problems] == [
        "TR00042-01 cup 3: 50 ppb (2026-10-27): the line's concentration, elements or expiry differ from the "
        "standards book",
        "TR00042-01 cup 4: 50 ppb (2026-10-25) is not in the standards book",
    ]


def test_a_batch_that_fails_the_rules_is_not_recorded(session, book):
    rules_id, _, _ = book
    with pytest.raises(PrepRefused, match="records who poured out"):
        record_batch(session, batch(pour_out=None), rules_id, ANALYST, SAMPLES, NOW)
    with pytest.raises(books.NotFound):
        books.get_batch(session, "PB-0001")


class Register:
    """The host's StockLookup over slim-quality (P-28), in miniature."""

    def __init__(self, *lots, refusals=None):
        self.lots = {(s.name, s.lot): s for s in lots}
        self.refusals = refusals or {}

    def stock(self, name, lot, on):
        if (name, lot) in self.refusals:
            return self.refusals[(name, lot)]
        return self.lots.get((name, lot), "not in the register")


def test_a_standard_takes_its_lot_from_the_register(session):
    """P-28: the register's lot is used and kept in the stock book as it was used."""
    rules_id = publish_rules(session, RULES, QUALITY).id
    lot = stock()
    made = record_standard(
        session, rules_id, R, "20 ppm", (lot.name, lot.lot), TODAY, ANALYST, stocks=Register(lot)
    )
    assert made.item.source == lot and books.get_stock(session, lot.name, lot.lot).version == 1
    again = record_standard(
        session,
        rules_id,
        R,
        "20 ppm",
        (lot.name, lot.lot),
        TODAY,
        ANALYST,
        expected_version=1,
        reason="x",
        stocks=Register(lot),
    )
    assert (
        again.version == 2 and books.get_stock(session, lot.name, lot.lot).version == 1
    )  # unchanged: not re-kept
    opened = lot.model_copy(update={"expires": TODAY + timedelta(days=30)})  # opened: an earlier expiry
    record_standard(
        session,
        rules_id,
        R,
        "20 ppm",
        (lot.name, lot.lot),
        TODAY,
        ANALYST,
        expected_version=2,
        reason="y",
        stocks=Register(opened),
    )
    kept = books.get_stock(session, lot.name, lot.lot)
    assert kept.version == 2 and kept.item.expires == TODAY + timedelta(days=30)
    assert kept.reason == "as the reference-material register has it"


def test_the_register_refuses_unknown_withdrawn_and_expired_lots(session):
    rules_id = publish_rules(session, RULES, QUALITY).id
    lot = stock()
    with pytest.raises(PrepRefused, match="not in the register"):
        record_standard(
            session, rules_id, R, "20 ppm", (lot.name, "NOPE"), TODAY, ANALYST, stocks=Register(lot)
        )
    withdrawn = Register(refusals={(lot.name, lot.lot): "withdrawn on 2026-01-01"})
    with pytest.raises(PrepRefused, match="withdrawn on 2026-01-01"):
        record_standard(session, rules_id, R, "20 ppm", (lot.name, lot.lot), TODAY, ANALYST, stocks=withdrawn)
    expired = lot.model_copy(update={"expires": TODAY - timedelta(days=1)})
    with pytest.raises(PrepRefused, match="expired"):
        record_standard(
            session, rules_id, R, "20 ppm", (lot.name, lot.lot), TODAY, ANALYST, stocks=Register(expired)
        )
