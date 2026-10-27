"""Builders for tests: the demo prep rules (invented, D-05), stocks, standards and batches."""

from datetime import date, datetime
from decimal import Decimal

from slim_prep.domain.prep import Cup, CupKind, PrepBatch, PrepSample, SpikeLine, StepRecord, Weighing
from slim_prep.domain.rules import PrepMethod, PrepRules, Recipe, RecipeStep, ShelfLife
from slim_prep.domain.standards import Stock, make_standard
from slim_prep.domain.units import Concentration

D = Decimal
TODAY = date(2026, 10, 27)
EVAPORATION = PrepMethod(name="evaporation", weighs_cap=True, pour_out_step=True)
DILUTE_AND_SHOOT = PrepMethod(name="dilute and shoot", tared_vessel=True, spike_cups=0)
SPIKE_RECIPE = Recipe(
    name="multi-element spike",
    stock="Multi-element stock A",
    steps=(
        RecipeStep(
            name="20 ppm", volume_ul=D(1000), final_ml=D(50), shelf_life=ShelfLife(amount=3, unit="months")
        ),
        RecipeStep(
            name="50 ppb", volume_ul=D(125), final_ml=D(50), shelf_life=ShelfLife(amount=1, unit="weeks")
        ),
    ),
)
RULES = PrepRules(
    name="demo prep rules",
    methods=(EVAPORATION, DILUTE_AND_SHOOT),
    recipes=(SPIKE_RECIPE,),
    balances=("BAL-1", "BAL-2"),
    pipettes=("P100-1", "P1000-1"),
)


def conc(value, unit="ppm"):
    return Concentration(value=D(value), unit=unit)


def stock(**changes):
    fields = dict(
        name="Multi-element stock A",
        lot="L-0042",
        concentration=conc("1000"),
        elements=("Cu", "Fe", "Ni"),
        expires=date(2027, 6, 30),
    )
    return Stock(**{**fields, **changes})


def chain(prepared=TODAY, rules=RULES):
    """The demo chain: stock → 20 ppm → 50 ppb, all made on `prepared`."""
    twenty = make_standard(rules, SPIKE_RECIPE.name, "20 ppm", stock(), prepared, "ana", ("P1000-1",))
    fifty = make_standard(rules, SPIKE_RECIPE.name, "50 ppb", twenty, prepared, "ana", ("P100-1",))
    return twenty, fifty


def evaporation_cup(number, gross="12.5000", final="2.6000", kind=CupKind.SAMPLE, spikes=(), **changes):
    """Tare 2.0, cap 0.5: net 10.0 g; solution 0.6 g: dilution 0.06."""
    weighing = Weighing(tare=D("2.0000"), cap=D("0.5000"), gross=D(gross), final=D(final))
    return Cup(number=number, kind=kind, weighing=weighing, spikes=spikes, **changes)


def spike_line(volume="10", pipette="P100-1"):
    return SpikeLine.of(chain()[1], D(volume), pipette)


def evaporation_sample(sample="TR00042-01", **changes):
    cups = (
        evaporation_cup(1),
        evaporation_cup(2),
        evaporation_cup(3, kind=CupKind.SPIKE, spikes=(spike_line(),)),
    )
    return PrepSample(sample=sample, cups=changes.pop("cups", cups), **changes)


def batch(**changes):
    at = datetime(2026, 10, 27, 9, 30)
    fields = dict(
        code="PB-0001",
        method="evaporation",
        analysis="10_elements_icpms",
        balance="BAL-1",
        pour_out=StepRecord(analyst="pat", at=at),
        prep=StepRecord(analyst="ana", at=at),
        samples=(evaporation_sample(),),
    )
    return PrepBatch(**{**fields, **changes})
