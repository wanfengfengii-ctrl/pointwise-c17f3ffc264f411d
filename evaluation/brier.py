from dataclasses import dataclass
from fractions import Fraction

from evaluation.alignment import AlignedSpecimen


@dataclass(frozen=True)
class BrierRow:
    specimen: AlignedSpecimen
    squared_error: Fraction


@dataclass(frozen=True)
class BrierScore:
    rows: tuple[BrierRow, ...]
    mean: Fraction


def score_brier(specimens: tuple[AlignedSpecimen, ...]) -> BrierScore:
    if not specimens:
        raise ValueError('Brier review requires a nonempty batch')
    rows = tuple(BrierRow(row, (row.probability - row.outcome) ** 2) for row in specimens)
    total = sum((row.squared_error for row in rows), Fraction(0))
    return BrierScore(rows, total / len(rows))
