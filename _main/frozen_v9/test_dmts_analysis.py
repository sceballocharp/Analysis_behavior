import unittest
from pathlib import Path
import numpy as np
import pandas as pd
from dmts_analysis import analyze_dmts, crossings, score_trial, plot_dmts_trial
from test_hit_source import behavior


class DMTSTests(unittest.TestCase):
    def session(self):
        def signal(data):
            return dict(data=np.asarray(data), start=0., rate=1000.)
        left = np.zeros(5000)
        right = np.zeros(5000)
        # Before window: ignored; at onset: counted; at end: excluded.
        left[1900:1910] = 1
        left[2000:2010] = 1
        left[3000:3010] = 1
        right[2100:2110] = 2
        return dict(parameters=dict(TaskType='DMTS', TriggerType='Lick',
                    SoundDuration_s='.5', Delay_s='1', ResponseWindow_s='1',
                    Minlickcount='1', TACLeftThreshold='.5', TACRightThreshold='1.5'),
                    signals={'LeftLick': signal(left), 'RightLick': signal(right),
                             'SoundCopy': signal(np.zeros(5000)), 'Reward': signal(np.zeros(5000))},
                    ResultsTable=pd.DataFrame(dict(SampleSoundId=[1], TestSoundId=[1],
                             StartTime=[0.], SavedOutcome=['Hit'])), nTotalTrials=1,
                    trialID={'full': np.array([99])})

    def test_response_window_and_independent_thresholds(self):
        result = analyze_dmts(self.session())
        trial = result['trials'][0]
        np.testing.assert_allclose(trial['events']['Left'], [2.])
        np.testing.assert_allclose(trial['events']['Right'], [2.1])
        self.assertEqual(trial['outcome'], 'Hit')
        self.assertEqual(trial['choice'], 'left')
        self.assertEqual(result['performance']['total'], 100)

    def test_high_before_window_is_not_an_extra_lick(self):
        session = self.session()
        session['signals']['LeftLick']['data'][1900:2200] = 1
        self.assertEqual(len(analyze_dmts(session)['trials'][0]['events']['Left']), 0)

    def test_choice_rules(self):
        self.assertEqual(score_trial([2., 2.2], [2., 2.1], 2, 'match'), ('FalseAlarm', 'right'))
        self.assertEqual(score_trial([2.], [2.], 1, 'match'), ('Hit', 'left'))
        self.assertEqual(score_trial([2.2], [2.], 1, 'nonmatch'), ('FalseAlarm', 'left'))
        self.assertEqual(score_trial([], [2.], 1, 'nonmatch'), ('Correct', ''))
        self.assertEqual(score_trial([], [], 1, 'match'), ('Miss', ''))
        self.assertEqual(score_trial([2.], [2.], 1, 'blank'), ('Blank', ''))

    def test_missing_channel_uses_saved_outcome_explicitly(self):
        session = self.session()
        del session['signals']['RightLick']
        result = analyze_dmts(session)
        self.assertEqual(result['missing_channels'], ['RightLick'])
        self.assertIsNone(result['trials'][0]['outcome'])
        self.assertEqual(result['saved_fallback_count'], 1)

    def test_timestamped_signal(self):
        signal = {'data': np.array([0., 1., 1., 0., 1.]), 'timestamps': np.array([1., 1.2, 1.4, 1.6, 1.8])}
        np.testing.assert_allclose(crossings(signal, .5), [1.2, 1.8])

    def test_new_nwb_and_render(self):
        path = (Path(__file__).resolve().parents[2] / 'pyBEHAVIOR/data/Sebastian/behavior_data/'
                'M99/20260924/132256_Data/Sebastian_M99_132256_Data.nwb')
        if not path.exists():
            self.skipTest('Local DMTS fixture not available')
        session = behavior.load_session_data_fromFile(path)
        performance = behavior.extract_performance(session)
        self.assertEqual(performance['n_blank'], 2)
        self.assertEqual(performance['n_go'], 4)
        self.assertEqual(performance['n_nogo'], 0)
        result = analyze_dmts(session)
        self.assertEqual(len(result['trials']), 6)
        self.assertEqual(result['missing_channels'], [])
        self.assertEqual(result['saved_fallback_count'], 0)
        self.assertEqual(result['mismatch_count'], 0)
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        output = Path(__file__).resolve().parents[1] / 'outputs/dmts_preview'
        output.mkdir(parents=True, exist_ok=True)
        for index in [0, 2, 5]:
            fig = plot_dmts_trial(session, index, show=False)
            self.assertEqual(len(fig.axes), 4)
            fig.savefig(output / f'trial_{index + 1}.png', dpi=120)
            plt.close(fig)


if __name__ == '__main__':
    unittest.main()
