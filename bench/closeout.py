from bench.amendment import Amendment, amendment_payload
from bench.snapshot import BenchSnapshot
from bench.store import BenchStore
from study.registry import get_roster
from study.store import StudyStore


def close_results(studies: StudyStore, bench: BenchStore, batch_id: str) -> BenchSnapshot:
    return bench.save_or_recall_closeout(get_roster(studies, batch_id))


def publish_amendment(
    bench: BenchStore, batch_id: str, parent_id: str, amendment_id: str, rows: object
) -> dict:
    return amendment_payload(bench.publish_amendment(batch_id, parent_id, amendment_id, rows))


def read_amendment(bench: BenchStore, batch_id: str, amendment_id: str) -> dict:
    return amendment_payload(bench.load_amendment(batch_id, amendment_id))
