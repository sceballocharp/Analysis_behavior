import tempfile
import unittest
from pathlib import Path
import numpy as np
from dmts_voltage_viewer import parse_dmts_log_file, voltages_to_pattern_grid, voltage_presentations_by_stim

class VoltageLogTests(unittest.TestCase):
    def test_pairs_and_missing_measurements(self):
        log = ('Trial:,7\nTrial ID:,abc\nPresentation:,sample\nStimulus:,S1\n'
               'LED pattern:,P1N1 P2N2\nPresentation completed:,true\n'
               'Measured voltages (V):\n1,2,3,4,5,6,7,8,9,10\n'
               'Trial:,7\nTrial ID:,abc\nPresentation:,test\nStimulus:,S2\n'
               'LED pattern:,P3N3\nPresentation completed:,false\n'
               'Measured voltages (V):,No measurement\n')
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            path = Path(folder) / 'log.csv'
            path.write_text(log, encoding='utf-8-sig')
            trials = parse_dmts_log_file(path)
        self.assertEqual(len(trials), 1)
        self.assertEqual(trials[0]['trial_id'], 'abc')
        self.assertIsNone(trials[0]['test']['voltages'])
        self.assertFalse(trials[0]['test']['completed'])
        grid = voltages_to_pattern_grid(trials[0]['sample']['voltages'], trials[0]['sample']['pattern'])
        self.assertEqual(grid[0,0], 1)
        self.assertEqual(grid[1,1], 2)
        self.assertEqual(np.isfinite(grid).sum(), 2)

    def test_short_measurement(self):
        with self.assertRaises(ValueError):
            voltages_to_pattern_grid([1,2], ['P1N1'])

    def test_pools_sample_and_test_as_separate_presentations(self):
        def presentation(values):
            return dict(stimulus='STIM1', pattern=['P1N1'], voltages=values)
        groups = voltage_presentations_by_stim([
            dict(sample=presentation([1]*10), test=presentation([3]*10)),
            dict(test=presentation(None))])
        group = groups['STIM1']
        self.assertEqual(group['total'], 3)
        self.assertEqual(group['valid'], 2)
        self.assertEqual(group['positions']['P1N1'], [1,3])

if __name__ == '__main__':
    unittest.main()
