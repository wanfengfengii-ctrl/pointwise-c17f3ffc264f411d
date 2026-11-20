from collections.abc import Mapping
from dataclasses import dataclass

from study.identity import make_roster_id, validate_study_identifiers


@dataclass(frozen=True)
class Roster:
    batch_id: str
    roster_id: str
    specimens: tuple[str, ...]

    def contains(self, specimen_id: str) -> bool:
        return specimen_id in self.specimens

    def as_payload(self) -> dict:
        return {
            'batch_id': self.batch_id,
            'roster_id': self.roster_id,
            'specimens': list(self.specimens),
        }


def build_roster(batch_id: object, specimens: object) -> Roster:
    batch, names = validate_study_identifiers(batch_id, specimens)
    return Roster(batch, make_roster_id(batch, names), names)


def roster_from_payload(payload: Mapping) -> Roster:
    roster = build_roster(payload.get('batch_id'), payload.get('specimens'))
    if payload.get('roster_id') != roster.roster_id:
        raise ValueError('roster identifier does not match batch and ordered specimens')
    return roster
