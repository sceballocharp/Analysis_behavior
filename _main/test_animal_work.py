"""Animal discovery and background batch regression checks, without Tk imports."""
from pathlib import Path
import queue
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from animal_work import scan_sessions, discovery_status, discovery_complete, batch_complete
from test_single_input_loading import method, variable
import test_gonogo_batch_async as batch_tests


class DiscoveryTests(unittest.TestCase):
    def collect(self, folder, kind='nwb', animal='', cancel=None):
        messages = queue.Queue()
        scan_sessions(folder, kind, animal, cancel or threading.Event(), messages)
        return list(messages.queue)

    def test_recursive_nwb_and_raw_folder_search(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as directory:
            root = Path(directory)
            session = root / 'M99' / 'session'
            session.mkdir(parents=True)
            (session / 'one.NWB').touch()
            (root / 'two.nwb').touch()
            for name in ['parameters.dat','TrialType.bin','TTLtrigsounds.bin','Trial_log.csv']:
                (session / name).touch()
            found = lambda events: [path for kind, data in events if kind == 'progress' for path in data[1]]
            self.assertEqual(set(found(self.collect(root))), {root/'two.nwb', session/'one.NWB'})
            self.assertEqual(found(self.collect(root, 'folder', 'm99')), [session])
            self.assertEqual(found(self.collect(root, 'folder', 'other')), [])
            self.assertEqual(found(self.collect(session, 'folder', 'M99')), [session])

    def test_empty_missing_and_cancelled_search(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as directory:
            events = self.collect(Path(directory))
            self.assertEqual(events[-1][0], 'done')
            self.assertEqual(events[0], ('progress', (1, [])))
            events = self.collect(Path(directory)/'missing')
            self.assertEqual([kind for kind, data in events], ['error', 'done'])
            cancel = threading.Event()
            cancel.set()
            self.assertEqual(self.collect(Path(directory), cancel=cancel), [('done', None)])

    def test_shared_status_messages(self):
        self.assertEqual(discovery_status(3, 2, 'nwb'), 'Scanning: 3 folders; 2 NWB files')
        self.assertIn('No NWB', discovery_complete(0, 'nwb'))
        self.assertIn('incomplete', discovery_complete(0, 'folder', 1))
        self.assertEqual(batch_complete(2, 1), 'Batch complete: 2 sessions; 1 skipped.')


class AnimalGuiTests(unittest.TestCase):
    def setUp(self):
        self.jobs, self.callbacks = [], []
        self.main = threading.get_ident()
        def thread(**kwargs):
            job = threading.Thread(**kwargs)
            self.jobs.append(job)
            return job
        self.ns = dict(Path=Path, queue=queue,
            threading=SimpleNamespace(Thread=thread, Event=threading.Event),
            scan_sessions=scan_sessions, discovery_status=discovery_status,
            discovery_complete=discovery_complete)
        self.root = SimpleNamespace(after=lambda ms, callback: (self.callbacks.append(callback), len(self.callbacks))[1],
                                    after_cancel=Mock())

    def ui(self, *args, **kwargs):
        self.assertEqual(threading.get_ident(), self.main)

    def finish(self):
        for job in self.jobs:
            job.join(5)
            self.assertFalse(job.is_alive())
        for _ in range(10):
            if not self.callbacks:
                return
            self.callbacks.pop(0)()
        self.fail('Search did not finish')

    def gonogo(self, folder, kind='nwb'):
        app = SimpleNamespace(root=self.root, _gonogo_search_generation=0,
            _gonogo_search_cancel=None, _gonogo_batch_generation=0,
            nwb_group_var=variable(), animal_var=variable(), status_var=variable(),
            current_folder_var=variable(), nwb_group_selector=Mock(),
            _write_output=Mock(side_effect=self.ui),
            _refresh_gonogo_animal_controls=Mock(side_effect=self.ui),
            _draw_selected_input_box=Mock(side_effect=self.ui))
        def reset():
            app._gonogo_search_generation += 1
            app._gonogo_batch_generation += 1
            if app._gonogo_search_cancel:
                app._gonogo_search_cancel.set()
            app.found_session_folders, app.found_nwb_files = [], []
        app._reset_session = reset
        app._group_nwb_files = lambda paths: ({'M99': paths}, []) if paths else ({}, [])
        run = method('behavior_gui_v10.py','_start_gonogo_animal_search', self.ns)
        run(app, folder, kind, 'M99')
        self.assertTrue(app.nwb_loading)
        return app

    def test_gonogo_scan_populates_animals_after_completion(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as directory:
            root = Path(directory)
            (root/'session.nwb').touch()
            app = self.gonogo(root)
            self.finish()
            self.assertFalse(app.nwb_loading)
            self.assertEqual(app.nwb_scanned_files, [root/'session.nwb'])
            self.assertIn('select an animal', app.status_var.get())
            self.assertFalse(app.found_nwb_files)  # Discovery does not start analysis.

    def test_gonogo_old_search_cannot_replace_new_selection(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as directory:
            app = self.gonogo(Path(directory))
            app._reset_session()
            app.status_var.set('new selection')
            self.finish()
            self.assertEqual(app.status_var.get(), 'new selection')

    def test_gonogo_empty_folder_search_clears_results(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as directory:
            app = self.gonogo(Path(directory), 'folder')
            self.finish()
            self.assertFalse(app.found_session_folders)
            self.assertIn('No session folder', app.status_var.get())

    def test_dmts_scan_completion_and_controls(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as directory:
            root = Path(directory)
            (root/'session.nwb').touch()
            app = SimpleNamespace(root=self.root, _dmts_batch_generation=0,
                _dmts_folder_scan_cancel=None, _dmts_folder_scan_poll=None,
                dmts_mouse_folder_var=variable(), dmts_scan_status_var=variable(),
                dmts_animal_output=Mock(), _refresh_dmts_animal_controls=Mock(side_effect=self.ui),
                _draw_dmts_canvas=Mock(side_effect=self.ui))
            method('dmts_gui.py','_start_dmts_folder_scan', self.ns)(app, root)
            self.assertIsNotNone(app._dmts_folder_scan_poll)
            self.finish()
            self.assertEqual(app.dmts_animal_nwb_files, [root/'session.nwb'])
            self.assertIsNone(app._dmts_folder_scan_poll)
            self.assertEqual(app.dmts_scan_status_var.get(), discovery_complete(1, 'nwb'))
            self.assertFalse(app._dmts_batch_running)
            self.assertFalse(app.dmts_batch_results)

    def test_dmts_previous_search_is_cancelled(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as directory:
            app = SimpleNamespace(root=self.root, _dmts_batch_generation=0,
                _dmts_folder_scan_cancel=None, _dmts_folder_scan_poll=None,
                dmts_mouse_folder_var=variable(), dmts_scan_status_var=variable(),
                dmts_animal_output=Mock(), _refresh_dmts_animal_controls=Mock(side_effect=self.ui),
                _draw_dmts_canvas=Mock(side_effect=self.ui))
            run = method('dmts_gui.py','_start_dmts_folder_scan', self.ns)
            run(app, Path(directory))
            old_cancel = app._dmts_folder_scan_cancel
            run(app, Path(directory)/'missing')
            self.assertTrue(old_cancel.is_set())
            self.finish()
            self.assertTrue(app.dmts_scan_status_var.get().startswith('Search failed:'))
            self.assertFalse(app.dmts_animal_nwb_files)

    def test_gonogo_search_buttons_disable_only_active_search(self):
        app = SimpleNamespace(nwb_loading=True, _gonogo_search_kind='folder',
            find_nwb_button=Mock(), find_folders_button=Mock(), nwb_group_selector=Mock())
        method('behavior_gui_v10.py','_refresh_gonogo_animal_controls', self.ns)(app)
        app.find_folders_button.configure.assert_called_with(text='Running...', state='disabled')
        app.find_nwb_button.configure.assert_called_with(text='Find NWB files', state='normal')
        app.nwb_group_selector.configure.assert_called_with(state='disabled')

    def test_dmts_search_control_disables_loading(self):
        app = SimpleNamespace(_dmts_folder_scan_poll='pending', _dmts_batch_running=False,
                              dmts_mouse_folder_button=Mock(), dmts_load_batch_button=Mock())
        run = method('dmts_gui.py','_refresh_dmts_animal_controls', self.ns)
        run(app)
        app.dmts_mouse_folder_button.configure.assert_called_with(text='Running...', state='disabled')
        app.dmts_load_batch_button.configure.assert_called_with(state='disabled')
        app._dmts_folder_scan_poll = None
        run(app)
        app.dmts_mouse_folder_button.configure.assert_called_with(text='Select mouse folder', state='normal')
        app.dmts_load_batch_button.configure.assert_called_with(state='normal')

    def test_raw_batch_uses_folder_loader_and_keeps_errors(self):
        case = batch_tests.BatchSchedulingTests()
        app, unused = case.make_app()
        # Extract with the scheduling fixture's namespace, replacing only the input loader.
        namespace = dict(queue=queue, threading=SimpleNamespace(Thread=lambda **kwargs: self.record_thread(**kwargs)))
        def load(path):
            self.assertNotEqual(threading.get_ident(), self.main)
            raise ValueError('invalid folder fixture')
        namespace['load_session_data_fromFolder'] = load
        method('behavior_gui_v10.py','_start_gonogo_animal_batch', namespace)(app, (Path('folder1'), Path('folder2')), 'folder')
        self.finish()
        # The fixture owns the UI callbacks.
        for callback in case.callbacks:
            callback()
        self.assertFalse(app._gonogo_batch_running)
        self.assertEqual(len(app._gonogo_batch_errors), 2)

    def test_successful_raw_batch_keeps_performance_and_trial_data(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest('NumPy unavailable in this Python runtime')
        case = batch_tests.BatchSchedulingTests()
        app, unused = case.make_app()
        class Results(dict):
            def __len__(self):
                return 2
        data = {'ResultsTable': Results(TrialType=[1,2], Hit=[1,0], CR=[0,1])}
        namespace = dict(queue=queue, np=np,
            threading=SimpleNamespace(Thread=lambda **kwargs: self.record_thread(**kwargs)),
            load_session_data_fromFolder=lambda path: data,
            extract_performance=lambda session: {'total': 100},
            session_start_time=lambda session: None,
            analyze_session_responses=lambda *args: (None,None,{}),
            _append_trials_by_sound_id=lambda *args: None,
            _merge_hit_by_sound=lambda *args: None)
        method('behavior_gui_v10.py','_start_gonogo_animal_batch',namespace)(app, (Path('folder1'),), 'folder')
        self.finish()
        for callback in case.callbacks:
            callback()
        self.assertFalse(app._gonogo_batch_running)
        self.assertEqual(app.batch_performance_by_file['folder1']['total'], 100)
        self.assertEqual(app.batch_trial_performance_by_file['folder1']['correct'].tolist(), [1,1])
        self.assertFalse(app._gonogo_batch_errors)

    def test_dmts_batch_progress_success_and_skip(self):
        def summarize(session, path, **settings):
            if path.name == 'bad.nwb':
                raise ValueError('invalid session')
            engagement = dict(n_periods=0, engaged_pct=100, unknown_eligible_trials=0,
                              silent_match_threshold=5, warning=None)
            return dict(file=str(path), total=100, engagement=engagement,
                        blank_response={side:dict(rate_pct=0, valid_trials=0)
                                        for side in ('any','left','right')})
        app = SimpleNamespace(root=self.root, _dmts_batch_running=False,
            dmts_animal_nwb_files=[Path('good.nwb'),Path('bad.nwb')],
            _dmts_folder_scan_poll=None, dmts_silent_match_var=variable('5'),
            _dmts_batch_generation=1, dmts_scan_status_var=variable(),
            _refresh_dmts_animal_controls=Mock(side_effect=self.ui),
            _draw_dmts_canvas=Mock(side_effect=self.ui),
            _write_dmts_animal_output=Mock(side_effect=self.ui))
        self.ns.update(load_session_data_fromFile=lambda path: {}, batch_complete=batch_complete)
        fake = SimpleNamespace(summarize_session=summarize, session_sort_key=lambda data:(0,data['file']))
        with patch.dict('sys.modules', {'dmts_batch':fake}):
            method('dmts_gui.py','_run_dmts_batch',self.ns)(app)
            self.assertTrue(app._dmts_batch_running)
            self.assertEqual(app.dmts_scan_status_var.get(), 'Analyzing 0/2 files')
            self.finish()
        self.assertFalse(app._dmts_batch_running)
        self.assertEqual(len(app.dmts_batch_results), 1)
        self.assertEqual(len(app.dmts_batch_errors), 1)
        self.assertEqual(app.dmts_scan_status_var.get(), batch_complete(1,1))

    def record_thread(self, **kwargs):
        job = threading.Thread(**kwargs)
        self.jobs.append(job)
        return job


if __name__ == '__main__':
    unittest.main()
