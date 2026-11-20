from copy import deepcopy
import json
import sqlite3

from archive.lookup import read_replacement, read_review
from bench.closeout import publish_amendment, read_amendment
from bench.reveal import reveal_result
from bench.snapshot import bench_piece_payload
from bench.results import record_result
from evaluation.accession import accept_piece, amendment_status, get_accepted_piece
from evaluation.review import issue_replacement, issue_review, read_current_review
from examples.amendment_fixture import AMEND_A, AMEND_B, BATCH, correction_rows
from forecast.snapshot import forecast_piece_payload
from study.registry import create_study
from tests.support import LabCase, archive_counts, fail_receipt_write, fail_review_commit


class AmendmentCase(LabCase):
    """The handover fixture: batch ``tray-correction-17`` with 97/288 and two amendments."""

    def seed_fixture(self):
        """Build exactly the sealed tray that examples/amendment_fixture describes."""
        create_study(self.studies, BATCH, ['B', 'A'])
        forecast = self.freeze(batch_id=BATCH, rows=[
            {'specimen_id': 'A', 'probability': '1/4', 'source': 'Model:A'},
            {'specimen_id': 'B', 'probability': '1/3', 'source': 'Model:B'},
        ])
        for specimen, outcome in [('A', 1), ('B', 0)]:
            record_result(self.studies, self.bench, BATCH, specimen, outcome, f'Bench:{specimen}')
            reveal_result(self.studies, self.bench, BATCH, specimen)
        from bench.closeout import close_results
        root = close_results(self.studies, self.bench, BATCH)
        forecast_id = accept_piece(self.accessions, forecast_piece_payload(forecast))
        results_id = accept_piece(self.accessions, bench_piece_payload(root))
        original = issue_review(self.accessions, self.archive, forecast_id, results_id)
        return root, original

    def fixture(self):
        root, original = self.seed_fixture()
        rows_a, rows_b = correction_rows()
        first = publish_amendment(self.bench, BATCH, root.closeout_id, AMEND_A, rows_a)
        second = publish_amendment(self.bench, BATCH, AMEND_A, AMEND_B, rows_b)
        return root, original, first, second


class PublishTests(AmendmentCase):
    def test_publish_shape_and_recall(self):
        root, *_ = self.fixture()
        first = read_amendment(self.bench, BATCH, AMEND_A)
        self.assertEqual(set(first), {
            'kind', 'batch_id', 'roster_id', 'specimens', 'source_id', 'parent_id',
            'parent_sha256', 'rows',
        })
        self.assertEqual(first['kind'], 'result-amendment')
        self.assertEqual(first['batch_id'], BATCH)
        self.assertEqual(first['roster_id'], root.roster.roster_id)
        self.assertEqual(first['specimens'], ['B', 'A'])
        self.assertEqual(first['source_id'], AMEND_A)
        self.assertEqual(first['parent_id'], root.closeout_id)
        self.assertEqual(first['rows'], [{'specimen_id': 'A', 'outcome': 0, 'source': 'Amendment:A'}])
        self.assertEqual(len(first['parent_sha256']), 64)
        self.assertEqual(first['parent_sha256'].lower(), first['parent_sha256'])
        second = read_amendment(self.bench, BATCH, AMEND_B)
        self.assertEqual(second['parent_id'], AMEND_A)
        self.assertNotEqual(second['parent_sha256'], first['parent_sha256'])
        self.bench = self.reopen(self.bench, 'bench')
        self.assertEqual(read_amendment(self.bench, BATCH, AMEND_A), first)
        self.assertEqual(read_amendment(self.bench, BATCH, AMEND_B), second)

    def test_fingerprint_is_canonical_parent_body(self):
        from bench.amendment import canonical_text, text_sha256
        from bench.snapshot import bench_piece_payload
        root, *_ = self.fixture()
        expected = text_sha256(canonical_text(bench_piece_payload(root)))
        self.assertEqual(read_amendment(self.bench, BATCH, AMEND_A)['parent_sha256'], expected)

    def test_row_order_is_normalised(self):
        root, original = self.seed_fixture()
        rows = [
            {'specimen_id': 'A', 'outcome': 0, 'source': 'Amendment:A'},
            {'specimen_id': 'B', 'outcome': 1, 'source': 'Amendment:B'},
        ]
        first = publish_amendment(self.bench, BATCH, root.closeout_id, AMEND_A, rows)
        self.assertEqual([row['specimen_id'] for row in first['rows']], ['B', 'A'])
        replay = publish_amendment(self.bench, BATCH, root.closeout_id, AMEND_A,
                                   list(reversed(rows)))
        self.assertEqual(replay, first)

    def test_replay_after_head_advanced(self):
        root, _original, first, second = self.fixture()
        rows_a, _rows_b = correction_rows()
        self.assertEqual(publish_amendment(self.bench, BATCH, root.closeout_id, AMEND_A, rows_a),
                         first)
        self.assertEqual(read_amendment(self.bench, BATCH, AMEND_B), second)

    def test_conflicts(self):
        root, _original = self.seed_fixture()
        rows_a, rows_b = correction_rows()
        first = publish_amendment(self.bench, BATCH, root.closeout_id, AMEND_A, rows_a)
        with self.assertRaises(ValueError):
            publish_amendment(self.bench, BATCH, root.closeout_id, AMEND_A, rows_b)
        publish_amendment(self.bench, BATCH, AMEND_A, AMEND_B, rows_b)
        with self.assertRaises(ValueError):
            publish_amendment(self.bench, BATCH, root.closeout_id, 'correction-C',
                              [{'specimen_id': 'A', 'outcome': 1, 'source': 'Amendment:C'}])
        with self.assertRaises(ValueError):
            publish_amendment(self.bench, BATCH, AMEND_B, AMEND_A, rows_a)
        self.assertEqual(read_amendment(self.bench, BATCH, AMEND_A), first)
        self.assertEqual(read_amendment(self.bench, BATCH, AMEND_B)['parent_id'], AMEND_A)

    def test_invalid_publication(self):
        root, _original = self.seed_fixture()
        valid = [{'specimen_id': 'A', 'outcome': 0, 'source': 'Amendment:A'}]
        for rows in (
            [], {},
            [{'specimen_id': 'A', 'outcome': 0}],
            [{'specimen_id': 'A', 'outcome': True, 'source': 'x'}],
            [{'specimen_id': 'A', 'outcome': 2, 'source': 'x'}],
            [{'specimen_id': 'A', 'outcome': 0, 'source': ''}],
            [{'specimen_id': 'C', 'outcome': 0, 'source': 'x'}],
            valid * 2,
            [{'specimen_id': 'A', 'outcome': 0, 'source': 'x', 'extra': 1}],
        ):
            with self.subTest(rows=rows):
                with self.assertRaises(ValueError):
                    publish_amendment(self.bench, BATCH, root.closeout_id, AMEND_A, rows)
        for bad_id in ('results:wrong', '', '   ', 'amendment\x00'):
            with self.subTest(case_id=bad_id):
                with self.assertRaises(ValueError):
                    publish_amendment(self.bench, BATCH, root.closeout_id, bad_id, valid)
        with self.assertRaises(ValueError):
            publish_amendment(self.bench, 'unknown-batch', root.closeout_id, AMEND_A, valid)
        with self.assertRaises(ValueError):
            publish_amendment(self.bench, BATCH, 'unknown-parent', AMEND_A, valid)
        with self.assertRaises(ValueError):
            publish_amendment(self.bench, BATCH, root.closeout_id, root.closeout_id, valid)
        with self.assertRaises(KeyError):
            read_amendment(self.bench, BATCH, 'correction-missing')
        with self.assertRaises(KeyError):
            read_amendment(self.bench, 'unknown-batch', AMEND_A)

    def test_amendment_needs_sealed_batch(self):
        self.register()
        with self.assertRaises(ValueError):
            publish_amendment(self.bench, BATCH, 'results:tray-17', AMEND_A,
                              [{'specimen_id': 'A', 'outcome': 0, 'source': 'x'}])


class AccessionChainTests(AmendmentCase):
    def test_reverse_delivery_and_status(self):
        _root, original, first, second = self.fixture()
        second_id = accept_piece(self.accessions, second)
        self.assertEqual(amendment_status(self.accessions, second_id), 'pending_proof')
        before = read_current_review(self.accessions, self.archive, original.report_id)
        self.assertEqual(before, {
            'status': 'original', 'amendment_accession': None,
            'report': json.loads(read_review(self.archive, original.report_id, as_json=True)),
        })
        with self.assertRaises(ValueError):
            issue_replacement(self.accessions, self.archive, original.report_id, second_id)
        self.accessions = self.reopen(self.accessions, 'accession')
        self.assertEqual(accept_piece(self.accessions, second), second_id)
        first_id = accept_piece(self.accessions, first)
        self.assertEqual(amendment_status(self.accessions, first_id), 'superseded')
        self.assertEqual(amendment_status(self.accessions, second_id), 'effective')
        self.assertEqual(accept_piece(self.accessions, first), first_id)

    def test_archive_may_close_during_acceptance(self):
        _root, _original, first, second = self.fixture()
        self.archive.connection.close()
        second_id = accept_piece(self.accessions, second)
        first_id = accept_piece(self.accessions, first)
        self.assertEqual(amendment_status(self.accessions, second_id), 'effective')
        self.assertEqual(amendment_status(self.accessions, first_id), 'superseded')

    def test_pending_wrong_fingerprint_becomes_invalid(self):
        self.register(BATCH, ('B', 'A'))
        self.freeze(batch_id=BATCH, rows=[
            {'specimen_id': 'A', 'probability': '1/4', 'source': 'Model:A'},
            {'specimen_id': 'B', 'probability': '1/3', 'source': 'Model:B'},
        ])
        from bench.closeout import close_results
        for specimen, outcome in [('A', 1), ('B', 0)]:
            record_result(self.studies, self.bench, BATCH, specimen, outcome, f'Bench:{specimen}')
            reveal_result(self.studies, self.bench, BATCH, specimen)
        seal = close_results(self.studies, self.bench, BATCH)
        rows = [{'specimen_id': 'A', 'outcome': 0, 'source': 'Amendment:A'}]
        roster = self.register(BATCH, ('B', 'A'))
        # The parent seal has not been accepted yet: the claim waits for proof.
        claim = {
            'kind': 'result-amendment', 'batch_id': BATCH,
            'roster_id': roster.roster_id, 'specimens': ['B', 'A'],
            'source_id': AMEND_A, 'parent_id': seal.closeout_id,
            'parent_sha256': '0' * 64, 'rows': rows,
        }
        pending = accept_piece(self.accessions, claim)
        self.assertEqual(amendment_status(self.accessions, pending), 'pending_proof')
        genuine = publish_amendment(self.bench, BATCH, seal.closeout_id, AMEND_B, rows)
        genuine_id = accept_piece(self.accessions, genuine)
        self.assertEqual(amendment_status(self.accessions, genuine_id), 'pending_proof')
        # Once the true parent lands, the wrong claim is invalid and does not block it.
        accept_piece(self.accessions, bench_piece_payload(seal))
        self.assertEqual(amendment_status(self.accessions, pending), 'invalid')
        self.assertEqual(amendment_status(self.accessions, genuine_id), 'effective')
        self.assertEqual(get_accepted_piece(self.accessions, pending).source_id, AMEND_A)
        with self.assertRaises(ValueError):
            accept_piece(self.accessions, {**claim, 'source_id': 'correction-C'})

    def test_same_parent_edge_conflict(self):
        root, _original = self.seed_fixture()
        first = publish_amendment(self.bench, BATCH, root.closeout_id, AMEND_A,
                                  [{'specimen_id': 'A', 'outcome': 0, 'source': 'Amendment:A'}])
        rival = {**first, 'source_id': 'correction-rival',
                 'rows': [{'specimen_id': 'A', 'outcome': 1, 'source': 'Rival:A'}]}
        accept_piece(self.accessions, first)
        with self.assertRaises(ValueError):
            accept_piece(self.accessions, rival)
        with self.assertRaises(ValueError):
            accept_piece(self.accessions, {**rival, 'source_id': 'correction-other'})

    def test_wrong_type_and_unknown(self):
        _root, original, first, _second = self.fixture()
        with self.assertRaises(ValueError):
            amendment_status(self.accessions, original.body.forecast_accession)
        with self.assertRaises(KeyError):
            amendment_status(self.accessions, 'piece-9999')

    def test_equivalent_resubmit_and_validation(self):
        root, _original = self.seed_fixture()
        first = publish_amendment(self.bench, BATCH, root.closeout_id, AMEND_A,
                                  [{'specimen_id': 'A', 'outcome': 0, 'source': 'Amendment:A'}])
        token = accept_piece(self.accessions, first)
        equivalent = deepcopy(first)
        equivalent['rows'] = [{**row} for row in first['rows']]
        self.assertEqual(accept_piece(self.accessions, equivalent), token)
        with self.assertRaises(ValueError):
            accept_piece(self.accessions, {**first, 'rows': [
                {'specimen_id': 'A', 'outcome': 1, 'source': 'Amendment:A'}]})
        for broken in (
            {**first, 'specimens': ['A', 'B']},
            {**first, 'roster_id': 'invented'},
            {**first, 'parent_sha256': 'XYZ'},
            {**first, 'parent_id': AMEND_A},
            {**first, 'extra': 1},
            {**first, 'rows': []},
            {**first, 'kind': 'results'},
        ):
            with self.subTest(broken=broken):
                with self.assertRaises(ValueError):
                    accept_piece(self.accessions, broken)
        self.assertEqual(get_accepted_piece(self.accessions, token).source_id, AMEND_A)


class ReplacementTests(AmendmentCase):
    def test_single_generation_score(self):
        _root, original, first, _second = self.fixture()
        first_id = accept_piece(self.accessions, first)
        report = issue_replacement(self.accessions, self.archive, original.report_id, first_id)
        self.assertEqual(report['body']['mean'], {'numerator': 25, 'denominator': 288})
        self.assertEqual(report['body']['original_report_id'], original.report_id)
        self.assertEqual(report['body']['amendment_accession'], first_id)
        self.assertEqual(report['body']['forecast_accession'], original.body.forecast_accession)
        self.assertEqual(report['body']['results_accession'], original.body.results_accession)
        self.assertEqual(report['body']['forecast_revision'], 'r1')
        self.assertEqual(report['body']['results_closeout'], f'results:{BATCH}')
        self.assertEqual(report['body']['amendment_chain'],
                         [{'source_id': AMEND_A, 'accession_id': first_id}])
        self.assertEqual(report['receipt'], {'report_id': report['report_id']})
        self.assertEqual([row['specimen_id'] for row in report['body']['rows']], ['B', 'A'])
        self.assertEqual(report['body']['rows'][1]['result_source'], 'Amendment:A')
        self.assertEqual(read_current_review(self.accessions, self.archive, original.report_id), {
            'status': 'replacement', 'amendment_accession': first_id, 'report': report,
        })

    def test_full_chain_and_history(self):
        _root, original, first, second = self.fixture()
        first_id = accept_piece(self.accessions, first)
        first_report = issue_replacement(self.accessions, self.archive, original.report_id, first_id)
        second_id = accept_piece(self.accessions, second)
        self.assertEqual(read_current_review(self.accessions, self.archive, original.report_id), {
            'status': 'pending_recompute', 'amendment_accession': second_id, 'report': None,
        })
        second_report = issue_replacement(self.accessions, self.archive, original.report_id, second_id)
        self.assertEqual(second_report['body']['mean'], {'numerator': 73, 'denominator': 288})
        self.assertEqual(second_report['body']['amendment_chain'], [
            {'source_id': AMEND_A, 'accession_id': first_id},
            {'source_id': AMEND_B, 'accession_id': second_id},
        ])
        self.assertEqual([row['squared_error'] for row in second_report['body']['rows']],
                         [{'numerator': 4, 'denominator': 9}, {'numerator': 1, 'denominator': 16}])
        self.assertEqual(issue_replacement(self.accessions, self.archive,
                                           original.report_id, first_id), first_report)
        self.assertEqual(read_current_review(self.accessions, self.archive,
                                             original.report_id)['report'], second_report)
        self.archive = self.reopen(self.archive, 'archive')
        self.assertions_on_reopen(original, first_report, second_report)

    def assertions_on_reopen(self, original, first_report, second_report):
        self.assertEqual(read_replacement(self.archive, first_report['report_id']), first_report)
        self.assertEqual(read_replacement(self.archive, second_report['report_id']), second_report)
        self.assertEqual(json.loads(read_review(self.archive, original.report_id, as_json=True))
                         ['body']['mean'], {'numerator': 97, 'denominator': 288})
        self.assertEqual(read_review(self.archive, original.report_id).body.mean,
                         original.body.mean)

    def test_skipping_generation_is_rejected(self):
        _root, original, first, second = self.fixture()
        second_id = accept_piece(self.accessions, second)
        self.assertEqual(amendment_status(self.accessions, second_id), 'pending_proof')
        with self.assertRaises(ValueError):
            issue_replacement(self.accessions, self.archive, original.report_id, second_id)
        accept_piece(self.accessions, first)
        report = issue_replacement(self.accessions, self.archive, original.report_id, second_id)
        self.assertEqual(report['body']['mean'], {'numerator': 73, 'denominator': 288})
        # the first generation never had a signed replacement, so it cannot be signed later
        rows_a, _rows_b = correction_rows()
        first = read_amendment(self.bench, BATCH, AMEND_A)
        first_id = accept_piece(self.accessions, first)
        with self.assertRaises(ValueError):
            issue_replacement(self.accessions, self.archive, original.report_id, first_id)

    def test_interleaved_current_read(self):
        _root, original, first, second = self.fixture()
        first_id = accept_piece(self.accessions, first)
        first_report = issue_replacement(self.accessions, self.archive, original.report_id, first_id)
        self.assertEqual(read_current_review(self.accessions, self.archive,
                                             original.report_id)['report'], first_report)
        # The later generation becomes effective as soon as its parent lands.
        second_id = accept_piece(self.accessions, second)
        self.assertEqual(second_id, accept_piece(self.accessions, second))
        pending = read_current_review(self.accessions, self.archive, original.report_id)
        self.assertEqual(pending['status'], 'pending_recompute')
        self.assertEqual(pending['amendment_accession'], second_id)
        self.assertIsNone(pending['report'])
        # A late request against the superseded first generation reuses its signed report
        # but cannot make it current again.
        late = issue_replacement(self.accessions, self.archive, original.report_id, first_id)
        self.assertEqual(late, first_report)
        self.assertEqual(read_current_review(self.accessions, self.archive,
                                             original.report_id)['amendment_accession'], second_id)
        report = issue_replacement(self.accessions, self.archive, original.report_id, second_id)
        current = read_current_review(self.accessions, self.archive, original.report_id)
        self.assertEqual(current, {'status': 'replacement', 'amendment_accession': second_id,
                                   'report': report})
        self.assertEqual(current['report']['body']['mean'],
                         {'numerator': 73, 'denominator': 288})

    def test_failures_roll_back_archive_only(self):
        _root, original, first, second = self.fixture()
        first_id = accept_piece(self.accessions, first)
        issue_replacement(self.accessions, self.archive, original.report_id, first_id)
        second_id = accept_piece(self.accessions, second)
        before = archive_counts(self.archive)
        for failure in (fail_receipt_write, fail_review_commit):
            with failure(self.archive), self.assertRaises(sqlite3.Error):
                issue_replacement(self.accessions, self.archive, original.report_id, second_id)
            self.assertEqual(archive_counts(self.archive), before)
            self.assertEqual(read_current_review(self.accessions, self.archive, original.report_id), {
                'status': 'pending_recompute', 'amendment_accession': second_id, 'report': None,
            })
        self.assertEqual(amendment_status(self.accessions, second_id), 'effective')
        self.archive = self.reopen(self.archive, 'archive')
        report = issue_replacement(self.accessions, self.archive, original.report_id, second_id)
        self.assertEqual(report['body']['mean'], {'numerator': 73, 'denominator': 288})
        self.assertEqual(archive_counts(self.archive), tuple(n + 1 for n in before))

    def test_bad_requests(self):
        _root, original, first, _second = self.fixture()
        first_id = accept_piece(self.accessions, first)
        with self.assertRaises(KeyError):
            issue_replacement(self.accessions, self.archive, 'review-9999', first_id)
        with self.assertRaises(KeyError):
            read_current_review(self.accessions, self.archive, 'review-9999')
        with self.assertRaises(ValueError):
            issue_replacement(self.accessions, self.archive, original.report_id,
                              original.body.forecast_accession)
        with self.assertRaises(KeyError):
            issue_replacement(self.accessions, self.archive, original.report_id, 'piece-9999')
        with self.assertRaises(ValueError):
            read_replacement(self.archive, original.report_id)
        with self.assertRaises(KeyError):
            read_replacement(self.archive, 'review-9999')
        self.assertEqual(archive_counts(self.archive), (1, 1))

    def test_foreign_batch_amendment_is_refused(self):
        _root, original, first, _second = self.fixture()
        self.register('other-tray', ('B', 'A'))
        other = self.freeze('r1', batch_id='other-tray')
        other_root = self.complete_results('other-tray')
        accept_piece(self.accessions, forecast_piece_payload(other))
        accept_piece(self.accessions, bench_piece_payload(other_root))
        foreign = publish_amendment(self.bench, 'other-tray', other_root.closeout_id,
                                    'foreign-A',
                                    [{'specimen_id': 'A', 'outcome': 0, 'source': 'F:A'}])
        foreign_id = accept_piece(self.accessions, foreign)
        self.assertEqual(amendment_status(self.accessions, foreign_id), 'effective')
        with self.assertRaises(ValueError):
            issue_replacement(self.accessions, self.archive, original.report_id, foreign_id)
