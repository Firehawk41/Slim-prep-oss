"""The prep book (P-03…P-09): a batch of samples, each with its cups, weighings and spikes.

What the analyst enters is stored as entered; everything that follows from it (net, solution, dilution,
spike level) is calculated by `figures`, never typed (P-05, P-06). `figures` also checks the batch
against the prep method and the lab's lists, and refuses with every problem at once.
"""

import re
from datetime import date
from decimal import Decimal
from enum import IntEnum
from typing import Self

from pydantic import AwareDatetime, Field, field_validator, model_validator

from slim_prep.domain.base import Dec, Frozen
from slim_prep.domain.problems import PrepRefused, Problem
from slim_prep.domain.rules import Name, PrepMethod, PrepRules
from slim_prep.domain.standards import Standard, StandardRef
from slim_prep.domain.units import MG_PER_UL, Concentration

_SAMPLE_RE = re.compile(r"^TR\d{5,}-\d+$")
# P-26: a batch code is safe anywhere it goes (a CSV cell, a file name, a URL): letters, digits, dot,
# hyphen and underscore, starting with a letter or digit.
BATCH_CODE = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,49}$"
Grams = Field(default=None, ge=0)
Note = Field(default=None, max_length=1000)


class CupKind(IntEnum):
    SAMPLE = 1
    SPIKE = 2  # its own spiked cup (P-06): slim-data's SPIKE reading


class Weighing(Frozen):
    """As entered, in grams (P-05). Which are needed depends on the prep method."""

    tare: Dec | None = Grams
    cap: Dec | None = Grams
    gross: Dec = Field(gt=0)
    final: Dec = Field(gt=0)


class SpikeLine(Frozen):
    """A spike added to a cup (P-06), with the standard's concentration and expiry snapshotted."""

    standard: StandardRef
    concentration: Concentration
    elements: tuple[str, ...] = Field(min_length=1)
    expires: date
    volume_ul: Dec = Field(gt=0)
    pipette: str = Name

    @classmethod
    def of(cls, standard: Standard, volume_ul: Decimal, pipette: str) -> Self:
        return cls(
            standard=standard.ref,
            concentration=standard.concentration,
            elements=standard.elements,
            expires=standard.expires,
            volume_ul=volume_ul,
            pipette=pipette,
        )


class Cup(Frozen):
    number: int = Field(ge=1)
    kind: CupKind = CupKind.SAMPLE
    weighing: Weighing
    spikes: tuple[SpikeLine, ...] = ()
    pipettes: tuple[str, ...] = ()  # any other pipettes used on this cup
    balance: str | None = None  # P-07: overrides the batch's balance for this cup
    note: str | None = Note

    @model_validator(mode="after")
    def _spikes_fit_the_kind(self) -> Self:
        if self.kind == CupKind.SAMPLE and self.spikes:
            raise ValueError(f"cup {self.number}: a sample cup has no spike; the spike gets its own cup")
        if self.kind == CupKind.SPIKE and not self.spikes:
            raise ValueError(f"cup {self.number}: a spike cup needs at least one spike")
        elements = [e for line in self.spikes for e in line.elements]
        if len(set(elements)) != len(elements):
            raise ValueError(f"cup {self.number}: an element is spiked twice")
        return self


class PrepSample(Frozen):
    sample: str  # the lab sample ID, e.g. TR00042-01
    cups: tuple[Cup, ...] = Field(min_length=1)
    note: str | None = Note

    @field_validator("sample")
    @classmethod
    def _lab_sample_id(cls, value: str) -> str:
        if not _SAMPLE_RE.match(value):
            raise ValueError(f"not a lab sample ID (expected e.g. TR00042-01): {value!r}")
        return value

    @model_validator(mode="after")
    def _numbered_once(self) -> Self:
        numbers = [c.number for c in self.cups]
        if len(set(numbers)) != len(numbers):
            raise ValueError(f"{self.sample}: a cup number is used twice")
        return self


class StepRecord(Frozen):
    """Who did a step and when (P-04): the analyst's initials as the book shows them, and the host's id
    for the person (P-27; None only on records made before it). The time is entered, with its zone (P-25)."""

    analyst: str = Field(min_length=1, max_length=100)
    analyst_id: str | None = Field(default=None, max_length=100)
    at: AwareDatetime


class PrepBatch(Frozen):
    code: str = Field(pattern=BATCH_CODE)
    method: str = Name
    analysis: str = Field(min_length=1, max_length=50)  # the analysis code, e.g. 10_elements_icpms
    balance: str = Name  # P-07: "all weights from this balance unless noted"
    pour_out: StepRecord | None = None
    prep: StepRecord
    samples: tuple[PrepSample, ...] = Field(min_length=1)
    note: str | None = Note

    @model_validator(mode="after")
    def _each_sample_once(self) -> Self:
        names = [s.sample for s in self.samples]
        if len(set(names)) != len(names):
            raise ValueError("a sample appears twice in the batch")
        if self.pour_out is not None and self.pour_out.at > self.prep.at:
            raise ValueError("the pour-out comes before the prep, not after it")
        return self


class CupFigures(Frozen):
    """What follows from a cup's entries (P-05, P-06): unrounded."""

    sample: str
    cup: int
    kind: CupKind
    net: Dec
    solution: Dec
    dilution: Dec  # solution ÷ net; below 1 when the prep concentrates (evaporation)
    added: tuple[tuple[str, Concentration], ...] = ()  # per element, in the sample's terms


def figures(batch: PrepBatch, rules: PrepRules) -> tuple[CupFigures, ...]:
    """Every cup's figures, or PrepRefused with every problem in the batch."""
    problems: list[Problem] = []
    method = rules.method(batch.method)
    if method is None:
        raise PrepRefused(
            [Problem(where="method", message=f"no prep method {batch.method!r} in {rules.name}")]
        )
    if batch.balance not in rules.balances:
        problems.append(Problem(where="balance", message=f"{batch.balance!r} is not on the lab's list"))
    if method.pour_out_step and batch.pour_out is None:
        problems.append(Problem(where="pour_out", message=f"{method.name} records who poured out"))
    if not method.pour_out_step and batch.pour_out is not None:
        problems.append(Problem(where="pour_out", message=f"{method.name} has no pour-out step"))
    prepped_on = batch.prep.at.date()
    out = []
    for sample in batch.samples:
        _check_cup_counts(sample, method, problems)
        for cup in sample.cups:
            where = f"{sample.sample} cup {cup.number}"
            _check_cup(cup, rules, prepped_on, where, problems)
            result = _cup_figures(cup.weighing, method, where, problems)
            if result is None:
                continue
            net, solution = result
            added = tuple(
                (element, line.concentration.times(line.volume_ul * MG_PER_UL / net))
                for line in cup.spikes
                for element in line.elements
            )
            out.append(
                CupFigures(
                    sample=sample.sample,
                    cup=cup.number,
                    kind=cup.kind,
                    net=net,
                    solution=solution,
                    dilution=solution / net,
                    added=added,
                )
            )
    if problems:
        raise PrepRefused(problems)
    return tuple(out)


def _check_cup_counts(sample: PrepSample, method: PrepMethod, problems: list[Problem]) -> None:
    for kind, wanted in ((CupKind.SAMPLE, method.sample_cups), (CupKind.SPIKE, method.spike_cups)):
        found = sum(1 for c in sample.cups if c.kind == kind)
        if found != wanted:
            problems.append(
                Problem(
                    where=sample.sample,
                    message=f"{method.name} has {wanted} {kind.name.lower()} cup(s), not {found}",
                )
            )


def _check_cup(cup: Cup, rules: PrepRules, prepped_on: date, where: str, problems: list[Problem]) -> None:
    if cup.balance is not None and cup.balance not in rules.balances:
        problems.append(Problem(where=where, message=f"balance {cup.balance!r} is not on the lab's list"))
    for pipette in (*cup.pipettes, *(line.pipette for line in cup.spikes)):
        if pipette not in rules.pipettes:
            problems.append(Problem(where=where, message=f"pipette {pipette!r} is not on the lab's list"))
    for line in cup.spikes:
        if line.expires < prepped_on:
            problems.append(Problem(where=where, message=f"{line.standard} expired on {line.expires}"))
        if line.standard.prepared > prepped_on:
            problems.append(Problem(where=where, message=f"{line.standard} was made after {prepped_on}"))


def _cup_figures(
    w: Weighing, method: PrepMethod, where: str, problems: list[Problem]
) -> tuple[Decimal, Decimal] | None:
    """(net, solution), or None after adding why they can't be worked out."""
    before = len(problems)
    if method.tared_vessel:
        for name, value in (("tare", w.tare), ("cap", w.cap)):
            if value is not None:
                problems.append(Problem(where=where, message=f"{method.name} tares the vessel: no {name}"))
        net, solution = w.gross, w.final
    else:
        if w.tare is None:
            problems.append(Problem(where=where, message=f"{method.name} needs the tare"))
        if method.weighs_cap and w.cap is None:
            problems.append(Problem(where=where, message=f"{method.name} needs the cap weight"))
        if not method.weighs_cap and w.cap is not None:
            problems.append(Problem(where=where, message=f"{method.name} doesn't weigh a cap"))
        if len(problems) > before:
            return None
        net = w.gross - w.tare - (w.cap or 0)
        solution = w.final - w.tare
    if net <= 0:
        problems.append(Problem(where=where, message=f"net weight {net} g: gross must exceed tare and cap"))
    if solution <= 0:
        problems.append(Problem(where=where, message=f"solution {solution} g: final must exceed the tare"))
    if len(problems) > before:
        return None
    return net, solution
