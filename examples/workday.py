"""A complete workday using the public laboratory workflows."""

import argparse
from contextlib import ExitStack, closing
from dataclasses import dataclass
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory

from archive.export import IssuedReview
from archive.lookup import read_review
from archive.store import ArchiveStore
from bench.closeout import close_results
from bench.results import record_result
from bench.reveal import reveal_result
from bench.snapshot import bench_piece_payload
from bench.store import BenchStore
from evaluation.accession import accept_piece
from evaluation.review import issue_review
from evaluation.store import AccessionStore
from forecast.revisions import freeze_forecast
from forecast.snapshot import forecast_piece_payload
from forecast.store import ForecastStore
from study.registry import create_study
from study.store import StudyStore


BATCH = 'liwan-17'
SPECIMENS = ('B', 'A')
FORECAST_ROWS = (
    {'specimen_id': 'A', 'probability': '1/4', 'source': 'model-r1:A'},
    {'specimen_id': 'B', 'probability': '1/2', 'source': 'model-r1:B'},
)
RESULT_ROWS = (
    {'specimen_id': 'A', 'outcome': 1, 'source': 'bench-17:A'},
    {'specimen_id': 'B', 'outcome': 0, 'source': 'bench-17:B'},
)


@dataclass(frozen=True)
class Workday:
    early_close_error: str
    original_report: IssuedReview
    recalled_report: IssuedReview
    corrected_report: IssuedReview
    original_json: str
    corrected_json: str


def run_workday() -> Workday:
    with TemporaryDirectory(prefix='liwan-workday-') as directory, ExitStack() as stack:
        root = Path(directory)

        def connect(name: str) -> sqlite3.Connection:
            return stack.enter_context(closing(sqlite3.connect(root / f'{name}.sqlite3')))

        studies = StudyStore(connect('study'))
        forecasts = ForecastStore(connect('forecast'))
        bench = BenchStore(connect('bench'))
        accessions = AccessionStore(connect('accession'))
        archive = ArchiveStore(connect('archive'))

        create_study(studies, BATCH, SPECIMENS)
        initial = freeze_forecast(studies, forecasts, BATCH, 'r1', FORECAST_ROWS)
        for row in RESULT_ROWS:
            record_result(studies, bench, BATCH, **row)
        reveal_result(studies, bench, BATCH, 'A')
        try:
            close_results(studies, bench, BATCH)
        except ValueError as exc:
            early_close_error = str(exc)
        else:
            raise ValueError('demo expected a refusal while B was still private')
        reveal_result(studies, bench, BATCH, 'B')
        closeout = close_results(studies, bench, BATCH)
        results_id = accept_piece(accessions, bench_piece_payload(closeout))
        initial_id = accept_piece(accessions, forecast_piece_payload(initial))
        bench.connection.close()
        original = issue_review(accessions, archive, initial_id, results_id)

        amended_rows = (
            {'specimen_id': 'A', 'probability': '3/4', 'source': 'model-r2:A'},
            FORECAST_ROWS[1],
        )
        amended = freeze_forecast(studies, forecasts, BATCH, 'r2', amended_rows)
        amended_id = accept_piece(accessions, forecast_piece_payload(amended))
        forecasts.connection.close()
        archive.connection.close()
        reopened = ArchiveStore(connect('archive'))
        corrected = issue_review(accessions, reopened, amended_id, results_id)
        recalled = read_review(reopened, original.report_id)
        return Workday(
            early_close_error, original, recalled, corrected,
            read_review(reopened, original.report_id, as_json=True),
            read_review(reopened, corrected.report_id, as_json=True),
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Run a coating laboratory review workday.')
    parser.parse_args(argv)
    try:
        day = run_workday()
    except (ValueError, KeyError, sqlite3.Error, OSError) as exc:
        parser.exit(1, f'workday failed: {exc}\n')
    print(f'Early close refused: {day.early_close_error}')
    print(f'Recalled original review: {day.original_json}')
    print(f'Explicit corrected review: {day.corrected_json}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
