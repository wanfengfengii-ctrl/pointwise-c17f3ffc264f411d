from hashlib import sha256
import json


def validate_identifier(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or '\x00' in value:
        raise ValueError(f'{field} must be a nonblank name without NUL')
    value.encode('utf-8')
    return value


def validate_study_identifiers(
    batch_id: object, specimens: object
) -> tuple[str, tuple[str, ...]]:
    batch = validate_identifier(batch_id, 'batch_id')
    if not isinstance(specimens, (list, tuple)) or not specimens:
        raise ValueError('specimens must be a nonempty ordered list or tuple')
    names = tuple(validate_identifier(item, 'specimen_id') for item in specimens)
    if len(set(names)) != len(names):
        raise ValueError('duplicate specimen in roster')
    return batch, names


def make_roster_id(batch_id: str, specimens: tuple[str, ...]) -> str:
    encoded = json.dumps([batch_id, specimens], ensure_ascii=False, separators=(',', ':'))
    return 'roster-' + sha256(encoded.encode('utf-8')).hexdigest()
