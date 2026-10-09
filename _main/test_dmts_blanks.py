import unittest
import numpy as np
from dmts_blanks import add_blank_responses, blank_rolling, blank_summary
from dmts_groups import export_curves


class BlankTests(unittest.TestCase):
    def test_coverage_and_either_side(self):
        trial = {'kind': 'blank'}
        detected = {'events': {'Left': [], 'Right': [1.]}, 'response_coverage': {'Left': True, 'Right': True}}
        add_blank_responses(trial, detected)
        self.assertFalse(trial['blank_left_response'])
        self.assertTrue(trial['blank_right_response'])
        self.assertTrue(trial['blank_any_response'])
        detected['response_coverage']['Left'] = False
        add_blank_responses(trial, detected)
        self.assertIsNone(trial['blank_any_response'])
        self.assertIsNone(trial['blank_left_response'])
        self.assertTrue(trial['blank_right_response'])

    def test_25_blanks_not_25_session_trials(self):
        trials = []
        for i in range(26):
            trials.append({'kind': 'match'})
            trials.append({'kind': 'blank', 'blank_any_response': i == 0})
        positions, rates = blank_rolling(trials, 'any')
        np.testing.assert_array_equal(positions, np.arange(2, 53, 2))
        self.assertEqual(rates[24], 4)
        self.assertEqual(rates[25], 0)
        trials.append({'kind': 'blank', 'blank_any_response': None})
        self.assertEqual(len(blank_rolling(trials, 'any')[0]), 26)
        self.assertEqual(blank_summary(trials)['any']['valid_trials'], 26)

    def test_groups_reset_sessions_and_ignore_engagement_filter_for_blanks(self):
        def trial(value):
            return dict(kind='blank', correct=None, engagement='disengaged', blank_any_response=value)
        payload = dict(format='dmts_batch_v2', sessions=[{'trials':[trial(True)]}, {'trials':[trial(False)]}])
        curves = export_curves(payload, engaged_only=True)
        np.testing.assert_array_equal(curves['blank_any'], [100, 0])
        self.assertTrue(np.isnan(curves['overall']).all())


if __name__ == '__main__':
    unittest.main()
