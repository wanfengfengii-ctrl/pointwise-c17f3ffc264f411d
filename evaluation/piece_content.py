from collections.abc import Mapping
from dataclasses import dataclass
import json

from bench.snapshot import BenchSnapshot, RevealedResult, bench_piece_payload, bench_snapshot_from_payload
from forecast.import_rows import ForecastRow
from forecast.snapshot import ForecastSnapshot, forecast_piece_payload, forecast_snapshot_from_payload
from study.roster import Roster


@dataclass(frozen=True)
class FixedPiece:
    kind: str
    roster: Roster
    source_id: str
    rows: tuple[ForecastRow, ...] | tuple[RevealedResult, ...]


def normalize_piece(payload: object) -> FixedPiece:
    fields = {'kind', 'batch_id', 'roster_id', 'specimens', 'source_id', 'rows'}
    if not isinstance(payload, Mapping) or set(payload) != fields:
        raise ValueError('invalid fixed-piece envelope')
    kind = payload['kind']
    if kind == 'forecast':
        forecast = forecast_snapshot_from_payload(payload)
        return FixedPiece(kind, forecast.roster, forecast.revision_id, forecast.rows)
    if kind == 'results':
        results = bench_snapshot_from_payload(payload)
        return FixedPiece(kind, results.roster, results.closeout_id, results.rows)
    raise ValueError('unrecognized fixed-piece type')


def encode_piece(piece: FixedPiece) -> str:
    if piece.kind == 'forecast':
        payload = forecast_piece_payload(ForecastSnapshot(piece.roster, piece.source_id, piece.rows))
    elif piece.kind == 'results':
        payload = bench_piece_payload(BenchSnapshot(piece.roster, piece.source_id, piece.rows))
    else:
        raise ValueError('unrecognized fixed-piece type')
    return json.dumps(payload, sort_keys=True, separators=(',', ':'))


def decode_piece(text: str) -> FixedPiece:
    if not isinstance(text, str):
        raise ValueError('fixed-piece encoding must be JSON text')
    return normalize_piece(json.loads(text))
