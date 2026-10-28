"""`verify` (P7): the prep book remakes and rechecks itself, and agrees with slim-data."""

from datetime import timedelta
from decimal import Decimal

from slim_data.domain.observations import CupDilution
from slim_data.domain.values import SampleRef
from slim_data.persistence import migrate as results_migrate
from slim_data.persistence.observations import correct_prep

from slim_prep.domain.prep import SpikeLine
from slim_prep.persistence import books
from slim_prep.persistence.rules import publish_rules
from slim_prep.service.handoff import send_to_results
from slim_prep.service.verify import verify
from tests.factories import (
    ANALYST,
    QUALITY,
    RULES,
    batch,
    chain,
    conc,
    evaporation_cup,
    evaporation_sample,
    stock,
)
from tests.service.test_handoff import METALS, RESULTS_ANA


def _book(session):
    results_migrate.upgrade(session.connection())
    rules_id = publish_rules(session, RULES, QUALITY).id
    books.save_stock(session, stock(), ANALYST)
    twenty, fifty = chain()
    books.save_standard(session, twenty, rules_id, ANALYST)
    books.save_standard(session, fifty, rules_id, ANALYST)
    books.save_batch(session, batch(), rules_id, ANALYST)
    return rules_id, twenty, fifty


def test_a_sound_book_verifies(session):
    _book(session)
    send_to_results(session, "PB-0001", RESULTS_ANA, 7, METALS, "ppb")
    report = verify(session)
    assert report.ok and (report.standards, report.batches, report.sent) == (2, 1, 1)


def test_a_standard_that_isnt_what_its_recipe_makes_is_reported(session):
    rules_id, twenty, _ = _book(session)
    forged = twenty.model_copy(
        update={"prepared": twenty.prepared - timedelta(days=1), "concentration": conc("25")}
    )
    books.save_standard(session, forged, rules_id, ANALYST)
    assert verify(session).problems == (
        # the expiry too: it counts from the standard's own (forged) date
        f"standard {forged.ref} version 1: differs from a remake in concentration, expires",
    )


def test_a_batch_whose_spike_or_rules_dont_hold_is_reported(session):
    rules_id, _, fifty = _book(session)
    wrong = SpikeLine.of(fifty.model_copy(update={"concentration": conc("60", "ppb")}), Decimal(10), "P100-1")
    sample = evaporation_sample(
        cups=(*evaporation_sample().cups[:2], evaporation_cup(3, kind=2, spikes=(wrong,)))
    )
    books.save_batch(session, batch(samples=(sample,), pour_out=None), rules_id, ANALYST, 1, "forged")
    problems = verify(session).problems
    assert problems[0].startswith("batch PB-0001 version 2: no longer passes its rules")
    assert problems[1] == f"batch PB-0001 version 2: {fifty.ref} differs from the standards book"


def test_slim_data_holding_other_dilutions_than_the_prep_book_is_reported(session):
    _book(session)
    send_to_results(session, "PB-0001", RESULTS_ANA, 7, METALS, "ppb")
    other = CupDilution(sample=SampleRef.parse("TR00042-01"), role=1, replicate=1, dilution=Decimal("0.5"))
    correct_prep(session, "PB-0001", RESULTS_ANA, "changed behind slim-prep's back", dilutions=[other])
    assert verify(session).problems == (
        "batch PB-0001 as sent (version 1): TR00042-01 CUP 1: slim-data holds 0.5, the prep book 0.06",
    )


def test_what_cant_be_found_is_reported(session):
    from sqlalchemy import insert

    from slim_prep.persistence.tables import sent_batches

    rules_id, twenty, fifty = _book(session)
    orphan = twenty.model_copy(
        update={"source": stock(lot="L-9999"), "prepared": twenty.prepared - timedelta(days=2)}
    )
    books.save_standard(session, orphan, rules_id, ANALYST)
    stray = SpikeLine.of(
        fifty.model_copy(update={"prepared": fifty.prepared - timedelta(days=9)}), Decimal(10), "P100-1"
    )
    sample = evaporation_sample(
        cups=(*evaporation_sample().cups[:2], evaporation_cup(3, kind=2, spikes=(stray,)))
    )
    books.save_batch(session, batch(samples=(sample,)), rules_id, ANALYST, 1, "other standard")
    session.execute(insert(sent_batches).values(code="PB-0001", version=1, created_by_id="x", created_by={}))
    session.execute(insert(sent_batches).values(code="PB-0009", version=1, created_by_id="x", created_by={}))
    problems = verify(session).problems
    assert any("can't be remade: no stock" in p for p in problems)
    assert f"batch PB-0001 version 2: {stray.standard} was not in the standards book" in problems
    assert "batch PB-0001 as sent (version 1): slim-data has no such batch" in problems
    assert "batch PB-0009 as sent (version 1): that version isn't in the prep book" in problems
