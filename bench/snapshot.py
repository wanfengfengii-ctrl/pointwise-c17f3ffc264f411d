from collections.abc import Mapping
from dataclasses import dataclass

from study.identity import validate_identifier
from study.roster import Roster, roster_from_payload


@dataclass(frozen=True)
class RevealedResult:
    specimen_id: str
    outcome: int
    source: str


@dataclass(frozen=True)
class BenchSnapshot:
    roster: Roster
    closeout_id: str
    rows: tuple[RevealedResult, ...]


def validate_binary_result(value: object) -> int:
    if type(value) is not int or value not in (0, 1):
        raise ValueError('outcome must be the integer 0 or 1')
    return value


def make_result(specimen_id: object, outcome: object, source: object) -> RevealedResult:
    return RevealedResult(
        validate_identifier(specimen_id, 'specimen_id'),
        validate_binary_result(outcome),
        validate_identifier(source, 'bench source'),
    )


def build_bench_snapshot(roster: Roster, rows: object) -> BenchSnapshot:
    if not isinstance(rows, (list, tuple)):
        raise ValueError('result rows must be a list or tuple')
    expected = set(roster.specimens)
    by_specimen: dict[str, RevealedResult] = {}
    for row in rows:
        if isinstance(row, RevealedResult):
            result = make_result(row.specimen_id, row.outcome, row.source)
        elif isinstance(row, Mapping) and set(row) == {'specimen_id', 'outcome', 'source'}:
            result = make_result(row['specimen_id'], row['outcome'], row['source'])
        else:
            raise ValueError('result row requires specimen_id, outcome and source')
        name = result.specimen_id
        if name not in expected or name in by_specimen:
            raise ValueError(f'unknown or repeated result specimen {name!r}')
        by_specimen[name] = result
    missing = [name for name in roster.specimens if name not in by_specimen]
    if missing:
        raise ValueError(f'missing revealed results: {missing!r}')
    return BenchSnapshot(roster, f'results:{roster.batch_id}',
                         tuple(by_specimen[name] for name in roster.specimens))


def bench_piece_payload(snapshot: BenchSnapshot) -> dict:
    return {
        'kind': 'results',
        **snapshot.roster.as_payload(),
        'source_id': snapshot.closeout_id,
        'rows': [
            {'specimen_id': row.specimen_id, 'outcome': row.outcome, 'source': row.source}
            for row in snapshot.rows
        ],
    }


def bench_snapshot_from_payload(payload: Mapping) -> BenchSnapshot:
    if payload.get('kind') != 'results':
        raise ValueError('expected a results piece')
    snapshot = build_bench_snapshot(roster_from_payload(payload), payload.get('rows'))
    if payload.get('source_id') != snapshot.closeout_id:
        raise ValueError('result closeout identifier does not match batch')
    return snapshot
