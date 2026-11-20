from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction

from forecast.probability import parse_probability
from study.identity import validate_identifier
from study.roster import Roster


@dataclass(frozen=True)
class ForecastRow:
    specimen_id: str
    probability: Fraction
    source: str


def validate_forecast_rows(roster: Roster, rows: object) -> tuple[ForecastRow, ...]:
    if not isinstance(rows, (list, tuple)):
        raise ValueError('forecast rows must be a list or tuple')
    expected = set(roster.specimens)
    by_specimen: dict[str, ForecastRow] = {}
    for row in rows:
        if not isinstance(row, Mapping) or set(row) != {'specimen_id', 'probability', 'source'}:
            raise ValueError('forecast row requires specimen_id, probability and source')
        specimen = validate_identifier(row['specimen_id'], 'specimen_id')
        if specimen not in expected or specimen in by_specimen:
            raise ValueError(f'unknown or repeated forecast specimen {specimen!r}')
        source = validate_identifier(row['source'], 'forecast source')
        by_specimen[specimen] = ForecastRow(specimen, parse_probability(row['probability']), source)
    missing = [name for name in roster.specimens if name not in by_specimen]
    if missing:
        raise ValueError(f'missing forecast specimens: {missing!r}')
    return tuple(by_specimen[name] for name in roster.specimens)
