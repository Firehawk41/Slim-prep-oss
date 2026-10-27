"""The planned run list (P-13): what goes on the instrument, in order, from the prep batches.

The plan is slim-prep's; what was actually run is the instrument file's, and slim-data judges check
standards against that (the file is the evidence, the plan only feeds the instrument). The lab's rule
(`RunListRule`, `PrepMethod.spikes_at_block_end`) decides where check standards and spikes go. A
matrix is chemical + prep method; samples run in the order given, and a new matrix starts wherever
the next sample's differs.
"""

import csv
import io
from collections.abc import Mapping, Sequence
from enum import IntEnum

from pydantic import Field

from slim_prep.domain.base import Dec, Frozen
from slim_prep.domain.prep import CupFigures, CupKind, PrepBatch
from slim_prep.domain.problems import PrepRefused, Problem
from slim_prep.domain.rules import PrepRules
from slim_prep.domain.units import plain


class EntryKind(IntEnum):
    CUP = 1
    SPIKE = 2
    CHECK = 3
    OTHER = 4  # an opening or closing item: calibration blank, rinse…


class RunEntry(Frozen):
    position: int = Field(ge=1)
    label: str
    kind: EntryKind
    batch: str | None = None
    sample: str | None = None
    cup: int | None = None
    dilution: Dec | None = None


def plan_run(
    batches: Sequence[tuple[PrepBatch, tuple[CupFigures, ...]]],
    chemicals: Mapping[str, str],
    rules: PrepRules,
) -> tuple[RunEntry, ...]:
    """The run list for these batches (each with its figures), in the order given. `chemicals` gives
    each sample's chemical (from the TR)."""
    missing = [s.sample for b, _ in batches for s in b.samples if s.sample not in chemicals]
    if missing:
        raise PrepRefused([Problem(where=s, message="no chemical for this sample") for s in missing])
    rule = rules.run_list

    def fixed(label: str) -> tuple:  # an opening or closing item: a check standard if it's named as one
        return (
            label,
            EntryKind.CHECK if label == rule.check_label else EntryKind.OTHER,
            None,
            None,
            None,
            None,
        )

    rows: list[tuple] = [fixed(label) for label in rule.opening]
    check = fixed(rule.check_label)
    matrix, count, held = None, 0, []
    for batch, cups in batches:
        method = rules.method(batch.method)
        if method is None:
            raise PrepRefused([Problem(where=batch.code, message=f"no prep method {batch.method!r}")])
        for sample in batch.samples:
            this = (chemicals[sample.sample].upper(), method.name)
            if matrix is not None and this != matrix:
                rows += held
                held = []
                if rule.check_between_matrices:
                    rows.append(check)
                count = 0
            elif rule.check_every is not None and count == rule.check_every:
                rows.append(check)
                count = 0
            matrix = this
            mine = sorted((c for c in cups if c.sample == sample.sample), key=lambda c: c.cup)
            sample_cups = [c for c in mine if c.kind == CupKind.SAMPLE]
            spike_cups = [c for c in mine if c.kind == CupKind.SPIKE]
            for n, cup in enumerate(sample_cups, start=1):
                label = sample.sample if len(sample_cups) == 1 else f"{sample.sample} {n}"
                rows.append((label, EntryKind.CUP, batch.code, sample.sample, cup.cup, cup.dilution))
            spikes = [
                (
                    f"{sample.sample} spike" + ("" if len(spike_cups) == 1 else f" {n}"),
                    EntryKind.SPIKE, batch.code, sample.sample, cup.cup, cup.dilution,
                )
                for n, cup in enumerate(spike_cups, start=1)
            ]  # fmt: skip
            if method.spikes_at_block_end:
                held += spikes
            else:
                rows += spikes
            count += 1
    rows += held
    rows += [fixed(label) for label in rule.closing]
    return tuple(
        RunEntry(position=i, label=lab, kind=kind, batch=b, sample=s, cup=c, dilution=d)
        for i, (lab, kind, b, s, c, d) in enumerate(rows, start=1)
    )


CSV_COLUMNS = ("position", "label", "type", "batch", "sample_id", "cup", "dilution_factor")


def run_list_csv(entries: Sequence[RunEntry]) -> str:
    """The run list as a plain CSV sample list for the instrument (P-13)."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for e in entries:
        dilution = "" if e.dilution is None else str(plain(e.dilution))
        writer.writerow(
            (e.position, e.label, e.kind.name.lower(), e.batch or "", e.sample or "", e.cup or "", dilution)
        )
    return out.getvalue()
