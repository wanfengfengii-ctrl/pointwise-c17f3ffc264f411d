"""Named result amendments that replace individual measured outcomes."""

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
import json
import re

from bench.snapshot import validate_binary_result
from study.identity import validate_identifier
from study.roster import Roster, roster_from_payload


AMENDMENT_KIND = 'result-amendment'
AMENDMENT_FIELDS = {
    'kind', 'batch_id', 'roster_id', 'specimens', 'source_id', 'parent_id',
    'parent_sha256', 'rows',
}
RESERVED_PREFIX = 'results:'
_SHA256 = re.compile(r'^[0-9a-f]{64}$')


@dataclass(frozen=True)
class AmendmentRow:
    specimen_id: str
    outcome: int
    source: str


@dataclass(frozen=True)
class Amendment:
    roster: Roster
    source_id: str
    parent_id: str
    parent_sha256: str
    rows: tuple[AmendmentRow, ...]

    @property
    def kind(self) -> str:
        return AMENDMENT_KIND


def canonical_text(payload: Mapping) -> str:
    """The canonical JSON text used for amendment fingerprints and storage."""
    return json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=True)


def text_sha256(text: str) -> str:
    return sha256(text.encode('utf-8')).hexdigest()


def validate_amendment_id(value: object) -> str:
    name = validate_identifier(value, 'amendment_id')
    if name.startswith(RESERVED_PREFIX):
        raise ValueError(f'{RESERVED_PREFIX!r} prefix is reserved for the sealed result batch')
    return name


def validate_parent_id(value: object) -> str:
    return validate_identifier(value, 'parent_id')


def validate_parent_sha256(value: object) -> str:
    if not isinstance(value, str) or not _SHA256.match(value):
        raise ValueError('parent_sha256 must be a lowercase 64-character hexadecimal digest')
    return value


def validate_amendment_rows(roster: Roster, rows: object) -> tuple[AmendmentRow, ...]:
    if not isinstance(rows, (list, tuple)) or not rows:
        raise ValueError('amendment rows must be a nonempty ordered list or tuple')
    by_specimen: dict[str, AmendmentRow] = {}
    for row in rows:
        if not isinstance(row, Mapping) or set(row) != {'specimen_id', 'outcome', 'source'}:
            raise ValueError('amendment row requires specimen_id, outcome and source')
        specimen = validate_identifier(row['specimen_id'], 'specimen_id')
        if specimen not in roster.specimens or specimen in by_specimen:
            raise ValueError(f'unknown or repeated amendment specimen {specimen!r}')
        by_specimen[specimen] = AmendmentRow(
            specimen,
            validate_binary_result(row['outcome']),
            validate_identifier(row['source'], 'amendment source'),
        )
    return tuple(by_specimen[name] for name in roster.specimens if name in by_specimen)


def build_amendment(
    roster: Roster, source_id: object, parent_id: object, parent_sha256: object, rows: object
) -> Amendment:
    source = validate_amendment_id(source_id)
    parent = validate_parent_id(parent_id)
    if source == parent:
        raise ValueError('an amendment may not name itself as its parent')
    return Amendment(roster, source, parent, validate_parent_sha256(parent_sha256),
                     validate_amendment_rows(roster, rows))


def amendment_payload(amendment: Amendment) -> dict:
    return {
        'kind': AMENDMENT_KIND,
        **amendment.roster.as_payload(),
        'source_id': amendment.source_id,
        'parent_id': amendment.parent_id,
        'parent_sha256': amendment.parent_sha256,
        'rows': [
            {'specimen_id': row.specimen_id, 'outcome': row.outcome, 'source': row.source}
            for row in amendment.rows
        ],
    }


def encode_amendment(amendment: Amendment) -> str:
    return canonical_text(amendment_payload(amendment))


def amendment_from_payload(payload: object) -> Amendment:
    if not isinstance(payload, Mapping) or set(payload) != AMENDMENT_FIELDS:
        raise ValueError('invalid result-amendment envelope')
    if payload['kind'] != AMENDMENT_KIND:
        raise ValueError('expected a result-amendment piece')
    roster = roster_from_payload(payload)
    return build_amendment(
        roster, payload['source_id'], payload['parent_id'], payload['parent_sha256'],
        payload['rows'],
    )
