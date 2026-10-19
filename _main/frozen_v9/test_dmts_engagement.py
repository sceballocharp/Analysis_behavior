import unittest
import pickle
import numpy as np
import pandas as pd
from dmts_batch import mark_engagement, summarize_session, plot_batch


class EngagementTests(unittest.TestCase):
    def test_threshold_and_intervening_trials(self):
        kinds = ['match'] * 5 + ['nonmatch', 'blank', 'match', 'nonmatch', 'match']
        trials = [dict(trial=i + 1, kind=kind, left_lick_count=0,
                       right_lick_count=int(i == 9), correct=None if kind == 'blank' else 0)
                  for i, kind in enumerate(kinds)]
        result = mark_engagement(trials, 5)
        self.assertEqual(result['periods'], [{'start_trial': 8, 'end_trial': 9}])
        self.assertFalse(trials[4]['disengaged'])
        self.assertFalse(trials[9]['disengaged'])
        self.assertEqual(trials[9]['silent_match_streak'], 0)

    def test_unknown_is_not_silence(self):
        trials = [dict(trial=i+1, kind='match', left_lick_count=None, right_lick_count=0, correct=0)
                  for i in range(10)]
        result = mark_engagement(trials)
        self.assertEqual(result['n_periods'], 0)
        self.assertEqual(result['unknown_eligible_trials'], 10)
        self.assertTrue(all(t['disengaged'] is None for t in trials))

    def test_real_detection_saved_performance_and_export(self):
        times = np.arange(0, 24, .01)
        right = np.zeros(len(times))
        right[(times >= 21.5) & (times < 21.55)] = 2
        session = dict(parameters=dict(TaskType='DMTS', TriggerType='Lick', SoundDuration_s='.2',
                       Delay_s='.1', ResponseWindow_s='1', Minlickcount='1',
                       TACLeftThreshold='1', TACRightThreshold='1'),
                       signals={'LeftLick':dict(timestamps=times, data=np.zeros(len(times))),
                                'RightLick':dict(timestamps=times, data=right)},
                       trialID={'full':np.array([])},
                       ResultsTable=pd.DataFrame(dict(SampleSoundId=[1]*8, TestSoundId=[1]*8,
                           StartTime=np.arange(8)*3., SavedOutcome=['Miss']*7+['FalseAlarm'])))
        result = summarize_session(session, 'test.nwb')
        self.assertEqual(result['total'], 0)
        self.assertEqual(result['engagement']['periods'], [{'start_trial':6,'end_trial':7}])
        self.assertEqual(result['engagement']['engaged_pct'], 75)
        restored = pickle.loads(pickle.dumps(result))
        self.assertTrue(restored['trials'][5]['disengaged'])
        self.assertEqual(restored['engagement']['silent_match_threshold'], 5)
        fig = plot_batch([result], show_engaged_only=True)
        self.assertEqual(len(fig.axes[1].patches), 1)
        self.assertTrue(any(line.get_label() == 'Engaged-only overall' for line in fig.axes[1].lines))


if __name__ == '__main__':
    unittest.main()
