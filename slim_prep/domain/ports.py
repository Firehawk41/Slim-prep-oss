"""What slim-prep asks the host about a sample (P-23; review B1). The TR is the host's: slim-prep never
reads its tables. Every batch is checked against it when it is recorded, corrected and sent."""

from collections.abc import Iterable
from enum import IntEnum
from typing import Protocol

from pydantic import Field

from slim_prep.domain.base import Frozen
from slim_prep.domain.problems import Problem


class SampleState(IntEnum):
    NOT_RECEIVED = 1  # the TR is submitted: the samples aren't in the lab yet
    OPEN = 2  # received, in work or reported: it may be prepped
    CANCELLED = 3
    CLOSED = 4  # invoiced: the request is finished


class SampleInfo(Frozen):
    sample: str  # the lab sample ID, e.g. TR00042-01
    state: SampleState
    analyses: frozenset[str] = frozenset()  # the analysis codes ordered for it
    chemical: str = Field(default="", max_length=200)  # as the customer named it
    chemical_id: int | None = None  # the matched SLIM chemical: the run list's matrix (P-21)

    @property
    def matrix(self) -> str:
        """What the run list groups by: the matched chemical, else the customer's name for it."""
        return f"#{self.chemical_id}" if self.chemical_id is not None else self.chemical.strip().upper()


class SampleLookup(Protocol):
    def sample(self, sample_id: str) -> SampleInfo | None: ...

    def open_samples(self, analysis: str) -> tuple[SampleInfo, ...]:
        """The open samples that ordered this analysis: what the new-batch picker offers."""
        ...


def sample_problems(samples: Iterable[str], analysis: str, lookup: SampleLookup) -> list[Problem]:
    """Each sample must exist, be in the lab (received, not cancelled) and have ordered the analysis."""
    problems = []
    for sample_id in samples:
        info = lookup.sample(sample_id)
        if info is None:
            message = "no such sample"
        elif info.state == SampleState.NOT_RECEIVED:
            message = "its request isn't checked in yet"
        elif info.state == SampleState.CANCELLED:
            message = "its request was cancelled"
        elif info.state == SampleState.CLOSED:
            message = "its request is closed (invoiced)"
        elif analysis not in info.analyses:
            message = f"{analysis} wasn't ordered for it"
        else:
            continue
        problems.append(Problem(where=sample_id, message=message))
    return problems
