"""A handover demo: out-of-order amendments, a pending recompute and a reopened claim."""
import argparse
from contextlib import ExitStack, closing
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory

from archive.lookup import read_replacement, read_review
from archive.store import ArchiveStore
from bench.closeout import publish_amendment
from evaluation.accession import accept_piece, amendment_status
from evaluation.review import issue_replacement, read_current_review
from evaluation.store import AccessionStore
from bench.store import BenchStore
from examples.amendment_fixture import AMEND_A, AMEND_B, BATCH, correction_rows, seed
from forecast.store import ForecastStore
from study.store import StudyStore


def _connect(stack, root, name):
    return stack.enter_context(closing(sqlite3.connect(root / f'{name}.sqlite3')))


def run_demo():
    with TemporaryDirectory(prefix='liwan-amendment-') as directory, ExitStack() as stack:
        root = Path(directory)
        studies = StudyStore(_connect(stack, root, 'study'))
        forecasts = ForecastStore(_connect(stack, root, 'forecast'))
        bench = BenchStore(_connect(stack, root, 'bench'))
        accessions = AccessionStore(_connect(stack, root, 'accession'))
        archive = ArchiveStore(_connect(stack, root, 'archive'))

        closeout, original = seed(studies, forecasts, bench, accessions, archive)
        rows_a, rows_b = correction_rows()
        first = publish_amendment(bench, BATCH, closeout.closeout_id, AMEND_A, rows_a)
        second = publish_amendment(bench, BATCH, AMEND_A, AMEND_B, rows_b)
        bench.connection.close()

        # Out of order: the successor arrives first and waits for its parent.
        second_id = accept_piece(accessions, second)
        reverse_status = amendment_status(accessions, second_id)
        with_parent_pending = read_current_review(accessions, archive, original.report_id)

        # The accession library may be closed and reopened between deliveries.
        accessions.connection.close()
        accessions = AccessionStore(_connect(stack, root, 'accession'))
        first_id = accept_piece(accessions, first)
        first_status = amendment_status(accessions, first_id)
        second_status = amendment_status(accessions, second_id)

        # A current generation without a signed replacement is pending recompute.
        pending = read_current_review(accessions, archive, original.report_id)

        # Signing the full chain replaces the score; the archive is then reopened.
        replacement = issue_replacement(accessions, archive, original.report_id, second_id)
        archive.connection.close()
        accessions.connection.close()
        archive = ArchiveStore(_connect(stack, root, 'archive'))
        accessions = AccessionStore(_connect(stack, root, 'accession'))
        claimed = read_replacement(archive, replacement['report_id'])
        current = read_current_review(accessions, archive, original.report_id)
        original_json = read_review(archive, original.report_id, as_json=True)
        return {
            'original_mean': json.loads(original_json)['body']['mean'],
            'reverse_delivery_status': reverse_status,
            'with_parent_pending': with_parent_pending,
            'first_status': first_status,
            'second_status': second_status,
            'pending_recompute': pending,
            'issued_mean': replacement['body']['mean'],
            'amendment_chain': replacement['body']['amendment_chain'],
            'claimed_equals_issued': claimed == replacement,
            'current': current,
            'original_still_recallable': json.loads(original_json)['body']['mean'],
        }


def main(argv=None):
    parser = argparse.ArgumentParser(description='Run the amendment handover demonstration.')
    parser.parse_args(argv)
    try:
        print(json.dumps(run_demo(), ensure_ascii=False, sort_keys=True))
    except (ValueError, KeyError, sqlite3.Error, OSError) as exc:
        parser.exit(1, f'amendment demo failed: {exc}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
