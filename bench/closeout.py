from bench.snapshot import BenchSnapshot
from bench.store import BenchStore
from study.registry import get_roster
from study.store import StudyStore


def close_results(studies: StudyStore, bench: BenchStore, batch_id: str) -> BenchSnapshot:
    return bench.save_or_recall_closeout(get_roster(studies, batch_id))
