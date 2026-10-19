"""Experimental workflow canvases. Run this file; production v10 stays untouched.

Uses existing loading/analysis callbacks. Node positions and edges live below in
WorkflowApp, WorkflowDmtsPanel, and WorkflowLeverPanel for easy experimentation.
"""
from dataclasses import dataclass, field
from contextlib import contextmanager
from pathlib import Path
import argparse
import tkinter as tk
from tkinter import filedialog, messagebox

from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
import matplotlib.pyplot as plt

from behavior_gui_v10 import ScanMediaFoldersApp
from dmts_gui import DmtsPanel
from lever_gui import LeverPanel


COLORS = {
    'Waiting': ('#F1F3F5', '#C6CDD5', '#77818D'),
    'Ready': ('#FFFFFF', '#6289B1', '#233A52'),
    'Running': ('#E9F2FF', '#3478C8', '#195391'),
    'Completed': ('#EEF7F1', '#62A27B', '#306044'),
    'Failed': ('#FFF0EF', '#CB6A63', '#963E38'),
    'Needs rerun': ('#FFF7E6', '#C89A3C', '#8A641E'),
}


def yes():
    return True


def no():
    return False


def values(variables):
    return tuple((key, value.get()) for key, value in variables.items())


@dataclass
class Node:
    key: str
    label: str
    column: int
    row: int
    callback: object
    available: object = yes
    done: object = no
    busy: object = no
    settings: object = lambda: ()
    reason: str = 'Complete the connected input step first.'
    after: tuple = ()
    # Optional edges communicate configuration, without blocking execution.
    optional: tuple = ()


class Workflow:
    """Draw one graph and track its actions without replacing analysis code."""
    def __init__(self, root, ax, canvas, title, fingerprint, note=lambda: ''):
        self.root, self.ax, self.canvas = root, ax, canvas
        self.title, self.fingerprint, self.note = title, fingerprint, note
        self.nodes = {}
        self.records = {}
        self.input_key = None
        self.last_signature = None
        self.active = None
        self.details = 'Click a ready node to run it. Arrows show data dependencies.'
        self.canvas.mpl_connect('pick_event', self.on_pick)
        self.canvas.mpl_connect('resize_event', lambda event: self.refresh(force=True))
        self.job = root.after(120, self.tick)

    def configure(self, nodes):
        self.nodes = {node.key: node for node in nodes}
        self.refresh(force=True)

    def sync(self):
        current = self.fingerprint()
        if current != self.input_key:
            self.input_key = current
            self.records.clear()
            self.active = None
            self.details = 'Input changed. Previous execution states were cleared.'
        for key, record in self.records.items():
            if record['state'] in ('Completed', 'Failed') and key in self.nodes:
                if record['settings'] != self.nodes[key].settings():
                    record['state'] = 'Needs rerun'
        # Invalidate completed downstream outputs when an upstream step changes.
        for _ in self.nodes:
            for key, node in self.nodes.items():
                if key in self.records and self.records[key]['state'] == 'Completed':
                    if any(self.records.get(parent, {}).get('state') == 'Needs rerun' for parent in node.after):
                        self.records[key]['state'] = 'Needs rerun'

    def state(self, node):
        if node.busy():
            return 'Running'
        record = self.records.get(node.key)
        if record and record['state'] in ('Running', 'Failed', 'Needs rerun'):
            return record['state']
        if not node.available():
            return 'Waiting'
        if any(self.records.get(parent, {}).get('state') in ('Needs rerun', 'Running', 'Failed') for parent in node.after):
            return 'Waiting'
        if record:
            return record['state']
        return 'Completed' if node.done() else 'Ready'

    @contextmanager
    def observe_dialogs(self):
        """Catch handled errors/cancellation as well as raised exceptions.

        Hooks exist only for the duration of this test canvas action, and are
        restored in finally. Existing callbacks still display their own dialogs.
        """
        result = {'failed': None, 'cancelled': False, 'warning': None}
        originals = {}
        for name in ('showerror', 'showwarning', 'showinfo'):
            original = getattr(messagebox, name)
            originals[(messagebox, name)] = original
            def show(*args, _original=original, _name=name, **kwargs):
                detail = kwargs.get('message', args[1] if len(args) > 1 else '')
                if _name == 'showerror':
                    result['failed'] = str(detail)
                elif _name == 'showwarning':
                    result['warning'] = str(detail)
                else:
                    result['cancelled'] = True
                return _original(*args, **kwargs)
            setattr(messagebox, name, show)
        for name in ('askopenfilename', 'asksaveasfilename', 'askdirectory'):
            original = getattr(filedialog, name)
            originals[(filedialog, name)] = original
            def ask(*args, _original=original, **kwargs):
                answer = _original(*args, **kwargs)
                if not answer:
                    result['cancelled'] = True
                return answer
            setattr(filedialog, name, ask)
        try:
            yield result
        finally:
            for (module, name), original in originals.items():
                setattr(module, name, original)

    def run(self, key):
        self.sync()
        node = self.nodes[key]
        if self.active or self.state(node) == 'Waiting':
            self.details = node.reason if not self.active else 'An action is already running in this view.'
            self.refresh(force=True)
            return
        old = self.records.get(key)
        self.records[key] = dict(state='Running', settings=node.settings())
        self.active = key
        self.details = f'{node.label.replace(chr(10), " ")}: running...'
        self.refresh(force=True)
        self.root.update_idletasks()
        failed = None
        try:
            with self.observe_dialogs() as outcome:
                node.callback()
            failed = outcome['failed']
        except Exception as exc:
            outcome = {'cancelled': False, 'warning': None}
            failed = str(exc)
            messagebox.showerror('Workflow action failed', str(exc), parent=self.root)
        self.sync()
        # Browsing/loading another input deliberately resets the old graph.
        if self.active != key:
            self.refresh(force=True)
            return
        if failed:
            self.finish(key, 'Failed', failed)
        elif outcome['cancelled']:
            self.records.pop(key, None)
            if old:
                self.records[key] = old
            self.active = None
            self.details = 'Action cancelled; previous results were kept.'
        elif node.busy():
            self.details = 'Loading/analysis continues in the background.'
        else:
            self.finish(key, 'Completed', outcome['warning'] or 'Action finished.')
        self.refresh(force=True)

    def finish(self, key, state, detail):
        self.records[key]['state'] = state
        self.active = None
        self.details = detail

    def on_pick(self, event):
        key = event.artist.get_gid()
        if key in self.nodes:
            self.run(key)

    def tick(self):
        if not self.canvas.get_tk_widget().winfo_exists():
            return
        self.sync()
        if self.active:
            node = self.nodes[self.active]
            if not node.busy():
                success = node.done()
                self.finish(node.key, 'Completed' if success else 'Failed',
                            'Results are ready.' if success else 'No results were produced. See the activity log for details.')
        self.refresh()
        self.job = self.root.after(120, self.tick)

    def refresh(self, force=False):
        self.sync()
        states = {key: self.state(node) for key, node in self.nodes.items()}
        signature = (tuple(states.items()), self.details, self.note(), self.title)
        if signature == self.last_signature and not force:
            return
        self.last_signature = signature
        ax = self.ax
        ax.clear()
        ax.set_facecolor('#F7F9FC')
        ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis('off')
        ax.text(.025, .97, self.title, fontsize=13, weight='bold', color='#233A52', va='top', transform=ax.transAxes)
        note = self.note()
        ax.text(.025, .91, str(note)[:105], fontsize=8, color='#657587', va='top', transform=ax.transAxes)
        width, height = .205, .105
        positions = {key: (.025 + node.column * .245, .76 - node.row * .135) for key, node in self.nodes.items()}
        for key, node in self.nodes.items():
            x, y = positions[key]
            for parent in (*node.after, *node.optional):
                if parent not in positions:
                    continue
                px, py = positions[parent]
                optional = parent in node.optional
                edge = FancyArrowPatch((px+width, py+height/2), (x, y+height/2),
                                       arrowstyle='-|>', mutation_scale=10,
                                       connectionstyle='arc3,rad=0.06',
                                       color='#A7B5C5', linewidth=1.1,
                                       linestyle='--' if optional else '-',
                                       transform=ax.transAxes, zorder=1)
                ax.add_patch(edge)
        for key, node in self.nodes.items():
            state = states[key]
            face, border, text = COLORS[state]
            x, y = positions[key]
            box = FancyBboxPatch((x, y), width, height,
                                 boxstyle='round,pad=0.006,rounding_size=0.012',
                                 facecolor=face, edgecolor=border, linewidth=1.4,
                                 transform=ax.transAxes, picker=True, zorder=3)
            box.set_gid(key)
            ax.add_patch(box)
            ax.text(x+.012, y+height-.018, node.label, fontsize=8, weight='bold',
                    va='top', color=text, transform=ax.transAxes, zorder=4)
            ax.text(x+.012, y+.012, state, fontsize=7, color=text, va='bottom', transform=ax.transAxes, zorder=4)
        ax.text(.025, .065, self.details[:145], fontsize=8, color='#526476', transform=ax.transAxes, wrap=True)
        ax.text(.025, .025, 'Waiting   /   Ready   /   Running   /   Completed   /   Failed   /   Needs rerun',
                fontsize=7, color='#657587', transform=ax.transAxes)
        self.canvas.draw_idle()


class WorkflowDmtsPanel(DmtsPanel):
    def __init__(self, app):
        self.flows = {}
        super().__init__(app)
        self.canvas.mpl_disconnect(self.canvas.callbacks.callbacks.get('pick_event', {}) and
                                   next(iter(self.canvas.callbacks.callbacks['pick_event'])) or 0)
        # The production pick handler ignores the test node IDs (wf_*).
        self._draw_dmts_canvas()

    def _draw_dmts_canvas(self):
        if not hasattr(self, 'canvas'):
            return
        page = self.dmts_file_notebook.select()
        if page == str(self.dmts_animal_tab):
            mode = 'Animal'
            fingerprint = lambda: (self.dmts_mouse_folder_var.get(), tuple(map(str, self.dmts_animal_nwb_files)))
            note = lambda: self.dmts_scan_status_var.get()
        elif page == str(self.dmts_groups_tab):
            mode = 'Groups'
            fingerprint = lambda: tuple(self.dmts_group_exports)
            note = lambda: self.dmts_group_folder_var.get()
        else:
            mode = 'File'
            fingerprint = lambda: self.dmts_file_var.get()
            note = lambda: Path(self.dmts_file_var.get()).name or 'Choose an NWB file to start.'
        if mode not in self.flows:
            self.flows[mode] = Workflow(self.root, self.canvas_ax, self.canvas, 'DMTS / '+mode, fingerprint, note)
        flow = self.flows[mode]
        # Only the visible subtab receives canvas picks.
        for name, other in self.flows.items():
            other.visible = name == mode
        if mode == 'File':
            selected = lambda: bool(self.dmts_file_var.get())
            loaded = lambda: self._dmts_loaded
            supported = lambda action: loaded() and action in self._dmts_file_actions and not self._dmts_file_busy
            origin = 'wf_time' if getattr(self, '_dmts_export_kind', '') == 'pretraining' else 'wf_aligned'
            nodes = [
                Node('wf_input','Choose NWB',0,0,self._browse_dmts_nwb,done=selected),
                Node('wf_load','Load NWB',1,0,self._load_dmts_file,selected,loaded,lambda:self._dmts_file_busy,after=('wf_input',)),
                Node('wf_raw','Session rawdata',2,0,self._open_dmts_summary,lambda:supported('dmts_summary'),after=('wf_load',)),
                Node('wf_time','Plot time window',2,1,self._run_dmts_pretraining,lambda:supported('dmts_pretraining'),settings=lambda:values(self.pretraining_vars),after=('wf_load',)),
                Node('wf_aligned','Trial-aligned licks',2,2,self._run_dmts_matchonly,lambda:supported('dmts_matchonly'),settings=lambda:values(self.matchonly_vars),after=('wf_load',)),
                Node('wf_examples','Trial examples',2,3,self._open_dmts_trial_examples,lambda:supported('dmts_trial_examples'),after=('wf_load',)),
                Node('wf_perf','Performance / StimID',2,4,self._open_dmts_sound_performance,lambda:supported('dmts_sound_performance'),after=('wf_load',)),
                Node('wf_export','Export results',3,2,self._export_dmts_file_results,lambda:self._dmts_export_ready and not self._dmts_file_busy,after=(origin,)),
                Node('wf_csv','Load voltage CSV',0,3,self._load_dmts_csv,lambda:bool(self._dmts_voltage_logs()),lambda:bool(getattr(self,'_dmts_csv_trials',None))),
                Node('wf_voltage','Voltage / StimID',1,3,self._open_dmts_csv_average,lambda:bool(getattr(self,'_dmts_csv_trials',None)),after=('wf_csv',)),
            ]
        elif mode == 'Animal':
            found = lambda: len(self.dmts_animal_nwb_files)>1 and self._dmts_folder_scan_poll is None
            results = lambda: bool(self.dmts_batch_results) and not self._dmts_batch_running
            nodes = [
                Node('wf_folder','Choose mouse folder',0,0,self._browse_dmts_mouse_folder,done=found),
                Node('wf_pkl','Load batch PKL',0,2,self._load_dmts_batch,done=results),
                Node('wf_batch','Run batch analysis',1,0,self._run_dmts_batch,found,results,lambda:self._dmts_batch_running,settings=lambda:self.dmts_silent_match_var.get(),after=('wf_folder',)),
                Node('wf_batch_plot','Session performance',2,0,self._plot_dmts_batch,results,settings=lambda:self.dmts_show_engaged_var.get(),after=('wf_batch',),optional=('wf_pkl',)),
                Node('wf_batch_hit','Hit / StimID',2,1,self._plot_dmts_batch_stim_hit,results,after=('wf_batch',),optional=('wf_pkl',)),
                Node('wf_batch_save','Save batch PKL',3,0,self._save_dmts_batch,results,after=('wf_batch',),optional=('wf_pkl',)),
            ]
        else:
            loaded = lambda: bool(self.dmts_group_exports)
            nodes = [
                Node('wf_groups','Load PKL folder',0,0,self._load_dmts_groups,done=loaded),
                Node('wf_assign','Assign selected files',1,1,self._assign_dmts_group,lambda:loaded() and bool(self.dmts_group_table.selection()),after=('wf_groups',)),
                Node('wf_group_plot','Plot group averages',2,0,self._plot_dmts_groups,loaded,settings=lambda:(tuple(sorted(self.dmts_group_assignments.items())),self.dmts_groups_engaged_var.get()),after=('wf_groups',),optional=('wf_assign',)),
            ]
        flow.configure(nodes)


class WorkflowLeverPanel(LeverPanel):
    def __init__(self, app):
        self.flow = None
        super().__init__(app)

    def draw(self):
        if not hasattr(self, 'canvas'):
            return
        if self.flow is None:
            self.flow = Workflow(self.root,self.ax,self.canvas,'Lever / File',lambda:self.filename.get(),lambda:Path(self.filename.get()).name or 'Choose an NWB file to start.')
        loaded = lambda: self.data is not None and not self.busy
        trial_ready = lambda: loaded() and len(self.data['starts'])>0 and bool(self.channel.get())
        crossing = lambda: loaded() and bool(__import__('numpy').any(__import__('numpy').isfinite(self.data.get('events',{}).get('crossing_duration_s',[]))))
        settings = lambda: tuple(variable.get() for variable in (self.channel,self.go_label,self.test_label,self.window_s,self.cmap_name,self.cmap_min,self.cmap_max))
        self.flow.configure([
            Node('wf_lever_input','Choose NWB',0,0,self.browse,done=lambda:bool(self.filename.get())),
            Node('wf_lever_load','Load NWB',1,0,self.load,lambda:bool(self.filename.get()),loaded,lambda:self.busy,after=('wf_lever_input',)),
            Node('wf_lever_plot','Lever across trials',2,0,self.open_plot,trial_ready,settings=settings,after=('wf_lever_load',)),
            Node('wf_lever_cross','Crossing distribution',2,1,lambda:self.open_plot(distribution=True),crossing,settings=lambda:(self.go_label.get(),self.test_label.get()),after=('wf_lever_load',)),
            Node('wf_lever_view','Trial viewer',2,2,self.open_viewer,lambda:loaded() and len(self.data['starts'])>0,after=('wf_lever_load',)),
        ])


class WorkflowApp(ScanMediaFoldersApp):
    def __init__(self, root, **kwargs):
        self.flows = {}
        super().__init__(root, **kwargs)
        self.root.title('BEHAVIOR — Workflow layout TEST')
        # Guide preference changes in this experiment cannot overwrite v10 prefs.
        self.guide_settings_path = Path(__file__).with_name('test_layout_preferences.json')
        self._draw_selected_input_box()

    def _build_ui(self):
        self._build_menu()
        self._build_main_tabs()
        controls, right, inputs, animal, groups = self._build_gonogo_layout()
        self._build_gonogo_groups_controls(groups)
        self._build_gonogo_input_controls(inputs)
        self._build_gonogo_animal_controls(animal)
        self._build_gonogo_output(controls)
        self._build_gonogo_canvas(right)
        self.dmts = WorkflowDmtsPanel(self)
        self.lever = WorkflowLeverPanel(self)
        self._lever_initial_split_pending = True
        self._configure_layout_reporting(controls,right)

    def _draw_selected_input_box(self):
        if self.main_canvas is None:
            return
        selected = self.notebook.select()
        if selected == str(self.animal_tab):
            mode='Animal'
            fingerprint=lambda:(tuple(map(str,self.found_nwb_files)),tuple(map(str,self.found_session_folders)))
        elif selected == str(self.groups_tab):
            mode='Groups'
            fingerprint=lambda:tuple(self.group_exports)
        else:
            mode='File'
            fingerprint=lambda:(self.active_input,self.file_var.get(),self.folder_var.get())
        if mode not in self.flows:
            self.flows[mode]=Workflow(self.root,self.main_canvas_ax,self.main_canvas,'Go/noGo / '+mode,fingerprint,lambda:self.status_var.get())
        flow=self.flows[mode]
        for name,other in self.flows.items():
            other.visible=name==mode
        if mode=='File':
            selected_input=lambda:self._single_input_selected
            loaded=lambda:hasattr(self,'single_session_datadict') and not self.is_running
            nodes=[
                Node('wf_go_input','Choose NWB',0,0,self._browse_nwb,done=lambda:selected_input() and self.active_input=='file'),
                Node('wf_go_folder','Choose folder',0,2,self._browse_folder,done=lambda:selected_input() and self.active_input=='folder'),
                Node('wf_go_run','Load + analyze',1,0,self._start_scan,lambda:selected_input() and self.hit_source_var.get() in ('IR','Licks'),loaded,lambda:self.is_running,settings=lambda:self.hit_source_var.get(),after=('wf_go_input',),optional=('wf_go_folder',)),
                Node('wf_go_perf','Performance',2,0,self._open_performance_plot,loaded,after=('wf_go_run',)),
                Node('wf_go_hit','Hit by sound',2,1,self._open_hit_by_sound_plot,loaded,after=('wf_go_run',)),
                Node('wf_go_ir','IR occupancy',2,2,self._open_ir_occupancy_plot,lambda:loaded() and self.single_session_trial_ir_analysis is not None,after=('wf_go_run',)),
                Node('wf_go_trials','Trial viewer',2,3,self._open_trial_viewer,loaded,after=('wf_go_run',)),
                Node('wf_go_vars','Session variables',2,4,self._open_session_console,loaded,after=('wf_go_run',)),
            ]
        elif mode=='Animal':
            found=lambda:bool(self.found_nwb_files or self.found_session_folders)
            results=lambda:bool(self.batch_performance_by_file)
            run=lambda:self._run_all_found_nwb_files() if self.active_input=='file' else self._run_all_found_session_folders()
            nodes=[
                Node('wf_find_nwb','Find NWB files',0,0,self._find_nwb_files_for_animal,done=lambda:bool(self.found_nwb_files)),
                Node('wf_find_folders','Find folders',0,2,self._find_session_folders_for_animal,done=lambda:bool(self.found_session_folders)),
                Node('wf_go_batch','Analyze all sessions',1,0,run,found,results,settings=lambda:self.hit_source_var.get(),after=('wf_find_nwb',),optional=('wf_find_folders',)),
                Node('wf_go_batch_plot','Batch performance',2,0,self._open_batch_session_performance_plot,results,after=('wf_go_batch',)),
                Node('wf_go_batch_save','Export batch PKL',3,0,self._export_batch_data,results,after=('wf_go_batch',)),
            ]
        else:
            loaded=lambda:bool(self.group_exports) and not self.groups_loading
            nodes=[
                Node('wf_go_groups','Load PKL folder',0,0,self._load_group_folder,done=loaded,busy=lambda:self.groups_loading),
                Node('wf_go_assign','Assign selected files',1,1,self._assign_selected_group,lambda:loaded() and bool(self.group_file_list.selection()),after=('wf_go_groups',)),
                Node('wf_go_groups_plot','Plot group averages',2,0,self._open_group_average_plot,lambda:loaded() and bool(self.group_assignments),settings=lambda:tuple(sorted(self.group_assignments.items())),after=('wf_go_groups',),optional=('wf_go_assign',)),
            ]
        flow.configure(nodes)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder',default='')
    parser.add_argument('--file',default='')
    args=parser.parse_args()
    root=tk.Tk()
    WorkflowApp(root,initial_folder=args.folder,initial_file=args.file)
    root.mainloop()


if __name__=='__main__':
    main()
