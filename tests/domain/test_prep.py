"""The prep book's figures (P-03…P-07): net, solution, dilution, spike level; checks against the rules."""

from datetime import datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from slim_prep.domain.prep import Cup, CupKind, PrepSample, StepRecord, Weighing, figures
from slim_prep.domain.problems import PrepRefused, Problem
from tests.factories import RULES, batch, conc, evaporation_cup, evaporation_sample, spike_line

D = Decimal


def problems(**changes):
    with pytest.raises(PrepRefused) as refused:
        figures(batch(**changes), RULES)
    return [str(p) for p in refused.value.problems]


def test_evaporation_net_dilution_and_spike_level():
    cup1, cup2, spiked = figures(batch(), RULES)
    assert cup1.net == D("10.0000") and cup1.solution == D("0.6000")
    assert cup1.dilution == D("0.06")  # concentrated: below 1 (slim-data D-93)
    assert spiked.kind == CupKind.SPIKE and cup2.added == ()
    # 10 µL of 50 ppb into 10 g: 50 ppb × 0.01 g ÷ 10 g = 50 ppt, for each element of the standard
    assert spiked.added == (("Cu", conc("50", "ppt")), ("Fe", conc("50", "ppt")), ("Ni", conc("50", "ppt")))


def test_dilute_and_shoot_tares_the_vial():
    cups = (
        Cup(number=1, weighing=Weighing(gross=D("0.5"), final=D("10.0"))),
        Cup(number=2, weighing=Weighing(gross=D("0.4"), final=D("10.0"))),
    )
    sample = PrepSample(sample="TR00042-01", cups=cups)
    one, two = figures(batch(method="dilute and shoot", pour_out=None, samples=(sample,)), RULES)
    assert one.net == D("0.5") and one.dilution == D(20) and two.dilution == D(25)


def test_unknown_method_is_refused_first():
    with pytest.raises(PrepRefused, match="no prep method 'x'"):
        figures(batch(method="x"), RULES)


def test_lab_lists_and_steps_are_checked():
    cups = (
        evaporation_cup(1, balance="BAL-9", pipettes=("P-9",)),
        evaporation_cup(2),
        evaporation_cup(3, kind=CupKind.SPIKE, spikes=(spike_line(pipette="P-8"),)),
    )
    found = problems(balance="BAL-0", samples=(evaporation_sample(cups=cups),))
    assert found == [
        "balance: 'BAL-0' is not on the lab's list",
        "TR00042-01 cup 1: balance 'BAL-9' is not on the lab's list",
        "TR00042-01 cup 1: pipette 'P-9' is not on the lab's list",
        "TR00042-01 cup 3: pipette 'P-8' is not on the lab's list",
    ]


def test_the_pour_out_step_follows_the_method():
    assert problems(pour_out=None) == ["pour_out: evaporation records who poured out"]
    sample = PrepSample(
        sample="TR00042-01",
        cups=(
            Cup(number=1, weighing=Weighing(gross=D(1), final=D(2))),
            Cup(number=2, weighing=Weighing(gross=D(1), final=D(2))),
        ),
    )
    assert problems(method="dilute and shoot", samples=(sample,)) == [
        "pour_out: dilute and shoot has no pour-out step"
    ]


def test_cup_counts_follow_the_method():
    sample = evaporation_sample(cups=(evaporation_cup(1),))
    assert problems(samples=(sample,)) == [
        "TR00042-01: evaporation has 2 sample cup(s), not 1",
        "TR00042-01: evaporation has 1 spike cup(s), not 0",
    ]


def test_an_expired_or_later_standard_is_refused():
    late = datetime(2026, 11, 4, 9, 0)  # the 50 ppb keeps one week: through 3 Nov
    assert problems(prep=StepRecord(analyst="ana", at=late)) == [
        "TR00042-01 cup 3: 50 ppb (2026-10-27) expired on 2026-11-03"
    ]
    early = datetime(2026, 10, 26, 9, 0)
    assert problems(prep=StepRecord(analyst="ana", at=early)) == [
        "TR00042-01 cup 3: 50 ppb (2026-10-27) was made after 2026-10-26"
    ]


def weighed(**w):
    return evaporation_sample(
        cups=(
            Cup(number=1, weighing=Weighing(**{"gross": D(12), "final": D(3), **w})),
            evaporation_cup(2),
            evaporation_cup(3, kind=CupKind.SPIKE, spikes=(spike_line(),)),
        )
    )


@pytest.mark.parametrize(
    "w, message",
    [
        (dict(cap=D("0.5")), "evaporation needs the tare"),
        (dict(tare=D(2)), "evaporation needs the cap weight"),
        (dict(tare=D(2), cap=D("0.5"), gross=D("2.4")), "net weight -0.1 g: gross must exceed tare and cap"),
        (dict(tare=D(2), cap=D("0.5"), final=D(2)), "solution 0 g: final must exceed the tare"),
    ],
)
def test_weighings_follow_the_method(w, message):
    assert problems(samples=(weighed(**w),)) == [f"TR00042-01 cup 1: {message}"]


def test_a_method_without_a_cap_refuses_one_and_a_tared_vial_refuses_a_tare():
    no_cap = RULES.method("evaporation").model_copy(update={"name": "no cap", "weighs_cap": False})
    rules = RULES.model_copy(update={"methods": (*RULES.methods, no_cap)})
    with pytest.raises(PrepRefused, match="no cap doesn't weigh a cap"):
        figures(batch(method="no cap"), rules)
    cup = Cup(number=1, weighing=Weighing(tare=D(1), cap=D(1), gross=D(1), final=D(2)))
    sample = PrepSample(
        sample="TR00042-01", cups=(cup, Cup(number=2, weighing=Weighing(gross=D(1), final=D(2))))
    )
    with pytest.raises(PrepRefused) as refused:
        figures(batch(method="dilute and shoot", pour_out=None, samples=(sample,)), RULES)
    assert [p.message for p in refused.value.problems] == [
        "dilute and shoot tares the vessel: no tare",
        "dilute and shoot tares the vessel: no cap",
    ]


def test_cup_shape_is_checked_on_entry():
    with pytest.raises(ValidationError, match="the spike gets its own cup"):
        evaporation_cup(1, spikes=(spike_line(),))
    with pytest.raises(ValidationError, match="needs at least one spike"):
        evaporation_cup(3, kind=CupKind.SPIKE)
    with pytest.raises(ValidationError, match="an element is spiked twice"):
        evaporation_cup(3, kind=CupKind.SPIKE, spikes=(spike_line(), spike_line()))
    with pytest.raises(ValidationError, match="cup number is used twice"):
        evaporation_sample(cups=(evaporation_cup(1), evaporation_cup(1)))
    with pytest.raises(ValidationError, match="not a lab sample ID"):
        evaporation_sample(sample="42-1")
    with pytest.raises(ValidationError, match="appears twice"):
        batch(samples=(evaporation_sample(), evaporation_sample()))
    with pytest.raises(ValidationError, match="float"):
        Weighing(gross=1.5, final=D(1))


def test_a_problem_without_a_place_prints_its_message():
    assert str(Problem(where="", message="m")) == "m"
