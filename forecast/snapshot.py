from collections.abc import Mapping
from dataclasses import dataclass

from forecast.import_rows import ForecastRow, validate_forecast_rows
from forecast.probability import fraction_payload
from study.identity import validate_identifier
from study.roster import Roster, roster_from_payload


@dataclass(frozen=True)
class ForecastSnapshot:
    roster: Roster
    revision_id: str
    rows: tuple[ForecastRow, ...]


def build_forecast_snapshot(roster: Roster, revision_id: str, rows: object) -> ForecastSnapshot:
    revision = validate_identifier(revision_id, 'revision_id')
    return ForecastSnapshot(roster, revision, validate_forecast_rows(roster, rows))


def forecast_piece_payload(snapshot: ForecastSnapshot) -> dict:
    return {
        'kind': 'forecast',
        **snapshot.roster.as_payload(),
        'source_id': snapshot.revision_id,
        'rows': [
            {'specimen_id': row.specimen_id, 'probability': fraction_payload(row.probability),
             'source': row.source}
            for row in snapshot.rows
        ],
    }


def forecast_snapshot_from_payload(payload: Mapping) -> ForecastSnapshot:
    if payload.get('kind') != 'forecast':
        raise ValueError('expected a forecast piece')
    roster = roster_from_payload(payload)
    return build_forecast_snapshot(roster, payload.get('source_id'), payload.get('rows'))
