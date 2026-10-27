"""The prep policy (P-02, P-07, P-15, P-16, P-17): what quality sets and the lab works under.

One versioned `PrepRules`: prep method layouts, the lab's standard recipes with their shelf lives, and the
equipment lists. Published like a slim-data ruleset; every standard and batch records the version it was
made under. Pure data: no `if method == ...` anywhere in the code.
"""

import calendar
from datetime import date, timedelta
from typing import Literal, Self

from pydantic import Field, model_validator

from slim_prep.domain.base import Dec, Frozen

Name = Field(min_length=1, max_length=100)


class ShelfLife(Frozen):
    """How long a standard keeps (P-16): e.g. 3 months, 1 week."""

    amount: int = Field(ge=1)
    unit: Literal["days", "weeks", "months"]

    def after(self, start: date) -> date:
        if self.unit == "days":
            return start + timedelta(days=self.amount)
        if self.unit == "weeks":
            return start + timedelta(weeks=self.amount)
        months = start.month - 1 + self.amount
        year, month = start.year + months // 12, months % 12 + 1
        return date(
            year, month, min(start.day, calendar.monthrange(year, month)[1])
        )  # 31 Jan + 1 month: 28/29 Feb

    def __str__(self) -> str:
        return f"{self.amount} {self.unit}"


class RecipeStep(Frozen):
    """One standard in a chain (P-15): `volume_ul` of the source made up to `final_ml`."""

    name: str = Name  # what the standard is called, e.g. "20 ppm"
    volume_ul: Dec = Field(gt=0)
    final_ml: Dec = Field(gt=0)
    shelf_life: ShelfLife

    @model_validator(mode="after")
    def _a_dilution(self) -> Self:
        if self.volume_ul >= self.final_ml * 1000:
            raise ValueError(f"{self.name}: the volume taken must be less than the final volume")
        return self


class Recipe(Frozen):
    """A named chain from a stock, e.g. 1000 ppm stock → 20 ppm → 50 ppb. Each step's source is the step
    before it; the first step's is the stock."""

    name: str = Name
    stock: str = Name  # the stock material's name, as on its bottle
    steps: tuple[RecipeStep, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique(self) -> Self:
        names = [s.name for s in self.steps]
        if len(set(names)) != len(names) or self.stock in names:
            raise ValueError(f"recipe {self.name}: every step needs its own name, not the stock's")
        return self

    def step(self, name: str) -> RecipeStep | None:
        return next((s for s in self.steps if s.name == name), None)

    def source_of(self, name: str) -> str:
        """The name of what a step is made from: the step before it, or the stock."""
        index = [s.name for s in self.steps].index(name)
        return self.stock if index == 0 else self.steps[index - 1].name


class PrepMethod(Frozen):
    """A prep book's layout (P-02, P-04): which weighings and steps it records.

    Evaporation: pre-weighed cup and cap, a Pour Out step, Final = cup + solution. Dilute-and-shoot: the
    vial is tared on the balance, so Gross reads the sample alone and Final the solution alone.
    """

    name: str = Name
    tared_vessel: bool = False
    weighs_cap: bool = False
    pour_out_step: bool = False
    sample_cups: int = Field(default=2, ge=1)
    spike_cups: int = Field(default=1, ge=0)

    @model_validator(mode="after")
    def _cap_needs_a_tare(self) -> Self:
        if self.tared_vessel and self.weighs_cap:
            raise ValueError(f"{self.name}: a tared vessel has no separate cap weight")
        return self


class PrepRules(Frozen):
    name: str = Name
    methods: tuple[PrepMethod, ...] = Field(min_length=1)
    recipes: tuple[Recipe, ...] = ()
    balances: tuple[str, ...] = Field(min_length=1)
    pipettes: tuple[str, ...] = ()
    cap_expiry_at_source: bool = True  # P-16: the lab may let a standard outlive its source

    @model_validator(mode="after")
    def _unique(self) -> Self:
        for what, names in (
            ("method", [m.name for m in self.methods]),
            ("recipe", [r.name for r in self.recipes]),
            ("balance", list(self.balances)),
            ("pipette", list(self.pipettes)),
        ):
            if len(set(names)) != len(names):
                raise ValueError(f"a {what} is listed twice")
        return self

    def method(self, name: str) -> PrepMethod | None:
        return next((m for m in self.methods if m.name == name), None)

    def recipe(self, name: str) -> Recipe | None:
        return next((r for r in self.recipes if r.name == name), None)
