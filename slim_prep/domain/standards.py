"""The standards book (P-14, P-15, P-16): stocks, and the standards the lab makes from them.

A standard is identified by name + prep date, as in today's spreadsheet, and records its source: a chain
from every spike back to the purchased stock. Its concentration and expiry are calculated from the
recipe, never typed.
"""

from datetime import date

from pydantic import Field

from slim_prep.domain.base import Frozen
from slim_prep.domain.problems import PrepRefused, Problem
from slim_prep.domain.rules import Name, PrepRules
from slim_prep.domain.units import G_PER_ML, MG_PER_UL, Concentration

Element = Field(min_length=1, max_length=20)


class Stock(Frozen):
    """A purchased stock solution. Typed in here until slim-quality registers them (P-14)."""

    name: str = Name
    lot: str = Field(min_length=1, max_length=50)
    concentration: Concentration
    elements: tuple[str, ...] = Field(min_length=1)  # every element at `concentration`
    expires: date  # usable through this day

    def __str__(self) -> str:
        return f"{self.name} lot {self.lot}"


class StandardRef(Frozen):
    name: str = Name
    prepared: date

    def __str__(self) -> str:
        return f"{self.name} ({self.prepared.isoformat()})"


class Standard(Frozen):
    """A standard the lab made: a recipe step, its actual source, who, when and with what."""

    recipe: str = Name
    name: str = Name  # the recipe step's name
    prepared: date
    source: StandardRef | Stock
    analyst: str = Field(min_length=1, max_length=100)
    pipettes: tuple[str, ...] = ()
    concentration: Concentration
    elements: tuple[str, ...] = Field(min_length=1)
    expires: date

    @property
    def ref(self) -> StandardRef:
        return StandardRef(name=self.name, prepared=self.prepared)


def make_standard(
    rules: PrepRules,
    recipe: str,
    step: str,
    source: Stock | Standard,
    prepared: date,
    analyst: str,
    pipettes: tuple[str, ...] = (),
) -> Standard:
    """A new standard, or PrepRefused with every reason it can't be made."""
    problems: list[Problem] = []
    found = rules.recipe(recipe)
    if found is None:
        raise PrepRefused([Problem(where="recipe", message=f"no recipe {recipe!r} in {rules.name}")])
    made = found.step(step)
    if made is None:
        raise PrepRefused([Problem(where="step", message=f"recipe {recipe!r} has no step {step!r}")])
    expected = found.source_of(step)
    if isinstance(source, Stock):
        if source.name != expected:
            problems.append(Problem(where="source", message=f"{step} is made from {expected}, not {source}"))
        from_ = source
    else:
        if source.recipe != recipe or source.name != expected:
            problems.append(
                Problem(where="source", message=f"{step} is made from {expected}, not {source.ref}")
            )
        if source.prepared > prepared:
            problems.append(Problem(where="source", message=f"{source.ref} was made after {prepared}"))
        from_ = source.ref
    if source.expires < prepared:
        problems.append(Problem(where="source", message=f"expired on {source.expires}"))
    for pipette in pipettes:
        if pipette not in rules.pipettes:
            problems.append(Problem(where="pipettes", message=f"{pipette!r} is not on the lab's list"))
    if problems:
        raise PrepRefused(problems)
    expires = made.shelf_life.after(prepared)
    if rules.cap_expiry_at_source:
        expires = min(expires, source.expires)
    return Standard(
        recipe=recipe,
        name=step,
        prepared=prepared,
        source=from_,
        analyst=analyst,
        pipettes=pipettes,
        concentration=source.concentration.times(made.volume_ul * MG_PER_UL / (made.final_ml * G_PER_ML)),
        elements=source.elements,
        expires=expires,
    )
