from copy import deepcopy
from fractions import Fraction
import json

from archive.lookup import read_review
from bench.snapshot import bench_piece_payload
from bench.store import BenchStore
from evaluation.accession import accept_piece, get_accepted_piece
from evaluation.review import issue_review
from forecast.snapshot import forecast_piece_payload
from study.registry import create_study
from study.store import StudyStore
from tests.support import BATCH, LabCase, LocalMessages, LostReply, archive_counts, forecast_rows


class ReviewTests(LabCase):
    def test_exact_brier(self):
        forecast_id, results_id = self.selected_pair()
        report = issue_review(self.accessions, self.archive, forecast_id, results_id)
        body = report.body
        self.assertEqual(body.batch_id, BATCH)
        self.assertEqual((body.forecast_accession, body.results_accession), (forecast_id, results_id))
        self.assertEqual((body.forecast_revision, body.results_closeout), ('r1', 'results:tray-17'))
        self.assertEqual(tuple(row.specimen_id for row in body.rows), ('B', 'A'))
        self.assertEqual(tuple(row.squared_error for row in body.rows), (Fraction(1, 4), Fraction(9, 16)))
        self.assertEqual([(row.forecast_source, row.result_source) for row in body.rows],
                         [('model:B', 'bench:B'), ('model:A', 'bench:A')])
        self.assertEqual(body.mean, Fraction(13, 32))
        self.assertEqual(report.receipt.report_id, report.report_id)
        self.assertEqual(read_review(self.archive, report.report_id), report)

    def test_accession_replay(self):
        self.register()
        prediction = forecast_piece_payload(self.freeze())
        results = bench_piece_payload(self.complete_results())
        messages = LocalMessages()
        messages.queue('held-results', results)
        messages.queue('first-forecast', prediction)
        with self.assertRaises(LostReply):
            messages.deliver('first-forecast', self.accessions, lose_reply=True)
        first_id = messages.committed['first-forecast']
        self.accessions = self.reopen(self.accessions, 'accession')
        with self.assertRaises(KeyError):
            get_accepted_piece(self.accessions, 'piece-2')
        original = get_accepted_piece(self.accessions, first_id)
        equivalent = deepcopy(prediction)
        equivalent['rows'].reverse()
        equivalent['rows'][0]['probability'] = {'numerator': 2, 'denominator': 8}
        messages.queue('retry-forecast', equivalent)
        self.assertEqual(messages.deliver('retry-forecast', self.accessions), first_id)
        self.assertEqual(get_accepted_piece(self.accessions, first_id), original)
        self.assertEqual(tuple(row.source for row in original.rows), ('model:B', 'model:A'))
        results_id = messages.deliver('held-results', self.accessions)
        report = issue_review(self.accessions, self.archive, first_id, results_id)
        self.assertEqual(report.body.forecast_accession, first_id)
        self.assertEqual(report.body.mean, Fraction(13, 32))

    def test_accession_conflict(self):
        self.register()
        prediction = forecast_piece_payload(self.freeze())
        results = bench_piece_payload(self.complete_results())
        bad = [
            None, {**prediction, 'kind': 'unknown'}, {**prediction, 'roster_id': 'invented'},
            {**prediction, 'rows': prediction['rows'][:1]},
            {**prediction, 'rows': [prediction['rows'][0]] * 2},
            {**prediction, 'source_id': ''}, {**results, 'source_id': 'results:other'},
            {**results, 'rows': [{**results['rows'][0], 'outcome': True}, results['rows'][1]]},
        ]
        for payload in bad:
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    accept_piece(self.accessions, payload)
        self.assertEqual(self.accessions.connection.execute('SELECT count(*) FROM accepted_pieces').fetchone(), (0,))
        token = accept_piece(self.accessions, prediction)
        original = get_accepted_piece(self.accessions, token)
        altered = deepcopy(prediction)
        altered['rows'][0]['source'] = 'other:B'
        with self.assertRaises(ValueError):
            accept_piece(self.accessions, altered)
        self.assertEqual(get_accepted_piece(self.accessions, token), original)
        self.assertEqual(accept_piece(self.accessions, prediction), token)

    def test_exact_thirds(self):
        ids = self.selected_pair(rows=forecast_rows(a='1/3', b=0))
        report = issue_review(self.accessions, self.archive, *ids)
        stored = read_review(self.archive, report.report_id)
        self.assertEqual(tuple(row.squared_error for row in stored.body.rows), (Fraction(0), Fraction(4, 9)))
        self.assertEqual(stored.body.mean, Fraction(2, 9))
        payload = json.loads(read_review(self.archive, report.report_id, as_json=True))['body']
        self.assertEqual(payload['rows'][0]['squared_error'], {'numerator': 0, 'denominator': 1})
        self.assertEqual(payload['rows'][1]['squared_error'], {'numerator': 4, 'denominator': 9})
        self.assertEqual(payload['mean'], {'numerator': 2, 'denominator': 9})

    def test_zero_export(self):
        self.register(specimens=('A',))
        forecast = self.freeze(rows=[{'specimen_id': 'A', 'probability': 1, 'source': 'model:A'}])
        from bench.closeout import close_results
        from bench.results import record_result
        from bench.reveal import reveal_result
        record_result(self.studies, self.bench, BATCH, 'A', 1, 'bench:A')
        reveal_result(self.studies, self.bench, BATCH, 'A')
        results = close_results(self.studies, self.bench, BATCH)
        ids = (accept_piece(self.accessions, forecast_piece_payload(forecast)),
               accept_piece(self.accessions, bench_piece_payload(results)))
        report = issue_review(self.accessions, self.archive, *ids)
        self.archive = self.reopen(self.archive, 'archive')
        self.assertEqual(read_review(self.archive, report.report_id).body.mean, Fraction(0))
        exported = read_review(self.archive, report.report_id, as_json=True)
        payload = json.loads(exported)
        zero = {'numerator': 0, 'denominator': 1}
        self.assertEqual(payload['body']['mean'], zero)
        self.assertEqual(payload['body']['rows'][0]['squared_error'], zero)
        self.assertEqual(payload['body']['rows'][0]['result_source'], 'bench:A')
        self.assertEqual(payload['receipt']['report_id'], report.report_id)
        self.assertEqual(read_review(self.archive, report.report_id, as_json=True), exported)

    def test_reject_mixed_batch(self):
        forecast_id, valid_results_id = self.selected_pair()
        self.register('other-tray')
        foreign = self.complete_results('other-tray')
        wrong_id = accept_piece(self.accessions, bench_piece_payload(foreign))
        with self.assertRaises(ValueError):
            issue_review(self.accessions, self.archive, forecast_id, wrong_id)
        self.assertEqual(archive_counts(self.archive), (0, 0))
        self.assertEqual(issue_review(self.accessions, self.archive, forecast_id, valid_results_id).body.mean,
                         Fraction(13, 32))

    def test_roster_mismatch(self):
        self.register()
        forecast_id = accept_piece(self.accessions, forecast_piece_payload(self.freeze()))
        other_studies = self.open_store(StudyStore, 'alternate-study')
        other_bench = self.open_store(BenchStore, 'alternate-bench')
        create_study(other_studies, BATCH, ('A', 'B'))
        foreign = self.complete_results(studies=other_studies, bench=other_bench)
        wrong_id = accept_piece(self.accessions, bench_piece_payload(foreign))
        with self.assertRaises(ValueError):
            issue_review(self.accessions, self.archive, forecast_id, wrong_id)
        self.assertEqual(archive_counts(self.archive), (0, 0))

    def test_bad_selection(self):
        forecast_id, results_id = self.selected_pair()
        with self.assertRaises(KeyError):
            issue_review(self.accessions, self.archive, 'piece-9999', results_id)
        with self.assertRaises(KeyError):
            issue_review(self.accessions, self.archive, forecast_id, 'piece-9999')
        for selection in ((results_id, forecast_id), (forecast_id, forecast_id), (results_id, results_id)):
            with self.subTest(selection=selection):
                with self.assertRaises(ValueError):
                    issue_review(self.accessions, self.archive, *selection)
        self.assertEqual(archive_counts(self.archive), (0, 0))
