"""A sealed V1 tray and the two correction requests used in the handover example."""
from contextlib import ExitStack, closing
from fractions import Fraction
import sqlite3

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


BATCH = 'tray-correction-17'
AMEND_A = 'correction-A'
AMEND_B = 'correction-B'


def correction_rows():
    return (
        [{'specimen_id': 'A', 'outcome': 0, 'source': 'Amendment:A'}],
        [{'specimen_id': 'B', 'outcome': 1, 'source': 'Amendment:B'}],
    )


def seed(studies, forecasts, bench, accessions, archive):
    create_study(studies, BATCH, ['B', 'A'])
    forecast = freeze_forecast(studies, forecasts, BATCH, 'r1', [
        {'specimen_id': 'A', 'probability': '1/4', 'source': 'Model:A'},
        {'specimen_id': 'B', 'probability': '1/3', 'source': 'Model:B'},
    ])
    for specimen, outcome in [('A', 1), ('B', 0)]:
        record_result(studies, bench, BATCH, specimen, outcome, f'Bench:{specimen}')
        reveal_result(studies, bench, BATCH, specimen)
    root = close_results(studies, bench, BATCH)
    forecast_id = accept_piece(accessions, forecast_piece_payload(forecast))
    results_id = accept_piece(accessions, bench_piece_payload(root))
    return root, issue_review(accessions, archive, forecast_id, results_id)


def main():
    with ExitStack() as stack:
        stores = [
            store_type(stack.enter_context(closing(sqlite3.connect(':memory:'))))
            for store_type in (StudyStore, ForecastStore, BenchStore, AccessionStore, ArchiveStore)
        ]
        _, original = seed(*stores)
        original_json = read_review(stores[-1], original.report_id, as_json=True)
        if original.body.mean != Fraction(97, 288) or [row.specimen_id for row in original.body.rows] != ['B', 'A']:
            raise RuntimeError('unexpected score or roster order in the original report')
        print(original_json)


if __name__ == '__main__':
    main()
