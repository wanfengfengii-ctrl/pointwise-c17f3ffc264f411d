from bench.snapshot import RevealedResult
from bench.store import BenchStore
from study.registry import require_specimen
from study.store import StudyStore


def reveal_result(
    studies: StudyStore, bench: BenchStore, batch_id: str, specimen_id: str
) -> RevealedResult:
    roster = require_specimen(studies, batch_id, specimen_id)
    return bench.mark_revealed(roster.batch_id, specimen_id)
