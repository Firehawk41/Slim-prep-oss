"""Builders for tests: the demo prep rules (invented, D-05), stocks, standards and batches."""

from datetime import UTC, date, datetime
from decimal import Decimal

from slim_prep.domain.actor import Actor, IdentitySource, Role
from slim_prep.domain.ports import SampleInfo, SampleState
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


AT = datetime(2026, 10, 27, 9, 30, tzinfo=UTC)  # when the demo batch was prepped
NOW = datetime(2026, 10, 27, 12, 0, tzinfo=UTC)  # when it is recorded


def batch(**changes):
    at = AT
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


QUALITY = Actor(id="qm-1", display="Quinn (quality)", roles=frozenset({Role.QUALITY}))
ANALYST = Actor(
    id="ana-1", display="Ana (analyst)", roles=frozenset({Role.ANALYST}),
    identity_source=IdentitySource.AUTHENTICATED,
)  # fmt: skip


class FakeSamples:
    """The host's SampleLookup (P-23): every sample is open, ordered 10 elements and is IPA, unless
    `found` says otherwise (None: no such sample)."""

    def __init__(self, **found: SampleInfo | None) -> None:
        self.found = {k.replace("_", "-"): v for k, v in found.items()}

    def sample(self, sample_id: str) -> SampleInfo | None:
        if sample_id in self.found:
            return self.found[sample_id]
        return info(sample_id)

    def open_samples(self, analysis: str) -> tuple[SampleInfo, ...]:
        return tuple(
            i for i in self.found.values() if i and i.state == SampleState.OPEN and analysis in i.analyses
        )


def info(
    sample_id: str, state=SampleState.OPEN, analyses=("10_elements_icpms",), chemical="IPA", chemical_id=None
):
    return SampleInfo(
        sample=sample_id,
        state=state,
        analyses=frozenset(analyses),
        chemical=chemical,
        chemical_id=chemical_id,
    )


SAMPLES = FakeSamples()
