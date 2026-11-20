from fractions import Fraction
import sqlite3

from archive.lookup import read_review
from bench.closeout import close_results
from bench.reveal import reveal_result
from evaluation.accession import get_accepted_piece
from evaluation.review import issue_review
from forecast.revisions import get_frozen_forecast
from study.registry import get_roster
from tests.support import BATCH, LabCase, archive_counts, fail_receipt_write, fail_review_commit, forecast_rows


class ArchiveTests(LabCase):
    def test_issue_failure_and_reopen(self):
        ids = self.selected_pair()
        with fail_receipt_write(self.archive):
            with self.assertRaisesRegex(sqlite3.IntegrityError, 'receipt write refused'):
                issue_review(self.accessions, self.archive, *ids)
            self.assertFalse(self.archive.connection.in_transaction)
        self.archive = self.reopen(self.archive, 'archive')
        self.assertEqual(archive_counts(self.archive), (0, 0))
        with self.assertRaises(KeyError):
            read_review(self.archive, 'review-1')
        report = issue_review(self.accessions, self.archive, *ids)
        original_json = read_review(self.archive, report.report_id, as_json=True)
        self.freeze('r2', rows=forecast_rows(a='3/4', a_source='amended:A'))
        self.forecasts.connection.close()
        self.archive = self.reopen(self.archive, 'archive')
        restored = read_review(self.archive, report.report_id)
        self.assertEqual(restored, report)
        self.assertEqual(restored.body.forecast_revision, 'r1')
        self.assertEqual(restored.body.mean, Fraction(13, 32))
        self.assertEqual(restored.receipt.report_id, report.report_id)
        self.assertEqual(read_review(self.archive, report.report_id, as_json=True), original_json)
        self.assertEqual(archive_counts(self.archive), (1, 1))

    def test_commit_failure(self):
        ids = self.selected_pair()
        first = issue_review(self.accessions, self.archive, *ids)
        with fail_review_commit(self.archive):
            with self.assertRaisesRegex(sqlite3.IntegrityError, 'FOREIGN KEY constraint failed'):
                issue_review(self.accessions, self.archive, *ids)
            self.assertFalse(self.archive.connection.in_transaction)
        self.archive = self.reopen(self.archive, 'archive')
        self.assertEqual(archive_counts(self.archive), (1, 1))
        self.assertEqual(read_review(self.archive, first.report_id), first)
        with self.assertRaises(KeyError):
            read_review(self.archive, 'review-2')
        retried = issue_review(self.accessions, self.archive, *ids)
        self.assertEqual(retried.body, first.body)
        self.assertEqual(retried.receipt.report_id, retried.report_id)
        self.assertNotEqual(retried.report_id, first.report_id)
        self.assertEqual(archive_counts(self.archive), (2, 2))

    def test_init_reopen(self):
        ids = self.selected_pair()
        report = issue_review(self.accessions, self.archive, *ids)
        roster = get_roster(self.studies, BATCH)
        forecast = get_frozen_forecast(self.forecasts, BATCH, 'r1')
        amended = self.freeze('r2', rows=forecast_rows(a='3/4', a_source='amended:A'))
        result = reveal_result(self.studies, self.bench, BATCH, 'A')
        closeout = close_results(self.studies, self.bench, BATCH)
        accepted = tuple(get_accepted_piece(self.accessions, token) for token in ids)
        for store in (self.studies, self.forecasts, self.bench, self.accessions, self.archive):
            store.initialize()
            store.initialize()
        self.studies = self.reopen(self.studies, 'study')
        self.forecasts = self.reopen(self.forecasts, 'forecast')
        self.bench = self.reopen(self.bench, 'bench')
        self.accessions = self.reopen(self.accessions, 'accession')
        self.archive = self.reopen(self.archive, 'archive')
        self.assertEqual(get_roster(self.studies, BATCH), roster)
        self.assertEqual(get_frozen_forecast(self.forecasts, BATCH, 'r1'), forecast)
        self.assertEqual(get_frozen_forecast(self.forecasts, BATCH, 'r2'), amended)
        self.assertEqual(reveal_result(self.studies, self.bench, BATCH, 'A'), result)
        self.assertEqual(close_results(self.studies, self.bench, BATCH), closeout)
        self.assertEqual(tuple(get_accepted_piece(self.accessions, token) for token in ids), accepted)
        self.assertEqual(read_review(self.archive, report.report_id), report)
        self.assertEqual(archive_counts(self.archive), (1, 1))
        with self.assertRaises(KeyError):
            read_review(self.archive, 'review-9999')
