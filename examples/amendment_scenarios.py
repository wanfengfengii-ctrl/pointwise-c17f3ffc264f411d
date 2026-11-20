"""Business checks for the correction handover once its public entries are implemented."""
import json
import sqlite3
import unittest

from archive.lookup import read_replacement, read_review
from bench.closeout import publish_amendment, read_amendment
from evaluation.accession import accept_piece, amendment_status
from evaluation.review import issue_replacement, read_current_review
from examples.amendment_fixture import AMEND_A, AMEND_B, BATCH, correction_rows, seed
from tests.support import LabCase, archive_counts, fail_receipt_write, fail_review_commit


class AmendmentScenarios(LabCase):
    def prepare_delivery(self):
        root, original = seed(self.studies, self.forecasts, self.bench, self.accessions, self.archive)
        rows_a, rows_b = correction_rows()
        first = publish_amendment(self.bench, BATCH, root.closeout_id, AMEND_A, rows_a)
        second = publish_amendment(self.bench, BATCH, AMEND_A, AMEND_B, rows_b)
        self.bench = self.reopen(self.bench, 'bench')
        self.assertEqual(read_amendment(self.bench, BATCH, AMEND_A), first)
        self.assertEqual(read_amendment(self.bench, BATCH, AMEND_B), second)
        for store in (self.studies, self.forecasts, self.bench):
            store.connection.close()
        return original.report_id, first, second

    def test_reverse_delivery(self):
        original_id, first, second = self.prepare_delivery()
        original_json = read_review(self.archive, original_id, as_json=True)
        second_id = accept_piece(self.accessions, second)
        self.assertEqual(amendment_status(self.accessions, second_id), 'pending_proof')
        before = read_current_review(self.accessions, self.archive, original_id)
        self.assertEqual(before, {
            'status': 'original', 'amendment_accession': None, 'report': json.loads(original_json),
        })
        with self.assertRaises(ValueError):
            issue_replacement(self.accessions, self.archive, original_id, second_id)
        self.archive.connection.close()
        self.accessions = self.reopen(self.accessions, 'accession')
        first_id = accept_piece(self.accessions, first)
        self.assertEqual(accept_piece(self.accessions, second), second_id)
        self.assertEqual(amendment_status(self.accessions, first_id), 'superseded')
        self.assertEqual(amendment_status(self.accessions, second_id), 'effective')
        self.archive = self.open_store(type(self.archive), 'archive')
        pending = read_current_review(self.accessions, self.archive, original_id)
        self.assertEqual(pending, {
            'status': 'pending_recompute', 'amendment_accession': second_id, 'report': None,
        })
        replacement = issue_replacement(self.accessions, self.archive, original_id, second_id)
        body = replacement['body']
        self.assertEqual(body['mean'], {'numerator': 73, 'denominator': 288})
        self.assertEqual(body['amendment_chain'], [
            {'source_id': AMEND_A, 'accession_id': first_id},
            {'source_id': AMEND_B, 'accession_id': second_id},
        ])
        self.assertEqual([(row['specimen_id'], row['outcome'], row['result_source']) for row in body['rows']],
                         [('B', 1, 'Amendment:B'), ('A', 0, 'Amendment:A')])
        self.archive = self.reopen(self.archive, 'archive')
        self.accessions = self.reopen(self.accessions, 'accession')
        current = read_current_review(self.accessions, self.archive, original_id)
        self.assertEqual(current, {
            'status': 'replacement', 'amendment_accession': second_id, 'report': replacement,
        })
        self.accessions.connection.close()
        recalled = read_replacement(self.archive, replacement['report_id'])
        self.assertEqual(recalled, replacement)
        self.assertEqual(read_review(self.archive, original_id, as_json=True), original_json)
        print(json.dumps({'before': before, 'pending': pending, 'current': current,
                          'recalled': recalled}, ensure_ascii=False, sort_keys=True))

    def test_failed_second_issue(self):
        original_id, first, second = self.prepare_delivery()
        first_id = accept_piece(self.accessions, first)
        first_report = issue_replacement(self.accessions, self.archive, original_id, first_id)
        self.assertEqual(first_report['body']['mean'], {'numerator': 25, 'denominator': 288})
        second_id = accept_piece(self.accessions, second)
        before_failure = archive_counts(self.archive)
        for failure in (fail_receipt_write, fail_review_commit):
            with failure(self.archive), self.assertRaises(sqlite3.Error):
                issue_replacement(self.accessions, self.archive, original_id, second_id)
            self.assertEqual(archive_counts(self.archive), before_failure)
            self.assertEqual(read_current_review(self.accessions, self.archive, original_id), {
                'status': 'pending_recompute', 'amendment_accession': second_id, 'report': None,
            })
        self.archive = self.reopen(self.archive, 'archive')
        second_report = issue_replacement(self.accessions, self.archive, original_id, second_id)
        self.assertEqual(second_report['body']['mean'], {'numerator': 73, 'denominator': 288})
        self.assertEqual(second_report['receipt'], {'report_id': second_report['report_id']})
        self.assertEqual(issue_replacement(self.accessions, self.archive, original_id, second_id), second_report)
        self.assertEqual(issue_replacement(self.accessions, self.archive, original_id, first_id), first_report)
        self.assertEqual(read_current_review(self.accessions, self.archive, original_id)['report'], second_report)
        self.assertEqual(archive_counts(self.archive), tuple(count + 1 for count in before_failure))


if __name__ == '__main__':
    unittest.main(verbosity=2)
