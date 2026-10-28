"""Guards for the 2026-10-28 review's module findings (slim-lims-oss docs/REVIEW_2026-10-28.md, B1–B10;
decisions P-23…P-27). Each test names the finding it keeps fixed."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from slim_data.domain.actor import Actor as ResultsActor
from slim_data.domain.enums import IdentitySource as ResultsIdentity
from slim_data.domain.enums import Role as ResultsRole
from slim_data.persistence import migrate as results_migrate
from slim_data.persistence.observations import get_batch as results_get_batch
from slim_data.persistence.observations import register_batch

from slim_prep.domain.ports import SampleState
from slim_prep.domain.prep import StepRecord, figures
from slim_prep.domain.problems import PrepRefused
from slim_prep.domain.run_list import EntryKind, RunEntry, run_list_csv
from slim_prep.persistence import books
from slim_prep.persistence.rules import publish_rules
from slim_prep.service.books import move_to_rules, next_batch_code, record_batch
from slim_prep.service.handoff import results_batch, send_correction, send_to_results
from slim_prep.service.run_list import run_list_for
from tests.factories import (
    ANALYST,
    AT,
    NOW,
    QUALITY,
    RULES,
    SAMPLES,
    FakeSamples,
    batch,
    chain,
    evaporation_cup,
    evaporation_sample,
    info,
)

RESULTS_ANA = ResultsActor(
    id="ana-1", display="Ana", roles=frozenset({ResultsRole.ANALYST}),
    identity_source=ResultsIdentity.AUTHENTICATED,
)  # fmt: skip
PREFIXED = RULES.model_copy(update={"batch_prefix": "PREP-", "entry_window_days": 7})


@pytest.fixture
def book(session):
    results_migrate.upgrade(session.connection())
    rules_id = publish_rules(session, RULES, QUALITY).id
    for standard in chain():
        books.save_standard(session, standard, rules_id, ANALYST)
    return rules_id


def refused(call) -> list[str]:
    with pytest.raises(PrepRefused) as error:
        call()
    return [str(p) for p in error.value.problems]


# --- B1: every sample is checked against its TR (P-23) --------------------------------------------


def test_b1_a_sample_must_exist_be_in_the_lab_and_have_ordered_the_analysis(session, book):
    two = tuple(evaporation_sample(f"TR00042-0{n}") for n in range(1, 5))
    lookup = FakeSamples(
        TR00042_01=None,
        TR00042_02=info("TR00042-02", SampleState.NOT_RECEIVED),
        TR00042_03=info("TR00042-03", analyses=("5_anions_ic",)),
        TR00042_04=info("TR00042-04", SampleState.CLOSED),
    )
    assert refused(lambda: record_batch(session, batch(samples=two), book, ANALYST, lookup, NOW)) == [
        "TR00042-01: no such sample",
        "TR00042-02: its request isn't checked in yet",
        "TR00042-03: 10_elements_icpms wasn't ordered for it",
        "TR00042-04: its request is closed (invoiced)",
    ]


def test_b1_a_request_cancelled_after_recording_stops_the_send(session, book):
    record_batch(session, batch(), book, ANALYST, SAMPLES, NOW)
    cancelled = FakeSamples(TR00042_01=info("TR00042-01", SampleState.CANCELLED))
    assert refused(
        lambda: send_to_results(session, "PB-0001", RESULTS_ANA, cancelled, 7, ("Cu",), "ppb")
    ) == ["TR00042-01: its request was cancelled"]
    send_to_results(session, "PB-0001", RESULTS_ANA, SAMPLES, 7, ("Cu",), "ppb")
    sample = evaporation_sample()
    cups = (evaporation_cup(1, final="2.7000"), *sample.cups[1:])
    fixed = batch(samples=(sample.model_copy(update={"cups": cups}),))
    record_batch(session, fixed, None, ANALYST, SAMPLES, NOW, 1, "final misread")
    assert refused(
        lambda: send_correction(session, "PB-0001", RESULTS_ANA, cancelled, 7, ("Cu",), "ppb")
    ) == ["TR00042-01: its request was cancelled"]


def test_b1_the_run_list_groups_by_the_matched_chemical(session, book):
    two = (evaporation_sample(), evaporation_sample("TR00042-02"))
    record_batch(session, batch(samples=two), book, ANALYST, SAMPLES, NOW)
    by_name = FakeSamples(TR00042_02=info("TR00042-02", chemical="isopropanol"))
    matched = FakeSamples(
        TR00042_01=info("TR00042-01", chemical_id=4),
        TR00042_02=info("TR00042-02", chemical="isopropanol", chemical_id=4),
    )
    entries = [run_list_for(session, ["PB-0001"], lookup, book) for lookup in (by_name, matched)]
    checks = [sum(e.kind == EntryKind.CHECK for e in run) for run in entries]
    assert checks == [3, 2]  # opening + closing, and one between the two "matrices" until matched
    assert refused(lambda: run_list_for(session, ["PB-0001"], FakeSamples(TR00042_02=None), book)) == [
        "TR00042-02: no such sample"
    ]


# --- B2, B9: a correction keeps code, method, analysis and its rules version (P-24) -----------------


def test_b2_a_correction_keeps_the_method_and_analysis(session, book):
    record_batch(session, batch(), book, ANALYST, SAMPLES, NOW)
    lookup = FakeSamples(TR00042_01=info("TR00042-01", analyses=("10_elements_icpms", "36_elements_icpms")))
    other = batch(method="dilute and shoot", analysis="36_elements_icpms")
    assert refused(lambda: record_batch(session, other, None, ANALYST, lookup, NOW, 1, "x")) == [
        "method: a correction keeps the batch's method ('evaporation')",
        "analysis: a correction keeps the batch's analysis ('10_elements_icpms')",
    ]


def test_b9_a_correction_is_checked_against_the_batchs_own_rules(session, book):
    record_batch(session, batch(), book, ANALYST, SAMPLES, NOW)
    stricter = publish_rules(session, RULES.model_copy(update={"balances": ("BAL-2",)}), QUALITY).id
    fixed = record_batch(session, batch(note="fixed"), None, ANALYST, SAMPLES, NOW, 1, "note")[0]
    assert fixed.rules_id == book  # BAL-1 is still fine under its own rules
    assert refused(lambda: record_batch(session, batch(), stricter, ANALYST, SAMPLES, NOW, 2, "x")) == [
        f"rules: the batch is under rules {book}: move it first"
    ]
    assert refused(
        lambda: move_to_rules(session, "PB-0001", stricter, ANALYST, SAMPLES, NOW, 2, "new rules")
    ) == ["balance: 'BAL-1' is not on the lab's list"]
    looser = publish_rules(
        session, RULES.model_copy(update={"pipettes": (*RULES.pipettes, "P10-1")}), QUALITY
    ).id
    moved, _ = move_to_rules(session, "PB-0001", looser, ANALYST, SAMPLES, NOW, 2, "rules v3")
    assert (moved.version, moved.rules_id, moved.reason) == (3, looser, "rules v3")
    assert refused(lambda: move_to_rules(session, "PB-0001", looser, ANALYST, SAMPLES, NOW, 3, "again")) == [
        f"rules: batch PB-0001 is already under rules {looser}"
    ]
    assert refused(lambda: record_batch(session, batch(code="PB-0002"), None, ANALYST, SAMPLES, NOW)) == [
        "rules: a new batch is recorded under the current rules"
    ]


# --- B4: the prep time is entered, bounded, in a zone (P-25) -----------------------------------------


def test_b4_entered_times_are_bounded(session):
    results_migrate.upgrade(session.connection())
    rules_id = publish_rules(session, PREFIXED, QUALITY).id
    for standard in chain():
        books.save_standard(session, standard, rules_id, ANALYST)
    late = NOW + timedelta(minutes=5)
    future = batch(
        code="PREP-0001", prep=StepRecord(analyst="ana", at=late), pour_out=StepRecord(analyst="p", at=late)
    )
    assert refused(lambda: record_batch(session, future, rules_id, ANALYST, SAMPLES, NOW)) == [
        f"prep: {late:%Y-%m-%d %H:%M} is in the future",
        f"pour_out: {late:%Y-%m-%d %H:%M} is in the future",
    ]
    assert refused(
        lambda: record_batch(
            session, batch(code="PREP-0001"), rules_id, ANALYST, SAMPLES, AT + timedelta(days=8)
        )
    ) == ["prep: more than 7 days ago: ask a supervisor"]
    with pytest.raises(ValidationError, match="timezone"):
        StepRecord(analyst="ana", at=datetime(2026, 10, 27, 9, 30))
    with pytest.raises(ValidationError, match="pour-out comes before the prep"):
        batch(pour_out=StepRecord(analyst="p", at=AT + timedelta(hours=1)))


# --- B6, B8: batch codes (P-26) ---------------------------------------------------------------------


@pytest.mark.parametrize("code", ["=HYPERLINK(1)", "-1", "@x", "a b", "a/b", "", "x" * 51])
def test_b8_a_batch_code_is_safe_anywhere(code):
    with pytest.raises(ValidationError):
        batch(code=code)


def test_b8_the_run_list_csv_never_starts_a_cell_with_a_formula():
    entry = RunEntry(position=1, label="=cmd|' /C calc'!A0", kind=EntryKind.OTHER)
    assert run_list_csv([entry]).splitlines()[1].startswith("1,'=cmd")


def test_b6_codes_follow_the_labs_series_and_never_reuse_one_in_results(session):
    results_migrate.upgrade(session.connection())
    rules_id = publish_rules(session, PREFIXED, QUALITY).id
    for standard in chain():
        books.save_standard(session, standard, rules_id, ANALYST)
    assert next_batch_code(session, PREFIXED) == "PREP-0001" and next_batch_code(session, RULES) is None
    assert refused(lambda: record_batch(session, batch(code="PB-0001"), rules_id, ANALYST, SAMPLES, NOW)) == [
        "code: prep batch codes are PREP-0001, …"
    ]
    taken = results_batch(batch(code="PREP-0001"), figures(batch(), RULES), 7, ("Cu",), "ppb")
    register_batch(session, taken, RESULTS_ANA)  # an instrument file got there first
    assert refused(
        lambda: record_batch(session, batch(code="PREP-0001"), rules_id, ANALYST, SAMPLES, NOW)
    ) == ["code: PREP-0001 is already a batch in results: choose another"]
    record_batch(session, batch(code="PREP-0002"), rules_id, ANALYST, SAMPLES, NOW)
    assert next_batch_code(session, PREFIXED) == "PREP-0003"


def test_b6_a_code_an_instrument_file_took_after_recording_is_refused_plainly(session, book):
    record_batch(session, batch(), book, ANALYST, SAMPLES, NOW)
    register_batch(session, results_batch(batch(), figures(batch(), RULES), 7, ("Cu",), "ppb"), RESULTS_ANA)
    assert refused(lambda: send_to_results(session, "PB-0001", RESULTS_ANA, SAMPLES, 7, ("Cu",), "ppb")) == [
        "PB-0001: results already has a batch with this code, from an instrument file: prep a new batch"
    ]
    assert results_get_batch(session, "PB-0001").code == "PB-0001"


# --- B7: who, with how the host knows (P-27) ---------------------------------------------------------


def test_b7_the_actor_and_the_analyst_are_recorded_with_their_ids(session, book):
    step = StepRecord(analyst="ANA", analyst_id="ana-1", at=AT)
    recorded, _ = record_batch(session, batch(prep=step), book, ANALYST, SAMPLES, NOW)
    again = books.get_batch(session, "PB-0001")
    assert again.item.prep.analyst_id == "ana-1"
    assert again.created_by.identity_source == ANALYST.identity_source
    old = StepRecord.model_validate({"analyst": "ana", "at": AT.isoformat()})  # before P-27: still reads
    assert old.analyst_id is None and AT.tzinfo is UTC
