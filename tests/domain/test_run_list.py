"""The planned run list (P-13): check standards between matrices and every N samples; spikes."""

from decimal import Decimal

import pytest

from slim_prep.domain.prep import Cup, CupKind, PrepSample, Weighing, figures
from slim_prep.domain.problems import PrepRefused
from slim_prep.domain.rules import RunListRule
from slim_prep.domain.run_list import EntryKind, plan_run, run_list_csv
from tests.factories import DILUTE_AND_SHOOT, RULES, batch, evaporation_sample, spike_line

D = Decimal


def evaporation(code, first, n):
    samples = tuple(evaporation_sample(f"TR00042-{i:02d}") for i in range(first, first + n))
    b = batch(code=code, samples=samples)
    return b, figures(b, RULES)


def kinds(entries):
    """A compact picture: C cup, S spike, K check standard, O opening/closing."""
    letters = {EntryKind.CUP: "C", EntryKind.SPIKE: "S", EntryKind.CHECK: "K", EntryKind.OTHER: "O"}
    return "".join(letters[e.kind] for e in entries)


def test_a_check_after_every_10_samples_and_between_matrices_spikes_before_it():
    ipa, hno3 = evaporation("PB-1", 1, 12), evaporation("PB-2", 13, 2)
    chemicals = {f"TR00042-{i:02d}": "IPA" for i in range(1, 13)} | {
        "TR00042-13": "HNO3",
        "TR00042-14": "hno3",
    }
    entries = plan_run([ipa, hno3], chemicals, RULES)
    # 2 cups per sample, spikes held to the end of the matrix; 10 samples, then a check (dups don't count)
    assert kinds(entries) == "OK" + "C" * 20 + "K" + "C" * 4 + "S" * 12 + "K" + "C" * 4 + "SS" + "K"
    assert [e.position for e in entries] == list(range(1, len(entries) + 1))
    first, spike = entries[2], entries[27]
    assert (first.label, first.batch, first.sample, first.cup, first.dilution) == (
        "TR00042-01 1", "PB-1", "TR00042-01", 1, D("0.06"),
    )  # fmt: skip
    assert spike.label == "TR00042-01 spike" and entries[-1].label == "Check standard"


def test_the_count_restarts_at_each_matrix():
    a, b = evaporation("PB-1", 1, 6), evaporation("PB-2", 7, 6)
    chemicals = {f"TR00042-{i:02d}": ("IPA" if i <= 6 else "HNO3") for i in range(1, 13)}
    assert (
        kinds(plan_run([a, b], chemicals, RULES))
        == "OK" + "C" * 12 + "S" * 6 + "K" + "C" * 12 + "S" * 6 + "K"
    )


def test_dilute_and_shoot_spikes_follow_their_sample_and_one_cup_has_no_number():
    method = DILUTE_AND_SHOOT.model_copy(update={"name": "d&s", "sample_cups": 1, "spike_cups": 1,
                                                 "spikes_at_block_end": False})  # fmt: skip
    rules = RULES.model_copy(update={"methods": (*RULES.methods, method)})
    vial = Weighing(gross=D("0.5"), final=D("10"))

    def sample(sid):
        spiked = Cup(number=2, kind=CupKind.SPIKE, weighing=vial, spikes=(spike_line(),))
        return PrepSample(sample=sid, cups=(Cup(number=1, weighing=vial), spiked))

    b = batch(method="d&s", pour_out=None, samples=(sample("TR00042-01"), sample("TR00042-02")))
    entries = plan_run([(b, figures(b, rules))], {"TR00042-01": "IPA", "TR00042-02": "IPA"}, rules)
    assert kinds(entries) == "OK" + "CS" + "CS" + "K"
    assert entries[2].label == "TR00042-01" and entries[3].dilution == D(20)


def test_the_lab_sets_the_rule():
    rule = RunListRule(
        check_label="CCV", check_between_matrices=False, check_every=None, opening=(), closing=()
    )
    rules = RULES.model_copy(update={"run_list": rule})
    a, b = evaporation("PB-1", 1, 11), evaporation("PB-2", 12, 1)
    chemicals = {f"TR00042-{i:02d}": ("IPA" if i <= 11 else "HNO3") for i in range(1, 13)}
    assert "K" not in kinds(plan_run([a, b], chemicals, rules))


def test_missing_chemical_or_method_is_refused():
    a = evaporation("PB-1", 1, 1)
    with pytest.raises(PrepRefused, match="TR00042-01: no chemical"):
        plan_run([a], {}, RULES)
    with pytest.raises(PrepRefused, match="no prep method 'evaporation'"):
        plan_run([a], {"TR00042-01": "IPA"}, RULES.model_copy(update={"methods": (DILUTE_AND_SHOOT,)}))


def test_the_csv_sample_list():
    entries = plan_run([evaporation("PB-1", 1, 1)], {"TR00042-01": "IPA"}, RULES)
    lines = run_list_csv(entries).splitlines()
    assert lines[0] == "position,label,type,batch,sample_id,cup,dilution_factor"
    assert lines[1] == "1,Calibration blank,other,,,,"
    assert lines[3] == "3,TR00042-01 1,cup,PB-1,TR00042-01,1,0.06"
    assert lines[5] == "5,TR00042-01 spike,spike,PB-1,TR00042-01,3,0.06"
    assert lines[2] == "2,Check standard,check,,,,"
