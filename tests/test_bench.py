from bench.closeout import close_results
from bench.results import record_result
from bench.reveal import reveal_result
from bench.snapshot import RevealedResult, bench_piece_payload
from tests.support import BATCH, LabCase


class BenchTests(LabCase):
    def setUp(self):
        super().setUp()
        self.roster = self.register()

    def record(self, specimen, outcome, source):
        return record_result(self.studies, self.bench, BATCH, specimen, outcome, source)

    def reveal(self, specimen):
        return reveal_result(self.studies, self.bench, BATCH, specimen)

    def close_batch(self):
        return close_results(self.studies, self.bench, BATCH)

    def assert_unsealed(self):
        self.assertEqual(self.bench.connection.execute('SELECT count(*) FROM bench_closeouts').fetchone(), (0,))

    def test_close_in_roster_order(self):
        snapshot = self.complete_results()
        self.assertEqual(snapshot.roster, self.roster)
        self.assertEqual(snapshot.rows, (RevealedResult('B', 0, 'bench:B'), RevealedResult('A', 1, 'bench:A')))
        self.assertEqual(bench_piece_payload(snapshot)['source_id'], 'results:tray-17')
        self.assertEqual(self.close_batch(), snapshot)

    def test_require_reveal(self):
        self.record('A', 1, 'bench:A')
        self.record('B', 0, 'bench:B')
        self.reveal('A')
        with self.assertRaisesRegex(ValueError, 'B'):
            self.close_batch()
        self.assert_unsealed()
        self.reveal('B')
        self.assertEqual(tuple(row.specimen_id for row in self.close_batch().rows), ('B', 'A'))

    def test_result_validation(self):
        for outcome in (True, False, 2, -1, 0.0, '1'):
            with self.subTest(outcome=outcome):
                with self.assertRaises(ValueError):
                    self.record('A', outcome, 'bench:A')
        with self.assertRaises(ValueError):
            self.record('A', 1, '')
        with self.assertRaises(KeyError):
            self.record('C', 1, 'bench:C')
        with self.assertRaises(KeyError):
            record_result(self.studies, self.bench, 'unknown', 'A', 1, 'bench:A')
        with self.assertRaises(KeyError):
            self.reveal('C')
        with self.assertRaises(KeyError):
            close_results(self.studies, self.bench, 'unknown')
        with self.assertRaises(ValueError):
            self.reveal('A')
        self.assert_unsealed()

    def test_revealed_immutable(self):
        self.record('A', 0, 'initial:A')
        self.record('A', 1, 'corrected:A')
        fixed = self.reveal('A')
        self.assertEqual(fixed, RevealedResult('A', 1, 'corrected:A'))
        with self.assertRaises(ValueError):
            self.record('A', 0, 'corrected:A')
        with self.assertRaises(ValueError):
            self.record('A', 1, 'rewritten:A')
        self.assertEqual(self.record('A', 1, 'corrected:A'), fixed)
        self.bench = self.reopen(self.bench, 'bench')
        self.assertEqual(self.reveal('A'), fixed)
        self.record('B', 0, 'bench:B')
        self.reveal('B')
        closeout = self.close_batch()
        self.assertEqual(closeout.rows[1], fixed)
        self.assertEqual(self.close_batch(), closeout)

    def test_missing_result(self):
        self.record('A', 1, 'bench:A')
        self.reveal('A')
        with self.assertRaises(ValueError):
            self.close_batch()
        self.assert_unsealed()
        self.record('B', 0, 'bench:B')
        with self.assertRaises(ValueError):
            self.close_batch()
        self.assert_unsealed()
        self.reveal('B')
        self.assertEqual(len(self.close_batch().rows), 2)
