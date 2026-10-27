"""Concentrations and their units (P-05, P-06, P-15).

ppm, ppb and ppt are mass fractions (µg/g, ng/g, pg/g). Volumes pipetted count as mass at 1 g/mL
(P-06): 1 µL is 1 mg, 1 mL is 1 g.
"""

from decimal import Decimal
from typing import Literal

from pydantic import Field

from slim_prep.domain.base import Dec, Frozen

Unit = Literal["ppm", "ppb", "ppt"]
UNITS: tuple[str, ...] = ("ppm", "ppb", "ppt")
_IN_PPT: dict[str, Decimal] = {"ppm": Decimal(10) ** 6, "ppb": Decimal(10) ** 3, "ppt": Decimal(1)}
_LARGEST_FIRST: tuple[Unit, ...] = ("ppm", "ppb", "ppt")

MG_PER_UL = Decimal("0.001")  # grams per µL at 1 g/mL
G_PER_ML = Decimal(1)


def plain(value: Decimal) -> Decimal:
    """Without trailing zeros, and never in exponent form: 20, not 2E+1."""
    value = value.normalize()
    return value.quantize(Decimal(1)) if value.as_tuple().exponent > 0 else value


class Concentration(Frozen):
    value: Dec = Field(gt=0)
    unit: Unit

    def to(self, unit: Unit) -> "Concentration":
        return Concentration(value=self.value * _IN_PPT[self.unit] / _IN_PPT[unit], unit=unit)

    def times(self, factor: Decimal) -> "Concentration":
        """Scaled by `factor`, in the largest unit that keeps the value at 1 or more (20 ppm, 50 ppb)."""
        ppt = self.value * _IN_PPT[self.unit] * factor
        unit = next((u for u in _LARGEST_FIRST if ppt >= _IN_PPT[u]), "ppt")
        return Concentration(value=plain(ppt / _IN_PPT[unit]), unit=unit)

    def __str__(self) -> str:
        return f"{self.value} {self.unit}"
