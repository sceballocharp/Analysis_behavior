import unittest
import numpy as np
import pandas as pd
from dmts_summary import plot_performance_by_sound

class SoundPerformanceTests(unittest.TestCase):
    def test_saved_accuracy_and_unknown_sounds(self):
        session = {'ResultsTable': pd.DataFrame(dict(SampleSoundId=[1,2,1,2,0,3], TestSoundId=[1,1,2,2,0,3], SavedOutcome=['Hit','FalseAlarm',b'Correct','MISS','Hit','unknown']))}
        fig = plot_performance_by_sound(session)
        ax = fig.axes[0]
        np.testing.assert_array_equal(ax.lines[0].get_xdata(), [0,1,2])
        np.testing.assert_allclose(ax.lines[0].get_ydata(), [100,0,np.nan], equal_nan=True)
        self.assertEqual(ax.get_ylabel(), 'Hit rate (%)')
        matrix = fig.axes[1].images[0].get_array().filled(np.nan)
        np.testing.assert_allclose(matrix, [[np.nan,100,np.nan],[0,np.nan,np.nan],[np.nan,np.nan,np.nan]], equal_nan=True)
        self.assertTrue(any('N/A' in text.get_text() for text in ax.texts))

    def test_nonmatch_only_and_unknown_pair(self):
        session = {'ResultsTable': pd.DataFrame(dict(SampleSoundId=[1,1,2], TestSoundId=[2,2,1],
                   SavedOutcome=['Correct','FalseAlarm','unknown']))}
        fig = plot_performance_by_sound(session)
        matrix = fig.axes[1].images[0].get_array().filled(np.nan)
        self.assertEqual(matrix[0,1], 50)
        self.assertTrue(np.isnan(matrix[1,0]))
        self.assertTrue(any('N/A' in text.get_text() for text in fig.axes[1].texts))

    def test_blank_only(self):
        session = {'ResultsTable': pd.DataFrame(dict(SampleSoundId=[0],TestSoundId=[0],SavedOutcome=['Hit']))}
        with self.assertRaisesRegex(ValueError, 'non-blank'):
            plot_performance_by_sound(session)

if __name__ == '__main__':
    unittest.main()
