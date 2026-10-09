"""LED identity selection must not turn light matches into blank trials."""
import tempfile
import unittest
from pathlib import Path
import h5py
import numpy as np
from nwb_obj import session_data_nwb


class LEDReaderTests(unittest.TestCase):
    def read(self, source, include_light=True):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            path = Path(folder) / 'session.nwb'
            with h5py.File(path, 'w') as f:
                p = f.create_group('acquisition/Parameters')
                p['key'] = [b'DMTSStimulusSource']
                p['value'] = [source.encode()]
                t = f.create_group('intervals/trials')
                for key, values in dict(id=[1, 2], sound_ids=[0, 0],
                                        sample_sound_ids=[0, 0], test_sound_ids=[0, 0],
                                        trial_type=[0, 1], HMCF=[b'', b'Hit']).items():
                    t[key] = values
                if include_light:
                    t['sample_light_id'] = [0, 3]
                    t['test_light_id'] = [0, 3]
                t['dmts_light_confirmed'] = [1, 1]
            reader = session_data_nwb(nwbfile=path)
            reader.generate_results_table()
            return reader.results_table

    def test_led_uses_light_ids_and_preserves_metadata(self):
        table = self.read('LED')
        np.testing.assert_array_equal(table.SampleSoundId, [0, 3])
        np.testing.assert_array_equal(table.TestSoundId, [0, 3])
        np.testing.assert_array_equal(table.SoundId, [0, 3])
        self.assertTrue((table.dmts_light_confirmed == 1).all())

    def test_sound_keeps_sound_ids(self):
        np.testing.assert_array_equal(self.read('Sound').SampleSoundId, [0, 0])

    def test_missing_led_ids_fails_explicitly(self):
        with self.assertRaisesRegex(ValueError, 'sample_light_id'):
            self.read('LED', include_light=False)


if __name__ == '__main__':
    unittest.main()
