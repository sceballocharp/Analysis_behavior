"""Independent Lever NWB loading and trial inspection for GUI v10."""
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import h5py
import numpy as np
from matplotlib import colormaps
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk


def load_lever_file(filename):
    signals = {}
    with h5py.File(filename, "r") as handle:
        parameters = {}
        if 'acquisition/Parameters/key' in handle:
            group = handle['acquisition/Parameters']
            parameters = dict(zip(group['key'].asstr()[:], group['value'].asstr()[:]))
        for parent in ("acquisition", "stimulus/presentation"):
            if parent not in handle:
                continue
            for name, group in handle[parent].items():
                if not isinstance(group, h5py.Group) or "data" not in group:
                    continue
                if not any(word in name.lower() for word in ("behaviorsignal", "irfork", "lever", "force", "position", "reward", "whichsound", "trialtype", "lick")):
                    continue
                dataset = group["data"]
                if dataset.dtype.kind not in "biuf":
                    continue
                values = np.asarray(dataset, dtype=float).squeeze()
                if values.ndim != 1 or not len(values):
                    continue
                if "timestamps" in group:
                    times = np.asarray(group["timestamps"], dtype=float)
                elif "starting_time" in group:
                    rate = float(group["starting_time"].attrs["rate"])
                    if not np.isfinite(rate) or rate <= 0:
                        raise ValueError(f"{name}: invalid sample rate")
                    times = float(group["starting_time"][()]) + np.arange(len(values))/rate
                else:
                    continue
                if times.ndim != 1 or len(times) != len(values) or not np.isfinite(times).all() or np.any(np.diff(times) <= 0):
                    raise ValueError(f"{name}: invalid timing")
                values = values*float(dataset.attrs.get("conversion", 1)) + float(dataset.attrs.get("offset", 0))
                unit = dataset.attrs.get("unit", "")
                if isinstance(unit, bytes):
                    unit = unit.decode("utf-8")
                signals[name] = (times, values, str(unit))
        if not signals:
            raise ValueError("No supported lever/force/position, lick, reward or stimulus signals found.")
        trials = handle.get("intervals/trials")
        timing_note = 'Trial start/stop times from intervals/trials.'
        if trials is not None and "start_time" in trials:
            starts = np.asarray(trials["start_time"], dtype=float)
            stops = np.asarray(trials["stop_time"], dtype=float) if "stop_time" in trials else None
        elif "TrialType" in signals:
            times, values, _ = signals["TrialType"]
            active = values == 99
            starts = times[active & ~np.r_[False, active[:-1]]]
            stops = None
            timing_note = ('Trial anchors from TrialType markers (100 ms resolution in this format); '
                           'display extends to the next anchor, including the inter-trial interval.')
        else:
            starts, stops = np.array([]), None
        if starts.ndim != 1 or not np.isfinite(starts).all() or np.any(np.diff(starts) <= 0):
            raise ValueError("Invalid trial start times")
        if stops is None:
            stops = np.r_[starts[1:], max(s[0][-1] for s in signals.values())] if len(starts) else np.array([])
        if stops.shape != starts.shape or not np.isfinite(stops).all() or np.any(stops <= starts):
            raise ValueError("Invalid trial stop times")
        labels = np.full(len(starts), "", dtype=object)
        if trials is not None and "trial_type" in trials:
            labels = np.asarray([v.decode() if isinstance(v, bytes) else str(v)
                                 for v in trials["trial_type"][:]])
            if labels.shape != starts.shape:
                raise ValueError("Trial types do not match trial start times")
        label_defaults = ('Go', 'Test')
        # Infer codes from the recorded sound IDs and task parameters, not from
        # generic Go/noGo numeric conventions.
        if parameters.get('TaskType', '').casefold() == 'lever' and trials is not None and 'sound_ids' in trials:
            sounds = np.asarray(trials['sound_ids'])
            inferred = []
            for key in ('GoSoundId', 'LeverTestSoundId'):
                try:
                    matches = np.unique(labels[sounds == int(parameters[key])])
                    inferred.append(str(matches[0]) if len(matches) == 1 else None)
                except (KeyError, ValueError):
                    inferred.append(None)
            if all(inferred) and inferred[0] != inferred[1]:
                label_defaults = tuple(inferred)
    return dict(signals=signals, starts=starts, stops=stops, labels=labels,
                parameters=parameters, label_defaults=label_defaults, timing_note=timing_note)


def lever_mean_sem(matrix):
    """Across-trial mean and sample SEM at each time; missing samples excluded."""
    valid = np.isfinite(matrix)
    n = valid.sum(axis=0)
    mean = np.divide(np.where(valid, matrix, 0).sum(axis=0), n,
                     out=np.full(matrix.shape[1], np.nan), where=n > 0)
    squared = np.where(valid, matrix - mean, 0) ** 2
    sem = np.sqrt(np.divide(squared.sum(axis=0), n * (n - 1),
                           out=np.full(matrix.shape[1], np.nan), where=n > 1))
    return mean, sem


def plot_lever_trials(data, channel, go_label="Go", test_label="Test", plot_layout=None, window_s=None):
    """Plot recorded signal, preserving trial order and masking outside each trial."""
    labels = np.asarray([str(v).strip().casefold() for v in data['labels']])
    go_label, test_label = go_label.strip().casefold(), test_label.strip().casefold()
    if not go_label or not test_label or go_label == test_label:
        raise ValueError("Enter two different recorded trial labels for GO and Test.")
    groups = [np.flatnonzero(labels == label) for label in (go_label, test_label)]
    if not any(len(indices) for indices in groups):
        available = ', '.join(sorted(set(labels))) or '(missing trial_type)'
        raise ValueError(f"No matching GO or Test trials. Recorded labels: {available}")
    times, values, unit = data['signals'][channel]
    duration = float(np.max(data['stops'] - data['starts']))
    if window_s is not None:
        duration = float(window_s)
        if not np.isfinite(duration) or duration <= 0:
            raise ValueError('Plot window must be a positive number of seconds.')
    # Bound display resolution; use step sampling rather than interpolating edges.
    count = min(1500, max(2, int(np.ceil(duration / np.median(np.diff(times))))))
    edges = np.linspace(0, duration, count + 1)
    relative = (edges[:-1] + edges[1:]) / 2
    finite = values[np.isfinite(values)]
    if not len(finite):
        raise ValueError(f"{channel} has no finite signal values")
    low, high = float(finite.min()), float(finite.max())
    if low == high:
        high = low + 1
    layout = plot_layout or {}
    dpi = float(layout.get('dpi', 100))
    figure = Figure(figsize=(3 * float(layout.get('subplot_width_px', 500)) / dpi,
                              2 * float(layout.get('subplot_height_px', 400)) / dpi),
                     dpi=dpi, constrained_layout=True)
    grid = figure.add_gridspec(2, 3)
    axes = [figure.add_subplot(grid[:, 0]), figure.add_subplot(grid[:, 1])]
    averages = [figure.add_subplot(grid[0, 2]), figure.add_subplot(grid[1, 2])]
    from matplotlib.colors import TwoSlopeNorm
    radius = max(abs(low - 2.5), abs(high - 2.5), 0.001)
    norm = TwoSlopeNorm(vmin=2.5-radius, vcenter=2.5, vmax=2.5+radius)
    cmap = colormaps['seismic'].with_extremes(bad='#eeeeee')
    for ax, avg_ax, indices, title in zip(axes, averages, groups, ('GO', 'Test')):
        avg_ax.set(title=f'{title}: mean ± SEM', xlabel='Time from trial start (s)',
                   ylabel=f'{channel} ({unit})' if unit else channel,
                   xlim=(0, duration), ylim=(low, high))
        avg_ax.grid(alpha=.2)
        ax.set(title=f'{title} ({len(indices)} trials)', xlabel='Time from trial start (s)',
               ylabel='Session trial number', xlim=(0, duration))
        if not len(indices):
            ax.text(.5, .5, 'No matching trials', ha='center', transform=ax.transAxes)
            avg_ax.text(.5, .5, 'No matching trials', ha='center', transform=avg_ax.transAxes)
            continue
        matrix = np.full((len(indices), count), np.nan)
        for row, trial in enumerate(indices):
            target = data['starts'][trial] + relative
            positions = np.searchsorted(times, target, side='right') - 1
            valid = ((positions >= 0) & (target <= times[-1]) &
                     (target < data['stops'][trial]))
            matrix[row, valid] = values[positions[valid]]
        mean, sem = lever_mean_sem(matrix)
        avg_ax.fill_between(relative, mean-sem, mean+sem, color='black', alpha=.2,
                            linewidth=0, label='SEM')
        avg_ax.plot(relative, mean, color='black', linewidth=2.5, label='Mean')
        avg_ax.legend(loc='upper right', fontsize=8)
        ax.pcolormesh(edges, np.arange(len(indices)+1), matrix,
                      cmap=cmap, norm=norm, shading='flat', rasterized=True)
        ax.set_ylim(len(indices), 0)
        ticks = np.unique(np.linspace(0, len(indices)-1, min(10, len(indices))).astype(int))
        ax.set_yticks(ticks+.5, (indices[ticks]+1).astype(str))
    from matplotlib.cm import ScalarMappable
    figure.colorbar(ScalarMappable(norm=norm, cmap=cmap), ax=axes,
                    label=f'{channel} ({unit})' if unit else channel)
    figure.suptitle('Lever signal across trials')
    return figure


class LeverPanel:
    def __init__(self, app):
        self.app = app
        self.root = app.root
        self.tab = ttk.Frame(app.main_notebook)
        app.main_notebook.add(self.tab, text="Lever")
        notebook = ttk.Notebook(self.tab, height=0)
        notebook.pack(fill="x")
        notebook.add(ttk.Frame(notebook), text="File")
        self.split = ttk.Panedwindow(self.tab, orient="horizontal")
        self.split.pack(fill="both", expand=True)
        left = ttk.Frame(self.split, padding=(10, 8, 10, 0))
        right = ttk.Frame(self.split, padding=(10, 8, 0, 0))
        self.split.add(left, weight=1)
        self.split.add(right, weight=3)
        self.filename = tk.StringVar()
        self.data = None
        self.busy = False
        self.generation = 0
        self.viewer = None
        ttk.Button(left, text="Browse NWB", command=self.browse).pack(fill="x")
        self.viewer_button = ttk.Button(left, text="Trial Viewer", state="disabled", command=self.open_viewer)
        self.viewer_button.pack(fill="x", pady=6)
        ttk.Label(left, textvariable=self.filename, wraplength=300).pack(anchor="w")
        settings = ttk.LabelFrame(left, text="Lever plot", padding=6)
        settings.pack(fill="x", pady=8)
        self.channel = tk.StringVar()
        self.channel_box = ttk.Combobox(settings, textvariable=self.channel, state="readonly")
        self.channel_box.pack(fill="x")
        self.go_label = tk.StringVar(value="Go")
        self.test_label = tk.StringVar(value="Test")
        self.window_s = tk.StringVar(value="5")
        for text, variable in (("GO trial label", self.go_label), ("Test trial label", self.test_label),
                               ("Plot window (s)", self.window_s)):
            row = ttk.Frame(settings)
            row.pack(fill="x", pady=2)
            ttk.Label(row, text=text).pack(side="left")
            ttk.Entry(row, textvariable=variable, width=10).pack(side="right")
        ttk.Label(left, text="Output").pack(anchor="w", pady=(10, 4))
        self.output = scrolledtext.ScrolledText(left, width=32, height=8, wrap="word", state="disabled")
        self.output.pack(fill="both", expand=True)
        ttk.Label(right, text="Plot").pack(anchor="w")
        figure = Figure(figsize=(6.5, 4.2), dpi=100)
        self.ax = figure.subplots()
        self.ax.axis("off")
        figure.tight_layout()
        self.canvas = FigureCanvasTkAgg(figure, right)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        self.canvas.mpl_connect("pick_event", self.on_pick)
        self.draw()

    def on_pick(self, event):
        action = event.artist.get_gid()
        if action == 'lever_load':
            self.load()
        elif action == 'lever_plot':
            self.open_plot()

    def open_plot(self):
        if self.data is None:
            return
        try:
            figure = plot_lever_trials(self.data, self.channel.get(), self.go_label.get(),
                                      self.test_label.get(), self.app.preferences.get('plot_layout', {}),
                                      window_s=float(self.window_s.get()))
        except Exception as exc:
            messagebox.showerror('Lever plot', str(exc), parent=self.root)
            return
        window = tk.Toplevel(self.root)
        window.title(f'Lever across trials - {Path(self.filename.get()).name}')
        canvas = FigureCanvasTkAgg(figure, window)
        toolbar = NavigationToolbar2Tk(canvas, window, pack_toolbar=False)
        toolbar.pack(side='bottom', fill='x')
        canvas.get_tk_widget().pack(fill='both', expand=True)
        canvas.draw()

    def log(self, text):
        self.output.configure(state="normal")
        self.output.insert("end", text + "\n")
        self.output.see("end")
        self.output.configure(state="disabled")

    def browse(self):
        path = filedialog.askopenfilename(parent=self.root, initialdir=self.app.default_nwb_folder,
                                         filetypes=[("NWB files", "*.nwb")])
        if path:
            self.generation += 1
            self.filename.set(path)
            self.data, self.busy = None, False
            if self.viewer is not None:
                self.viewer.destroy()
                self.viewer = None
            self.viewer_button.configure(state="disabled")
            self.log(f"Selected: {path}")
            self.draw()

    def draw(self):
        self.ax.clear()
        self.ax.axis("off")
        if self.filename.get():
            loaded = self.data is not None
            self.app._canvas_button(16, 16, "Running..." if self.busy else "Loaded NWB file" if loaded else "Run NWB file",
                "lever_load", "#EEEEEE" if self.busy else "#F7FBFF" if loaded else "#F3FAF1",
                "#AAAAAA" if self.busy else "#4C78A8" if loaded else "#59A14F", enabled=not self.busy, ax=self.ax)
            if loaded and len(self.data['starts']) and self.channel.get():
                self.app._canvas_button(182, 16, 'Plot Lever Across Trials', 'lever_plot',
                                        '#F3FAF1', '#59A14F', ax=self.ax)
        self.canvas.draw_idle()

    def load(self):
        if self.busy or not self.filename.get():
            return
        self.busy, self.data = True, None
        self.viewer_button.configure(state="disabled")
        path, generation = self.filename.get(), self.generation
        self.log(f"Loading: {path}")
        self.draw()
        messages = queue.Queue()
        def worker():
            try:
                messages.put((load_lever_file(path), None))
            except Exception as exc:
                messages.put((None, str(exc)))
        def poll():
            if generation != self.generation:
                return
            try:
                data, error = messages.get_nowait()
            except queue.Empty:
                self.root.after(100, poll)
                return
            self.busy = False
            self.data = data
            if error:
                self.log(f"Load failed: {error}")
                messagebox.showerror("Lever NWB", error, parent=self.root)
            else:
                self.log(f"Loaded {len(data['starts'])} trials. Channels: {', '.join(data['signals'])}")
                channels = [name for name, signal in data['signals'].items()
                            if any(word in name.lower() for word in ('behaviorsignal', 'irfork', 'lever', 'force', 'position'))
                            and len(signal[0]) > 1]
                channels.sort(key=lambda name: (name.casefold() != 'behaviorsignal', name.casefold() != 'lever', name))
                self.channel_box.configure(values=channels)
                self.channel.set(channels[0] if channels else '')
                self.go_label.set(data['label_defaults'][0])
                self.test_label.set(data['label_defaults'][1])
                self.log(data['timing_note'])
                self.log(f"GO label: {self.go_label.get()}; Test label: {self.test_label.get()}")
                self.log('Recorded trial labels: ' + (', '.join(sorted(set(data['labels']))) or '(none)'))
                self.viewer_button.configure(state="normal" if len(data['starts']) else "disabled")
                if not len(data['starts']):
                    self.log("No trial timing found; Trial Viewer unavailable.")
            self.draw()
        threading.Thread(target=worker, daemon=True).start()
        self.root.after(100, poll)

    def open_viewer(self):
        if self.data is None or not len(self.data['starts']):
            return
        if self.viewer is not None and self.viewer.winfo_exists():
            self.viewer.lift()
            return
        data = self.data
        window = tk.Toplevel(self.root)
        self.viewer = window
        window.title(f"Lever Trial Viewer - {Path(self.filename.get()).name}")
        window.geometry("1000x800")
        controls = ttk.Frame(window, padding=8)
        controls.pack(fill="x")
        index = tk.StringVar(value="0")
        status = tk.StringVar()
        ttk.Label(controls, text="Trial index:").pack(side="left")
        entry = ttk.Entry(controls, textvariable=index, width=8)
        entry.pack(side="left")
        figure = Figure(figsize=(10, 7))
        names = [name for name in data['signals'] if name != 'TrialType'] or list(data['signals'])
        axes = figure.subplots(len(names), 1, sharex=True, squeeze=False)[:, 0]
        canvas = FigureCanvasTkAgg(figure, window)
        toolbar = NavigationToolbar2Tk(canvas, window, pack_toolbar=False)
        toolbar.pack(side="bottom", fill="x")
        canvas.get_tk_widget().pack(fill="both", expand=True)
        def render(delta=0):
            try:
                value = int(index.get())
            except ValueError:
                value = 0
            value = min(max(value+delta, 0), len(data['starts'])-1)
            index.set(str(value))
            start, stop = data['starts'][value], data['stops'][value]
            for ax, name in zip(axes, names):
                times, values, unit = data['signals'][name]
                mask = (times >= start-.5) & (times <= stop+.5)
                ax.clear()
                ax.step(times[mask]-start, values[mask], where="post", lw=.8)
                ax.axvspan(0, stop-start, color="steelblue", alpha=.1)
                ax.set_ylabel(f"{name}\n{unit}", fontsize=8)
                ax.grid(alpha=.2)
            axes[-1].set(xlabel="Time from trial start (s)", xlim=(-.5, stop-start+.5))
            status.set(f"Showing {value} / {len(data['starts'])-1}")
            figure.tight_layout()
            toolbar.update()
            canvas.draw()
        for label, command in (("Go", render), ("Previous", lambda: render(-1)), ("Next", lambda: render(1))):
            ttk.Button(controls, text=label, command=command).pack(side="left", padx=4)
        ttk.Label(controls, textvariable=status).pack(side="left")
        entry.bind("<Return>", lambda event: render())
        def close():
            window.destroy()
            self.viewer = None
        window.protocol("WM_DELETE_WINDOW", close)
        render()
