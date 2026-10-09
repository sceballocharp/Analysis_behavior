"""Regression checks for source-specific response analysis."""
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd

# Progress bars are unrelated to these tests and optional in the test environment.
try:
    import tqdm
except ImportError:
    sys.modules["tqdm"] = types.SimpleNamespace(tqdm=lambda iterable, **kwargs: iterable)

sys.path.insert(0, str(Path(__file__).resolve().parent))
import behavior_functions as behavior


class HitSourceTests(unittest.TestCase):
    def setUp(self):
        signal = np.zeros(5000)
        for start in [1150, 1250, 1350, 1450, 1550]:
            signal[start:start + 10] = 3
        markers = np.zeros(50)
        markers[[0, 10, 30]] = 99
        self.session = {
            "parameters": {},
            "dataIR": {"full": signal, "mean": signal.mean()},
            "trialID": {"full": markers},
            "nTotalTrials": 3,
            "ResultsTable": pd.DataFrame({"SoundId": [1, 2, 1]}),
        }

    def test_licks_count_signal_without_ir_analysis(self):
        with patch.object(behavior, "analyze_ir_by_trial", side_effect=AssertionError):
            events, analysis, hits = behavior.analyze_session_responses(self.session, "Licks")
        self.assertIsNone(events)
        self.assertIsNone(analysis)
        self.assertEqual(hits[2]["n_FAs"], 1)
        self.assertEqual(hits[2]["allTrialsAsGO"], [1])

    def test_licks_preserve_existing_window_and_counts(self):
        self.session["parameters"] = {"percIRFork": 50}
        events = behavior.detect_ir_events(self.session["dataIR"]["full"])
        legacy = behavior.extract_hit_by_sound_licks(
            self.session, behavior.analyze_ir_by_trial(self.session, events))
        self.assertEqual(behavior.analyze_session_responses(self.session, "Licks")[2], legacy)

    def test_ir_still_requires_percentage(self):
        with self.assertRaisesRegex(ValueError, "percIRFork"):
            behavior.analyze_session_responses(self.session, "IR")

    def test_ir_keeps_occupancy_results(self):
        self.session["parameters"] = {"percIRFork": 50}
        events, analysis, hits = behavior.analyze_session_responses(self.session, "IR")
        self.assertIsNotNone(events)
        self.assertEqual(analysis["stay_threshold_ms"], 500)

    def test_fewer_than_five_lick_events_is_not_a_hit(self):
        self.session["dataIR"]["full"][1550:1560] = 0
        hits = behavior.analyze_session_responses(self.session, "Licks")[2]
        self.assertEqual(hits[2]["n_FAs"], 0)
        self.assertEqual(hits[2]["allTrialsAsGO"], [0])

    def test_reported_nwb_through_gui_worker(self):
        path = (Path(__file__).resolve().parents[2] / "pyBEHAVIOR/data/Sebastian/"
                "behavior_data/M99/20260923/120259_Data/Sebastian_M99_120259_Data.nwb")
        if not path.exists():
            self.skipTest("Reported NWB fixture is not available on this machine")
        with patch.object(sys, "argv", ["behavior_gui_v8.py", "--nogui"]):
            import behavior_gui_v8 as gui
        app = gui.ScanMediaFoldersApp.__new__(gui.ScanMediaFoldersApp)
        app.scan_generation = 0
        app.root = types.SimpleNamespace(after=lambda delay, callback, *args: callback(*args))
        app._handle_scan_success = Mock()
        app._handle_scan_error = Mock()
        with patch.object(behavior, "analyze_ir_by_trial", side_effect=AssertionError):
            app._run_scan_worker(path, "Licks", 0)
        app._handle_scan_error.assert_not_called()
        app._handle_scan_success.assert_called_once()
        args = app._handle_scan_success.call_args.args
        self.assertEqual(args[1]["nTotalTrials"], 15)
        self.assertIsNone(args[-1])


if __name__ == "__main__":
    unittest.main()
