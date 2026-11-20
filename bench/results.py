from bench.snapshot import RevealedResult, make_result
from bench.store import BenchStore
from study.registry import require_specimen
from study.store import StudyStore


def record_result(
    studies: StudyStore, bench: BenchStore, batch_id: str, specimen_id: str,
    outcome: int, source: str,
) -> RevealedResult:
    roster = require_specimen(studies, batch_id, specimen_id)
    return bench.save_result(roster.batch_id, make_result(specimen_id, outcome, source))
