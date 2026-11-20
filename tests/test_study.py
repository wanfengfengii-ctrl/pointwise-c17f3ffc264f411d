from study.registry import create_study, get_roster, require_specimen
from tests.support import BATCH, ROSTER, LabCase


class StudyTests(LabCase):
    def test_duplicate_roster(self):
        with self.assertRaises(ValueError):
            create_study(self.studies, BATCH, ('B', 'B', 'A'))
        with self.assertRaises(KeyError):
            get_roster(self.studies, BATCH)
        roster = create_study(self.studies, BATCH, ROSTER)
        self.assertEqual(roster.specimens, ('B', 'A'))
        self.assertEqual(get_roster(self.studies, BATCH), roster)

    def test_same_batch_reorder(self):
        original = self.register()
        self.assertEqual(create_study(self.studies, BATCH, ['B', 'A']), original)
        with self.assertRaises(ValueError):
            create_study(self.studies, BATCH, ('A', 'B'))
        self.assertEqual(get_roster(self.studies, BATCH), original)
        self.assertEqual(require_specimen(self.studies, BATCH, 'A'), original)
        with self.assertRaises(KeyError):
            require_specimen(self.studies, BATCH, 'C')

    def test_invalid_roster_inputs(self):
        for specimens in ((), 'BA', {'B', 'A'}, ['B', ' '], ['B', 1]):
            with self.subTest(specimens=specimens):
                with self.assertRaises(ValueError):
                    create_study(self.studies, BATCH, specimens)
        with self.assertRaises(ValueError):
            create_study(self.studies, '', ROSTER)
        with self.assertRaises(KeyError):
            get_roster(self.studies, BATCH)
