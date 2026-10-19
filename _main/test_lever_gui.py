import io
import unittest
import h5py
import numpy as np
from lever_gui import load_lever_file, plot_lever_trials, lever_mean_sem

class LeverPlotTests(unittest.TestCase):
    def test_mean_sem_missing_samples(self):
        mean, sem = lever_mean_sem(np.array([[1., 2., np.nan], [3., np.nan, np.nan]]))
        np.testing.assert_allclose(mean, [2, 2, np.nan], equal_nan=True)
        np.testing.assert_allclose(sem, [1, np.nan, np.nan], equal_nan=True)

    def test_groups_scaling_and_trial_mask(self):
        source = io.BytesIO()
        with h5py.File(source, 'w') as f:
            signal = f.create_group('acquisition/LEVER')
            d = signal.create_dataset('data', data=np.arange(60))
            d.attrs['conversion'] = 0.1
            d.attrs['unit'] = 'V'
            signal.create_dataset('timestamps', data=np.arange(60)/10)
            trials = f.create_group('intervals/trials')
            trials.create_dataset('start_time', data=[0, 2, 4])
            trials.create_dataset('stop_time', data=[1, 4, 5])
            trials.create_dataset('trial_type', data=[b'Go', b'Test', b'Go'])
        source.seek(0)
        data = load_lever_file(source)
        fig = plot_lever_trials(data, 'LEVER')
        self.assertEqual([a.get_title() for a in fig.axes[:2]], ['GO (2 trials)', 'Test (1 trials)'])
        matrix = fig.axes[0].collections[0].get_array().reshape(2, -1)
        self.assertTrue(np.ma.getmaskarray(matrix)[:, 10:].all())
        self.assertAlmostEqual(float(matrix[1, 0]), 4.0)
        self.assertEqual([t.get_text() for t in fig.axes[0].get_yticklabels()], ['1', '3'])
        np.testing.assert_allclose(fig.get_size_inches(), [15, 8])
        self.assertAlmostEqual(fig.axes[2].lines[0].get_ydata()[0], 2.0)
        with self.assertRaisesRegex(ValueError, 'No matching'):
            plot_lever_trials(data, 'LEVER', '1', '2')
        with self.assertRaisesRegex(ValueError, 'different'):
            plot_lever_trials(data, 'LEVER', 'Go', 'Go')

if __name__ == '__main__':
    unittest.main()
