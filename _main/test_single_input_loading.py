"""Test single-input loading without a display or optional plotting packages."""
import ast
from pathlib import Path
import queue
import threading
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


def method(filename, name, namespace):
    tree = ast.parse(Path(__file__).with_name(filename).read_text(encoding='utf-8'))
    node = next(n for c in tree.body if isinstance(c, ast.ClassDef)
                for n in c.body if isinstance(n, ast.FunctionDef) and n.name == name)
    node.decorator_list = []
    exec(compile(ast.Module(body=[node], type_ignores=[]), filename, 'exec'), namespace)
    return namespace[name]


def variable(value=''):
    state = SimpleNamespace(value=value)
    state.get = lambda: state.value
    state.set = lambda value: setattr(state, 'value', value)
    return state


class InputLoadingTests(unittest.TestCase):
    def setUp(self):
        self.callbacks, self.jobs = [], []
        self.main_thread = threading.get_ident()
        def thread(**kwargs):
            job = threading.Thread(**kwargs)
            self.jobs.append(job)
            return job
        self.ns = dict(Path=Path, queue=queue, threading=SimpleNamespace(Thread=thread),
                       messagebox=SimpleNamespace(showerror=Mock()))
        self.root = SimpleNamespace(after=lambda delay, callback: self.callbacks.append(callback))

    def ui(self, *args):
        self.assertEqual(threading.get_ident(), self.main_thread)

    def finish(self):
        for job in self.jobs:
            job.join(5)
            self.assertFalse(job.is_alive())
        for _ in range(10):
            if not self.callbacks:
                return
            self.callbacks.pop(0)()
        self.fail('Loading did not finish')

    def gonogo(self, source):
        def read(path):
            self.assertNotEqual(threading.get_ident(), self.main_thread)
            return source, 'fixture metadata'
        app = SimpleNamespace(root=self.root, scan_generation=1, hit_source_var=variable(),
            status_var=variable(), hit_source_status_var=variable(),
            _set_running_state=Mock(side_effect=self.ui), _read_nwb_hit_source=read,
            _write_output=Mock(side_effect=self.ui), _start_scan=Mock(side_effect=self.ui))
        run = method('behavior_gui_v10.py', '_detect_nwb_hit_source', self.ns)
        run(app, 'fixture.nwb')
        return app

    def test_gonogo_metadata_then_analysis(self):
        app = self.gonogo('Licks')
        self.finish()
        self.assertEqual(app.hit_source_var.get(), 'Licks')
        app._start_scan.assert_called_once()

    def test_gonogo_unknown_source_waits_for_user(self):
        app = self.gonogo(None)
        self.finish()
        app._start_scan.assert_not_called()
        self.assertIn('Choose IR or Licks', app.status_var.get())

    def test_gonogo_ignores_previous_selection(self):
        app = self.gonogo('IR')
        app.scan_generation += 1
        self.finish()
        app._start_scan.assert_not_called()

    def scan(self, target, kind, fail=False):
        def load(path):
            self.assertNotEqual(threading.get_ident(), self.main_thread)
            if fail:
                raise ValueError('invalid session')
            return {'session': str(path)}
        self.ns.update(load_session_data_fromFile=load, load_session_data_fromFolder=load,
                       extract_performance=lambda data: {'total': 100},
                       analyze_session_responses=lambda *args: (None, None, {}))
        worker = method('behavior_gui_v10.py', '_run_scan_worker', self.ns)
        app = SimpleNamespace(root=self.root, is_running=False, scan_generation=1,
            folder_var=variable(str(target) if kind == 'folder' else ''),
            file_var=variable(str(target) if kind == 'file' else ''), active_input=kind,
            hit_source_var=variable('Licks'), animal_var=variable(), status_var=variable(),
            _sync_current_input_label=Mock(side_effect=self.ui),
            _write_output=Mock(side_effect=self.ui),
            _handle_scan_success=Mock(side_effect=self.ui),
            _handle_scan_error=Mock(side_effect=self.ui))
        def running(value):
            self.ui()
            app.is_running = value
        app._set_running_state = running
        app._run_scan_worker = lambda *args: worker(app, *args)
        method('behavior_gui_v10.py', '_start_scan', self.ns)(app)
        self.assertTrue(app.is_running)
        return app

    def test_gonogo_folder_runs_in_background(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder:
            app = self.scan(Path(folder), 'folder')
            self.finish()
            app._handle_scan_success.assert_called_once()
            app._handle_scan_error.assert_not_called()
            self.assertEqual(app.status_var.get(), 'Analyzing session responses...')

    def test_gonogo_file_error_delivered_to_ui(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder:
            target = Path(folder) / 'fixture.nwb'
            target.touch()
            app = self.scan(target, 'file', fail=True)
            self.finish()
            app._handle_scan_error.assert_called_once()
            app._handle_scan_success.assert_not_called()

    def dmts(self, fail=False):
        def read(path):
            self.assertNotEqual(threading.get_ident(), self.main_thread)
            if fail:
                raise ValueError('invalid NWB')
            return {'dmts_summary'}
        self.ns['load_session_data_fromFile'] = lambda path: {'trials': [1]}
        app = SimpleNamespace(root=self.root, _dmts_file_busy=False, _dmts_file_generation=1,
            dmts_file_var=variable('fixture.nwb'), dmts_example_var=variable(),
            dmts_file_status_var=variable(), _dmts_file_actions=set(),
            dmts_trial_viewer_button=Mock(), _dmts_loaded=False,
            _write_dmts_file_output=Mock(side_effect=self.ui),
            _draw_dmts_canvas=Mock(side_effect=self.ui), _read_dmts_file_actions=read)
        method('dmts_gui.py', '_load_dmts_file', self.ns)(app)
        self.assertTrue(app._dmts_file_busy)
        return app

    def test_dmts_loads_and_enables_actions(self):
        app = self.dmts()
        self.finish()
        self.assertFalse(app._dmts_file_busy)
        self.assertTrue(app._dmts_loaded)
        self.assertEqual(app._dmts_file_actions, {'dmts_summary'})
        self.assertTrue(app.dmts_file_status_var.get().startswith('Done:'))

    def test_dmts_error_recovers(self):
        app = self.dmts(fail=True)
        self.finish()
        self.assertFalse(app._dmts_file_busy)
        self.assertFalse(app._dmts_loaded)
        self.assertEqual(app.dmts_file_status_var.get(), 'NWB loading failed')

    def test_dmts_ignores_previous_selection(self):
        app = self.dmts()
        app._dmts_file_generation += 1
        app.dmts_file_status_var.set('new selection')
        self.finish()
        self.assertFalse(app._dmts_loaded)
        self.assertEqual(app.dmts_file_status_var.get(), 'new selection')

    def lever(self, fail=False):
        def read(path):
            self.assertNotEqual(threading.get_ident(), self.main_thread)
            if fail:
                raise ValueError('invalid NWB')
            return dict(starts=[0], signals={}, label_defaults=('Go','Test'), timing_note='fixture', labels=['Go'])
        self.ns['load_lever_file'] = read
        app = SimpleNamespace(root=self.root, busy=False, filename=variable('fixture.nwb'), generation=1,
            viewer_button=Mock(), log=Mock(side_effect=self.ui), draw=Mock(side_effect=self.ui),
            status_var=variable(), channel_box=Mock(), channel=variable(), go_label=variable(), test_label=variable())
        method('lever_gui.py','load',self.ns)(app)
        self.assertTrue(app.busy)
        return app

    def test_lever_loads(self):
        app = self.lever()
        self.finish()
        self.assertFalse(app.busy)
        self.assertTrue(app.status_var.get().startswith('Done:'))
        self.assertEqual(app.data['starts'], [0])

    def test_lever_error_recovers(self):
        app = self.lever(fail=True)
        self.finish()
        self.assertFalse(app.busy)
        self.assertIsNone(app.data)
        self.assertEqual(app.status_var.get(), 'NWB loading failed')

    def test_lever_ignores_previous_selection(self):
        app = self.lever()
        app.generation += 1
        app.status_var.set('new selection')
        self.finish()
        self.assertEqual(app.status_var.get(), 'new selection')


if __name__ == '__main__':
    unittest.main()
