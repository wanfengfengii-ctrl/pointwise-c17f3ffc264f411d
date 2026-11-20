from study.identity import validate_identifier
from study.roster import Roster, build_roster
from study.store import StudyStore


def create_study(store: StudyStore, batch_id: str, specimens: list[str] | tuple[str, ...]) -> Roster:
    return store.save_roster(build_roster(batch_id, specimens))


def get_roster(store: StudyStore, batch_id: str) -> Roster:
    return store.load_roster(batch_id)


def require_specimen(store: StudyStore, batch_id: str, specimen_id: str) -> Roster:
    name = validate_identifier(specimen_id, 'specimen_id')
    roster = get_roster(store, batch_id)
    if not roster.contains(name):
        raise KeyError((batch_id, name))
    return roster
