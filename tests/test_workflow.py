from contextlib import redirect_stderr
from fractions import Fraction
from io import StringIO
import json
import unittest

from examples.workday import BATCH, FORECAST_ROWS, RESULT_ROWS, SPECIMENS, main, run_workday


class WorkflowTests(unittest.TestCase):
    def test_workday(self):
        day = run_workday()
        self.assertIn('B', day.early_close_error)
        original = day.original_report
        self.assertEqual(original.body.batch_id, BATCH)
        self.assertEqual(original.body.forecast_revision, 'r1')
        self.assertEqual(original.body.results_closeout, 'results:liwan-17')
        self.assertEqual(original.body.mean, Fraction(13, 32))
        self.assertEqual([(row.specimen_id, row.squared_error) for row in original.body.rows],
                         [('B', Fraction(1, 4)), ('A', Fraction(9, 16))])
        self.assertEqual(day.recalled_report, original)
        self.assertEqual(day.corrected_report.body.mean, Fraction(5, 32))
        self.assertEqual(day.corrected_report.body.forecast_revision, 'r2')
        self.assertNotEqual(day.corrected_report.report_id, original.report_id)
        self.assertEqual(day.corrected_report.body.results_accession, original.body.results_accession)
        recalled = json.loads(day.original_json)
        corrected = json.loads(day.corrected_json)
        self.assertEqual(recalled['report_id'], original.report_id)
        self.assertEqual(recalled['receipt']['report_id'], original.report_id)
        self.assertEqual(recalled['body']['rows'][1]['forecast_source'], 'model-r1:A')
        self.assertEqual(recalled['body']['rows'][1]['result_source'], 'bench-17:A')
        self.assertEqual(corrected['body']['rows'][1]['forecast_source'], 'model-r2:A')
        self.assertEqual(recalled['body']['mean'], {'numerator': 13, 'denominator': 32})
        self.assertEqual(corrected['body']['mean'], {'numerator': 5, 'denominator': 32})

        evidence = {
            'case_id': 'v6',
            'input': {'batch_id': BATCH, 'roster': SPECIMENS,
                      'forecast_rows': FORECAST_ROWS, 'result_rows': RESULT_ROWS},
            'expected': {'specimens': ['B', 'A'], 'errors': ['1/4', '9/16'], 'mean': '13/32'},
            'actual': {'specimens': [row.specimen_id for row in original.body.rows],
                       'errors': [str(row.squared_error) for row in original.body.rows],
                       'mean': str(original.body.mean)},
            'downstream_expected': {'revision': 'r1', 'mean': {'numerator': 13, 'denominator': 32},
                                    'amended_mean': {'numerator': 5, 'denominator': 32}},
            'downstream_actual': {'revision': recalled['body']['forecast_revision'],
                                  'mean': recalled['body']['mean'], 'amended_mean': corrected['body']['mean']},
            'code_paths': ['evaluation/accession.py', 'evaluation/alignment.py', 'evaluation/brier.py',
                           'evaluation/review.py', 'archive/store.py', 'archive/lookup.py'],
            'oracle': 'Hand calculation: (1/2-0)^2=1/4, (1/4-1)^2=9/16; average 13/32. '
                      'For r2, (3/4-1)^2=1/16; average 5/32. Recall keeps the r1 result.',
        }
        print('POINTWISE_SCENARIO ' + json.dumps(evidence, sort_keys=True, separators=(',', ':')))

    def test_demo_argument_failure(self):
        with redirect_stderr(StringIO()) as errors:
            with self.assertRaises(SystemExit) as raised:
                main(['--unrecognized'])
        self.assertEqual(raised.exception.code, 2)
        self.assertIn('--unrecognized', errors.getvalue())
