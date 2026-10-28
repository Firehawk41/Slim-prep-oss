"""Concentrations (P-05, P-06) and the prep rules (P-02, P-15, P-16)."""

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from slim_prep.domain.rules import PrepMethod, PrepRules, Recipe, RecipeStep, ShelfLife
from slim_prep.domain.units import Concentration
from tests.factories import EVAPORATION, RULES, SPIKE_RECIPE, conc

D = Decimal


def test_units_convert_and_scale_to_the_largest_unit_at_1_or_more():
    assert conc("1").to("ppb") == conc("1000", "ppb")
    assert conc("1000").times(D("0.02")) == conc("20")
    assert conc("20").times(D("0.0025")) == conc("50", "ppb")
    assert conc("1", "ppt").times(D("0.5")) == conc("0.5", "ppt")
    assert str(conc("50", "ppb")) == "50 ppb"


def test_a_concentration_is_positive_and_never_a_float():
    with pytest.raises(ValidationError):
        conc("0")
    with pytest.raises(ValidationError, match="float"):
        Concentration(value=1.5, unit="ppm")


@pytest.mark.parametrize(
    "life, start, end",
    [
        (ShelfLife(amount=10, unit="days"), date(2026, 10, 27), date(2026, 11, 6)),
        (ShelfLife(amount=1, unit="weeks"), date(2026, 10, 27), date(2026, 11, 3)),
        (ShelfLife(amount=3, unit="months"), date(2026, 10, 27), date(2027, 1, 27)),
        (ShelfLife(amount=1, unit="months"), date(2027, 1, 31), date(2027, 2, 28)),
        (ShelfLife(amount=12, unit="months"), date(2026, 12, 15), date(2027, 12, 15)),
    ],
)
def test_shelf_life(life, start, end):
    assert life.after(start) == end
    assert str(ShelfLife(amount=3, unit="months")) == "3 months"


def test_a_recipe_knows_each_steps_source():
    assert SPIKE_RECIPE.source_of("20 ppm") == "Multi-element stock A"
    assert SPIKE_RECIPE.source_of("50 ppb") == "20 ppm"
    assert SPIKE_RECIPE.step("5 ppb") is None


def step(name, volume="100", final="10"):
    return RecipeStep(
        name=name, volume_ul=D(volume), final_ml=D(final), shelf_life=ShelfLife(amount=1, unit="weeks")
    )


def test_a_step_must_dilute():
    with pytest.raises(ValidationError, match="less than the final volume"):
        step("x", volume="10000", final="10")


@pytest.mark.parametrize("names", [("a", "a"), ("stock", "a")])
def test_recipe_step_names_are_unique(names):
    with pytest.raises(ValidationError, match="its own name"):
        Recipe(name="r", stock="stock", steps=tuple(step(n) for n in names))


def test_a_tared_vessel_has_no_cap():
    with pytest.raises(ValidationError, match="no separate cap"):
        PrepMethod(name="m", tared_vessel=True, weighs_cap=True)


def test_rules_find_methods_and_recipes():
    assert RULES.method("evaporation") == EVAPORATION and RULES.method("x") is None
    assert RULES.recipe(SPIKE_RECIPE.name) == SPIKE_RECIPE and RULES.recipe("x") is None
    assert RULES.cap_expiry_at_source


@pytest.mark.parametrize(
    "changes, what",
    [
        (dict(methods=(EVAPORATION, EVAPORATION)), "method"),
        (dict(recipes=(SPIKE_RECIPE, SPIKE_RECIPE)), "recipe"),
        (dict(balances=("B", "B")), "balance"),
        (dict(pipettes=("P", "P")), "pipette"),
    ],
)
def test_rules_list_each_name_once(changes, what):
    with pytest.raises(ValidationError, match=f"a {what} is listed twice"):
        PrepRules(**{**RULES.model_dump(), **changes})
