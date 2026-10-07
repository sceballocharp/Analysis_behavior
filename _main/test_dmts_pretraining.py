import io
import unittest

import h5py
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from dmts_pretraining import plot_pretraining, trailing_average


class PretrainingTests(unittest.TestCase):
    def setUp(self):
        self.path = io.BytesIO()
        with h5py.File(self.path, "w") as handle:
            acquisition = handle.create_group("acquisition")
            for name, data in (
                ("LeftLick", [0, 2, 2, 0, 2, 0]),
                ("RightLick", [0, 0, 0, 2, 2, 0]),
                ("Reward", [0, 0, 0, 1, 1, 0]),
            ):
                group = acquisition.create_group(name)
                dataset = group.create_dataset("data", data=data)
                dataset.attrs["conversion"] = 0.5
                dataset.attrs["offset"] = 0.1
                # Reward and left use timestamps; right uses regular sampling.
                if name != "RightLick":
                    group.create_dataset("timestamps", data=np.arange(6, dtype=float))
                else:
                    start = group.create_dataset("starting_time", data=0.0)
                    start.attrs["rate"] = 1.0

    def tearDown(self):
        plt.close("all")
        self.path.close()

    def test_scaled_crossings_detected_before_crop(self):
        figure, times = plot_pretraining(self.path, 2, 5)
        np.testing.assert_array_equal(times["LeftLick"], [4])
        np.testing.assert_array_equal(times["RightLick"], [3])
        np.testing.assert_allclose(figure.axes[0].lines[0].get_ydata(), [1.1, 0.1, 1.1, 0.1])
        np.testing.assert_allclose(figure.axes[0].lines[-1].get_ydata(), [0.1, 0.6, 0.6, 0.1])

    def test_causal_smoothing(self):
        np.testing.assert_allclose(trailing_average(np.array([2., 0., 4.]), 2), [2, 1, 2])
        _, times = plot_pretraining(self.path, 0, 5, smooth_ms=2000)
        np.testing.assert_array_equal(times["LeftLick"], [2])
        np.testing.assert_array_equal(times["RightLick"], [4])

    def test_reward_regular_sampling(self):
        with h5py.File(self.path, "a") as handle:
            reward = handle["acquisition/Reward"]
            del reward["timestamps"]
            start = reward.create_dataset("starting_time", data=0.0)
            start.attrs["rate"] = 1.0
        figure, _ = plot_pretraining(self.path, 0, 5)
        np.testing.assert_array_equal(figure.axes[0].lines[-1].get_xdata(), np.arange(6))

    def test_invalid_parameters_and_empty_window(self):
        for settings in ({"t_start": 5, "t_end": 5}, {"smooth_ms": -1},
                         {"threshold_v": float("nan")}, {"t_start": 50, "t_end": 60}):
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                plot_pretraining(self.path, **settings)

    def test_bad_signal_timestamps(self):
        with h5py.File(self.path, "a") as handle:
            handle["acquisition/LeftLick/timestamps"][2] = 1
        with self.assertRaisesRegex(ValueError, "strictly increasing"):
            plot_pretraining(self.path, 0, 5)


if __name__ == "__main__":
    unittest.main()
