"""Exercise batch scheduling without requiring Tk, NWB, or SciPy."""
import ast
from pathlib import Path
import queue
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

SOURCE = Path(__file__).with_name('behavior_gui_v10.py')

class BatchSchedulingTests(unittest.TestCase):
    def make_app(self):
        tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'ScanMediaFoldersApp')
        method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '_start_gonogo_animal_batch')
        self.jobs = []
        self.callbacks = []
        self.loaded = []
        self.ui_thread = threading.get_ident()
        def load(path):
            self.loaded.append(path)
            self.assertNotEqual(threading.get_ident(), self.ui_thread)
            raise ValueError('broken NWB fixture')
        def check_ui(*args):
            self.assertEqual(threading.get_ident(), self.ui_thread)
        def thread(**kwargs):
            job = threading.Thread(**kwargs)
            self.jobs.append(job)
            return job
        ns = dict(queue=queue, threading=SimpleNamespace(Thread=thread), load_session_data_fromFile=load)
        exec(compile(ast.Module(body=[method], type_ignores=[]), str(SOURCE), 'exec'), ns)
        app = SimpleNamespace(_gonogo_batch_running=False, _gonogo_batch_generation=0, nwb_loading=False,
            found_nwb_files=[Path('bad1.nwb'), Path('bad2.nwb')],
            hit_source_var=SimpleNamespace(get=lambda: 'IR'),
            status_var=SimpleNamespace(set=Mock(side_effect=check_ui)),
            root=SimpleNamespace(after=lambda ms, cb: self.callbacks.append(cb)),
            _write_output=Mock(side_effect=check_ui), _draw_selected_input_box=Mock(side_effect=check_ui),
            _finish_gonogo_nwb_batch=Mock(side_effect=check_ui))
        return app, lambda app: ns['_start_gonogo_animal_batch'](app, tuple(app.found_nwb_files), 'nwb')

    def test_background_errors_progress_and_duplicate_click(self):
        app, run = self.make_app()
        run(app)
        self.assertTrue(app._gonogo_batch_running)
        run(app)
        self.assertEqual(len(self.jobs), 1)
        self.jobs[0].join(5)
        self.assertFalse(self.jobs[0].is_alive())
        self.assertEqual(len(self.loaded), 2)
        self.callbacks.pop(0)()
        self.assertFalse(app._gonogo_batch_running)
        app._finish_gonogo_nwb_batch.assert_called_once()
        statuses = [call.args[0] for call in app.status_var.set.call_args_list]
        self.assertTrue(any('Analyzing 2/2' in s for s in statuses))
        self.assertEqual(sum('ERROR:' in call.args[0] for call in app._write_output.call_args_list), 2)

    def test_previous_selection_results_are_ignored(self):
        app, run = self.make_app()
        run(app)
        self.jobs[0].join(5)
        app._gonogo_batch_generation += 1
        app.batch_performance_by_file = {'new selection': {}}
        self.callbacks.pop(0)()
        app._finish_gonogo_nwb_batch.assert_not_called()
        self.assertIn('new selection', app.batch_performance_by_file)

if __name__ == '__main__':
    unittest.main()
