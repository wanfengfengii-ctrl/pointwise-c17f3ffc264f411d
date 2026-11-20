from dataclasses import dataclass
from fractions import Fraction

from evaluation.piece_content import FixedPiece


@dataclass(frozen=True)
class AlignedSpecimen:
    specimen_id: str
    probability: Fraction
    outcome: int
    forecast_source: str
    result_source: str


def align_accepted_pair(forecast: FixedPiece, results: FixedPiece) -> tuple[AlignedSpecimen, ...]:
    if forecast.kind != 'forecast' or results.kind != 'results':
        raise ValueError('select a forecast piece followed by a results piece')
    if forecast.roster != results.roster:
        raise ValueError('selected pieces have different batches or ordered rosters')
    specimens = forecast.roster.specimens
    forecast_rows = {row.specimen_id: row for row in forecast.rows}
    result_rows = {row.specimen_id: row for row in results.rows}
    expected = set(specimens)
    if forecast_rows.keys() != expected or result_rows.keys() != expected:
        raise ValueError('selected piece does not cover the roster')
    if len(forecast.rows) != len(specimens) or len(results.rows) != len(specimens):
        raise ValueError('selected piece has repeated rows')
    return tuple(
        AlignedSpecimen(name, forecast_rows[name].probability, result_rows[name].outcome,
                        forecast_rows[name].source, result_rows[name].source)
        for name in specimens
    )
