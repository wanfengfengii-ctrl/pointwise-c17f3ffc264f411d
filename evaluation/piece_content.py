from collections.abc import Mapping
from dataclasses import dataclass
import json

from bench.amendment import Amendment, amendment_from_payload, encode_amendment, canonical_text, text_sha256
from bench.snapshot import BenchSnapshot, RevealedResult, bench_piece_payload, bench_snapshot_from_payload
from forecast.import_rows import ForecastRow
from forecast.snapshot import ForecastSnapshot, forecast_piece_payload, forecast_snapshot_from_payload
from study.roster import Roster


@dataclass(frozen=True)
class FixedPiece:
    kind: str
    roster: Roster
    source_id: str
    rows: tuple[ForecastRow, ...] | tuple[RevealedResult, ...] | tuple
    parent_id: str | None = None
    parent_sha256: str | None = None


def _amendment_from_piece(piece: FixedPiece) -> Amendment:
    if piece.parent_id is None or piece.parent_sha256 is None:
        raise ValueError('amendment piece requires a parent')
    return Amendment(piece.roster, piece.source_id, piece.parent_id, piece.parent_sha256, piece.rows)


def normalize_piece(payload: object) -> FixedPiece:
    fields = {'kind', 'batch_id', 'roster_id', 'specimens', 'source_id', 'rows'}
    if isinstance(payload, Mapping) and payload.get('kind') == 'result-amendment':
        amendment = amendment_from_payload(payload)
        return FixedPiece('result-amendment', amendment.roster, amendment.source_id,
                          amendment.rows, amendment.parent_id, amendment.parent_sha256)
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
    elif piece.kind == 'result-amendment':
        return encode_amendment(_amendment_from_piece(piece))
    else:
        raise ValueError('unrecognized fixed-piece type')
    return json.dumps(payload, sort_keys=True, separators=(',', ':'))


def piece_canonical_text(piece: FixedPiece) -> str:
    """The canonical body text a parent fingerprint is taken over (always ASCII-escaped)."""
    if piece.kind == 'forecast':
        payload = forecast_piece_payload(ForecastSnapshot(piece.roster, piece.source_id, piece.rows))
    elif piece.kind == 'results':
        payload = bench_piece_payload(BenchSnapshot(piece.roster, piece.source_id, piece.rows))
    elif piece.kind == 'result-amendment':
        return encode_amendment(_amendment_from_piece(piece))
    else:
        raise ValueError('unrecognized fixed-piece type')
    return canonical_text(payload)


def piece_fingerprint(piece: FixedPiece) -> str:
    return text_sha256(piece_canonical_text(piece))


def decode_piece(text: str) -> FixedPiece:
    if not isinstance(text, str):
        raise ValueError('fixed-piece encoding must be JSON text')
    return normalize_piece(json.loads(text))
