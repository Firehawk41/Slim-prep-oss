"""The standards book (P-14, P-15, P-16)."""

from datetime import date, timedelta

import pytest

from slim_prep.domain.problems import PrepRefused
from slim_prep.domain.standards import StandardRef, make_standard
from tests.factories import RULES, SPIKE_RECIPE, TODAY, chain, conc, stock

R = SPIKE_RECIPE.name


def test_the_chain_calculates_concentration_and_expiry():
    twenty, fifty = chain()
    assert twenty.concentration == conc("20") and twenty.expires == date(2027, 1, 27)  # 3 months
    assert fifty.concentration == conc("50", "ppb") and fifty.expires == TODAY + timedelta(weeks=1)
    assert twenty.source == stock() and fifty.source == StandardRef(name="20 ppm", prepared=TODAY)
    assert fifty.elements == ("Cu", "Fe", "Ni") and fifty.pipettes == ("P100-1",)
    assert str(fifty.ref) == "50 ppb (2026-10-27)" and str(stock()) == "Multi-element stock A lot L-0042"


def test_expiry_is_capped_at_the_source_unless_the_lab_says_not():
    short = stock(expires=TODAY + timedelta(days=10))
    assert make_standard(RULES, R, "20 ppm", short, TODAY, "ana").expires == short.expires
    uncapped = RULES.model_copy(update={"cap_expiry_at_source": False})
    assert make_standard(uncapped, R, "20 ppm", short, TODAY, "ana").expires == date(2027, 1, 27)


def test_unknown_recipe_or_step_is_refused():
    with pytest.raises(PrepRefused, match="no recipe 'x'"):
        make_standard(RULES, "x", "20 ppm", stock(), TODAY, "ana")
    with pytest.raises(PrepRefused, match="has no step '5 ppb'"):
        make_standard(RULES, R, "5 ppb", stock(), TODAY, "ana")


def test_every_problem_is_reported_at_once():
    twenty, _ = chain()
    with pytest.raises(PrepRefused) as refused:
        make_standard(
            RULES,
            R,
            "20 ppm",
            stock(name="Other stock", expires=TODAY - timedelta(days=1)),
            TODAY,
            "ana",
            ("P-unknown",),
        )
    assert [p.where for p in refused.value.problems] == ["source", "source", "pipettes"]
    assert "expired on 2026-10-26" in str(refused.value)


def test_a_standard_source_must_be_the_step_before_and_made_earlier():
    twenty, fifty = chain()
    with pytest.raises(PrepRefused, match="made from 20 ppm, not 50 ppb"):
        make_standard(RULES, R, "50 ppb", fifty, TODAY, "ana")
    with pytest.raises(PrepRefused, match="was made after 2026-10-26"):
        make_standard(RULES, R, "50 ppb", twenty, TODAY - timedelta(days=1), "ana")
    with pytest.raises(PrepRefused, match="expired"):
        make_standard(RULES, R, "50 ppb", twenty, date(2027, 2, 1), "ana")
