from fractions import Fraction

from forecast.revisions import get_frozen_forecast
from forecast.snapshot import forecast_piece_payload
from tests.support import BATCH, LabCase, forecast_rows


class ForecastTests(LabCase):
    def setUp(self):
        super().setUp()
        self.roster = self.register()

    def test_frozen_revision(self):
        initial = self.freeze()
        amended = self.freeze('r2', rows=forecast_rows(a='3/4', a_source='amended:A'))
        self.assertEqual(initial.roster, self.roster)
        self.assertEqual(initial.revision_id, 'r1')
        self.assertEqual(amended.revision_id, 'r2')
        self.assertEqual(tuple(row.specimen_id for row in initial.rows), ('B', 'A'))
        self.assertEqual(tuple(row.probability for row in initial.rows), (Fraction(1, 2), Fraction(1, 4)))
        self.assertEqual(tuple(row.probability for row in amended.rows), (Fraction(1, 2), Fraction(3, 4)))
        self.assertEqual(tuple(row.source for row in initial.rows), ('model:B', 'model:A'))
        self.assertEqual(amended.rows[1].source, 'amended:A')
        self.assertEqual(get_frozen_forecast(self.forecasts, BATCH, 'r1'), initial)

    def test_coverage(self):
        base = forecast_rows()
        invalid = [
            base[:1], [base[0], base[0]], [*base, {**base[0], 'specimen_id': 'C'}],
            forecast_rows(a='5/4'), forecast_rows(a='-1/4'), forecast_rows(a='1/0'),
            forecast_rows(a=True), forecast_rows(a=0.25), forecast_rows(a_source=''),
            [{key: value for key, value in base[0].items() if key != 'source'}, base[1]],
        ]
        for rows in invalid:
            with self.subTest(rows=rows):
                with self.assertRaises(ValueError):
                    self.freeze(rows=rows)
                with self.assertRaises(KeyError):
                    get_frozen_forecast(self.forecasts, BATCH, 'r1')
        with self.assertRaises(KeyError):
            self.freeze(batch_id='unregistered')
        self.assertEqual(self.freeze().revision_id, 'r1')

    def test_frozen_reload(self):
        initial = self.freeze()
        amended = self.freeze('r2', rows=forecast_rows(a='3/4', a_source='amended:A'))
        self.forecasts = self.reopen(self.forecasts, 'forecast')
        old = get_frozen_forecast(self.forecasts, BATCH, 'r1')
        new = get_frozen_forecast(self.forecasts, BATCH, 'r2')
        self.assertEqual(old, initial)
        self.assertEqual(new, amended)
        self.assertEqual(forecast_piece_payload(old)['source_id'], 'r1')
        self.assertEqual(old.rows[1].probability, Fraction(1, 4))
        self.assertEqual(old.rows[1].source, 'model:A')
        self.assertEqual(new.rows[1].probability, Fraction(3, 4))
        with self.assertRaises(KeyError):
            get_frozen_forecast(self.forecasts, BATCH, 'r3')

    def test_revision_reuse(self):
        original = self.freeze()
        self.assertEqual(self.freeze(), original)
        with self.assertRaises(ValueError):
            self.freeze(rows=forecast_rows(a='1/2'))
        self.assertEqual(get_frozen_forecast(self.forecasts, BATCH, 'r1'), original)

    def test_equivalent_rows(self):
        original = self.freeze()
        equivalent = forecast_rows(a={'numerator': 2, 'denominator': 8}, b=Fraction(1, 2))
        self.assertEqual(self.freeze(rows=list(reversed(equivalent))), original)
        self.assertEqual(tuple(row.specimen_id for row in original.rows), ('B', 'A'))

    def test_provenance_conflict(self):
        original = self.freeze()
        with self.assertRaises(ValueError):
            self.freeze(rows=forecast_rows(a_source='another:A'))
        self.assertEqual(get_frozen_forecast(self.forecasts, BATCH, 'r1'), original)
