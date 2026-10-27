"""The demo's prep rules and stock (invented, never a real lab's: slim-data D-05). The host seeds them."""

from datetime import date
from decimal import Decimal

from slim_prep.domain.rules import PrepMethod, PrepRules, Recipe, RecipeStep, RunListRule, ShelfLife
from slim_prep.domain.standards import Stock
from slim_prep.domain.units import Concentration

D = Decimal

DEMO_RULES = PrepRules(
    name="demo prep rules",
    methods=(
        PrepMethod(name="evaporation", weighs_cap=True, pour_out_step=True, sample_cups=2, spike_cups=1),
        PrepMethod(
            name="dilute and shoot", tared_vessel=True, sample_cups=2, spike_cups=1, spikes_at_block_end=False
        ),
    ),
    recipes=(
        Recipe(
            name="multi-element spike",
            stock="Multi-element stock A",
            steps=(
                RecipeStep(
                    name="20 ppm",
                    volume_ul=D(1000),
                    final_ml=D(50),
                    shelf_life=ShelfLife(amount=3, unit="months"),
                ),
                RecipeStep(
                    name="50 ppb",
                    volume_ul=D(125),
                    final_ml=D(50),
                    shelf_life=ShelfLife(amount=1, unit="weeks"),
                ),
            ),
        ),
    ),
    balances=("BAL-1", "BAL-2"),
    pipettes=("P100-1", "P100-2", "P1000-1"),
    run_list=RunListRule(),
)


def demo_stock(expires: date) -> Stock:
    return Stock(
        name="Multi-element stock A",
        lot="DEMO-0001",
        concentration=Concentration(value=D(1000), unit="ppm"),
        elements=("Cu", "Fe", "Ni", "Zn", "Pb", "Cr", "Mn", "Co", "Al", "Na"),
        expires=expires,
    )
