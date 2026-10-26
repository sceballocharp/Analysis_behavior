"""DMTS controls, session viewers, and batch analysis for the behavior GUI."""
from pathlib import Path
import os
import json
import pickle
import queue
import re
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import numpy as np

from behavior_functions import load_session_data_fromFile, analyze_session_responses

DEFAULT_DMTS_FILE = (
    "Y:/User_folders/Sebastian/behavior_data/M986/20260930/121733_Data/"
    "Sebastian_M986_121733_Data.nwb"
)

DEFAULT_DMTS_MATCHONLY_FILE = (
    "Y:/User_folders/Sebastian/behavior_data/M986/20261002/122447_Data/"
    "Sebastian_M986_122447_Data.nwb"
)


class DmtsPanel:
    """Own the DMTS tab, its analysis state, and its child windows."""

    def __init__(self, app):
        self.app = app
        self.root = app.root
        self.tab = ttk.Frame(app.main_notebook)
        app.main_notebook.add(self.tab, text="DMTS")
        self._build_ui()

    @property
    def preferences(self):
        return self.app.preferences

    @property
    def default_nwb_folder(self):
        return self.app.default_nwb_folder

    def _build_ui(self) -> None:
        groups_controls, animal_controls, file_controls, panels, plot = self._build_dmts_layout()
        self._build_dmts_groups_controls(groups_controls)
        self._build_dmts_animal_controls(animal_controls)
        settings = self._build_dmts_file_controls(file_controls)
        self._build_dmts_plot_settings(settings)
        self._build_dmts_canvas(panels, plot)

    def _build_dmts_layout(self):
        """Initialize DMTS state and create its tabs, panels, and split panes."""
        self.dmts_file_notebook = ttk.Notebook(self.tab, height=0)
        self.dmts_file_notebook.pack(fill="x")
        self.split = ttk.Panedwindow(self.tab, orient="horizontal")
        self.split.pack(fill="both", expand=True)
        dmts_controls = ttk.Frame(self.split, width=360, padding=(0, 8, 10, 0))
        dmts_plot = ttk.Frame(self.split, padding=(10, 8, 0, 0))
        self.split.add(dmts_controls, weight=1)
        self.split.add(dmts_plot, weight=3)
        self._dmts_initial_split_pending = True
        self.dmts_file_var = tk.StringVar(value="")
        self._dmts_loaded = False
        self._dmts_session = None
        self._dmts_loaded_signals = None
        self._dmts_file_actions = set()
        self._dmts_file_busy = False
        self._dmts_export_ready = False
        self.dmts_example_var = tk.StringVar(value="")
        self.dmts_viewer_window = None
        dmts_file_page = ttk.Frame(self.dmts_file_notebook)
        self.dmts_file_notebook.add(dmts_file_page, text="File")
        self.dmts_animal_tab = ttk.Frame(self.dmts_file_notebook)
        self.dmts_file_notebook.add(self.dmts_animal_tab, text="Animal")
        dmts_file_tab = ttk.Frame(dmts_controls, padding=10)
        dmts_animal_tab = ttk.Frame(dmts_controls, padding=10)
        self.dmts_batch_results = []
        self.dmts_batch_errors = []
        self._dmts_batch_running = False
        self._dmts_batch_generation = 0
        self.dmts_groups_tab = ttk.Frame(self.dmts_file_notebook)
        self.dmts_file_notebook.add(self.dmts_groups_tab, text="Groups")
        dmts_groups_controls = ttk.Frame(dmts_controls, padding=10)
        dmts_panels = {str(dmts_file_page): dmts_file_tab,
                       str(self.dmts_animal_tab): dmts_animal_tab,
                       str(self.dmts_groups_tab): dmts_groups_controls}
        dmts_file_tab.pack(fill="x")
        return dmts_groups_controls, dmts_animal_tab, dmts_file_tab, dmts_panels, dmts_plot


    def _build_dmts_groups_controls(self, dmts_groups_controls) -> None:
        """Build DMTS group loading, assignment, and curve controls."""
        self.dmts_group_exports = {}
        self.dmts_group_assignments = {}
        self.dmts_group_folder_var = tk.StringVar(value="No PKL folder selected")
        self.dmts_group_name_var = tk.StringVar(value="All files")
        self.dmts_groups_engaged_var = tk.BooleanVar(value=False)
        ttk.Button(dmts_groups_controls, text="Select PKL folder", command=self._load_dmts_groups).pack(anchor="w")
        ttk.Label(dmts_groups_controls, textvariable=self.dmts_group_folder_var, wraplength=300).pack(anchor="w", pady=6)
        table_frame = ttk.Frame(dmts_groups_controls)
        table_frame.pack(fill="both", expand=True)
        self.dmts_group_table = ttk.Treeview(table_frame, columns=("file", "sessions", "group"),
                                             show="headings", height=9, selectmode="extended")
        for key, title, width in (("file", "PKL file", 260), ("sessions", "Sessions", 70), ("group", "Group", 110)):
            self.dmts_group_table.heading(key, text=title)
            self.dmts_group_table.column(key, width=width, stretch=False)
        self.dmts_group_table.grid(row=0, column=0, sticky="nsew")
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)
        scroll_y = ttk.Scrollbar(table_frame, orient="vertical", command=self.dmts_group_table.yview)
        scroll_x = ttk.Scrollbar(table_frame, orient="horizontal", command=self.dmts_group_table.xview)
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x.grid(row=1, column=0, sticky="ew")
        self.dmts_group_table.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        ttk.Label(dmts_groups_controls, text="Group for selected files:").pack(anchor="w", pady=(8, 0))
        ttk.Entry(dmts_groups_controls, textvariable=self.dmts_group_name_var).pack(fill="x")
        ttk.Button(dmts_groups_controls, text="Assign to group", command=self._assign_dmts_group).pack(fill="x", pady=4)
        ttk.Checkbutton(dmts_groups_controls, text="Engaged-only curves", variable=self.dmts_groups_engaged_var).pack(anchor="w")
        ttk.Label(dmts_groups_controls, text="All files are included. Ctrl/Shift selects files for assignment. Each PKL has equal weight.", wraplength=300).pack(anchor="w")


    def _build_dmts_animal_controls(self, dmts_animal_tab) -> None:
        """Build mouse-folder selection, batch settings, and animal output."""
        self.dmts_animal_notebook = ttk.Notebook(dmts_animal_tab, style="DmtsFile.TNotebook")
        self.dmts_animal_notebook.pack(fill="both", expand=True)
        main_page = ttk.Frame(self.dmts_animal_notebook)
        self.dmts_light_matchonly_tab = ttk.Frame(self.dmts_animal_notebook)
        self.dmts_animal_notebook.add(main_page, text="Main")
        self.dmts_animal_notebook.add(self.dmts_light_matchonly_tab, text="LED testing")
        self.dmts_ls_tab = ttk.Frame(self.dmts_animal_notebook)
        self.dmts_animal_notebook.add(self.dmts_ls_tab, text="L&S")
        self._build_ls_controls(self.dmts_ls_tab)
        self.dmts_animal_notebook.bind("<<NotebookTabChanged>>", lambda _event: self._draw_dmts_canvas())
        self._build_light_matchonly_controls(self.dmts_light_matchonly_tab)
        dmts_animal_tab = main_page
        self.dmts_mouse_folder_var = tk.StringVar(value="No mouse folder selected")
        self.dmts_scan_status_var = tk.StringVar(value="Choose a mouse folder")
        self.dmts_silent_match_var = tk.StringVar(value="5")
        self.dmts_show_engaged_var = tk.BooleanVar(value=False)
        self.dmts_animal_nwb_files = []
        self._dmts_folder_scan_cancel = None
        self._dmts_folder_scan_poll = None
        input_buttons = ttk.Frame(dmts_animal_tab)
        input_buttons.pack(fill="x")
        ttk.Button(input_buttons, text="Select mouse folder", command=self._browse_dmts_mouse_folder).pack(side="left")
        ttk.Button(input_buttons, text="Load PKL", command=self._load_dmts_batch).pack(side="left", padx=(6, 0))
        ttk.Label(dmts_animal_tab, textvariable=self.dmts_mouse_folder_var, wraplength=300).pack(
            anchor="w", pady=(6, 8))
        ttk.Label(dmts_animal_tab, textvariable=self.dmts_scan_status_var, wraplength=300).pack(anchor="w")
        ttk.Label(dmts_animal_tab, text="Silent match trials allowed before disengagement:", wraplength=300).pack(anchor="w", pady=(8, 0))
        ttk.Spinbox(dmts_animal_tab, from_=1, to=1000, textvariable=self.dmts_silent_match_var, width=8).pack(anchor="w")
        ttk.Label(dmts_animal_tab, text="5 starts marking at the 6th silent match. Rerun batch after changing.", wraplength=300).pack(anchor="w")
        ttk.Checkbutton(dmts_animal_tab, text="Show engaged-only performance", variable=self.dmts_show_engaged_var).pack(anchor="w")
        ttk.Label(dmts_animal_tab, text="Output").pack(anchor="w", pady=(8, 4))
        self.dmts_animal_output = scrolledtext.ScrolledText(
            dmts_animal_tab, wrap="word", width=32, height=12, font=self.app.fonts.tk("output"), state="disabled")
        self.dmts_animal_output.pack(fill="both", expand=True)


    def _build_ls_controls(self, parent):
        self.ls_folder = None
        self.ls_results = []
        self.ls_errors = {}
        self._ls_busy = False
        self._ls_generation = 0
        self.ls_folder_var = tk.StringVar(value="No mouse folder selected")
        self.ls_status_var = tk.StringVar(value="Select a mouse folder, then run batch analysis.")
        ttk.Button(parent, text="Select mouse folder", command=self._browse_ls_folder).pack(anchor="w")
        ttk.Label(parent, textvariable=self.ls_folder_var, wraplength=300).pack(anchor="w", pady=(6, 8))
        ttk.Label(parent, textvariable=self.ls_status_var, wraplength=300).pack(anchor="w")
        ttk.Label(parent, text="Includes NWB files in subfolders. Uses saved outcomes and recorded Light/Sound identities.", wraplength=300).pack(anchor="w", pady=(8, 8))
        ttk.Label(parent, text="Output").pack(anchor="w")
        self.ls_output = scrolledtext.ScrolledText(parent, wrap="word", width=32, height=12,
                                                font=self.app.fonts.tk("output"), state="disabled")
        self.ls_output.pack(fill="both", expand=True, pady=(4, 0))

    def _write_ls_output(self, text):
        self.ls_output.configure(state="normal")
        self.ls_output.insert("end", text + "\n")
        self.ls_output.see("end")
        self.ls_output.configure(state="disabled")

    def _browse_ls_folder(self):
        folder = filedialog.askdirectory(parent=self.root, title="Select L&S mouse folder",
                                         initialdir=str(self.ls_folder) if self.ls_folder else self.default_nwb_folder)
        if folder:
            self._ls_generation += 1
            self._ls_busy = False
            self.ls_folder = Path(folder)
            self.ls_folder_var.set(folder)
            self.ls_results = []
            self.ls_errors = {}
            self.ls_output.configure(state="normal")
            self.ls_output.delete("1.0", "end")
            self.ls_output.configure(state="disabled")
            self.ls_status_var.set("Folder selected. Click Batch analysis in the canvas.")
            self._draw_dmts_canvas()

    def _run_ls_batch(self):
        if self._ls_busy or self.ls_folder is None:
            return
        self._ls_generation += 1
        generation = self._ls_generation
        folder = self.ls_folder
        self._ls_busy = True
        self.ls_results = []
        self.ls_errors = {}
        self.ls_status_var.set("Searching for NWB files...")
        self._write_ls_output(f"Batch: {folder}")
        self._draw_dmts_canvas()
        messages = queue.Queue()

        def worker():
            from dmts_ls_batch import summarize_modality_session
            try:
                paths = []
                def scan_error(exc):
                    messages.put(("error", str(exc.filename), str(exc)))
                for directory, dirs, files in os.walk(folder, onerror=scan_error, followlinks=False):
                    if generation != self._ls_generation:
                        return
                    dirs.sort(key=str.casefold)
                    paths.extend(Path(directory)/name for name in sorted(files, key=str.casefold) if Path(name).suffix.lower() == ".nwb")
                messages.put(("found", None, len(paths)))
                for index, path in enumerate(paths, 1):
                    if generation != self._ls_generation:
                        return
                    try:
                        result = summarize_modality_session(load_session_data_fromFile(path), path)
                        messages.put(("result", str(path), result))
                    except Exception as exc:
                        messages.put(("error", str(path), str(exc)))
                    messages.put(("progress", None, (index, len(paths))))
            except Exception as exc:
                messages.put(("error", str(folder), str(exc)))
            finally:
                messages.put(("done", None, None))

        def poll():
            if generation != self._ls_generation:
                return
            finished = False
            for _ in range(100):
                try:
                    kind, path, payload = messages.get_nowait()
                except queue.Empty:
                    break
                if kind == "result":
                    self.ls_results.append(payload)
                    stats = payload["stats"]
                    self._write_ls_output(f"OK: {Path(path).name}")
                    for label in ("Light", "Sound"):
                        metric = stats[label]["Overall accuracy"]
                        self._write_ls_output(f"  {label}: {metric['percent']:.1f}% (n={metric['n']})")
                    self._write_ls_output(f"  Excluded: {payload['excluded']}")
                elif kind == "error":
                    self.ls_errors[path] = payload
                    self._write_ls_output(f"Skipped: {path}: {payload}")
                elif kind == "found":
                    self._write_ls_output(f"Found {payload} NWB files.")
                elif kind == "progress":
                    self.ls_status_var.set(f"Analyzing {payload[0]}/{payload[1]} files")
                elif kind == "done":
                    finished = True
                    break
            if finished:
                from dmts_batch import session_sort_key
                self.ls_results.sort(key=session_sort_key)
                self._ls_busy = False
                self.ls_status_var.set(f"Batch complete: {len(self.ls_results)} sessions; {len(self.ls_errors)} skipped.")
                self._write_ls_output(self.ls_status_var.get())
                self._draw_dmts_canvas()
            else:
                self.root.after(100, poll)

        threading.Thread(target=worker, daemon=True).start()
        self.root.after(100, poll)

    def _plot_ls_results(self):
        if self._ls_busy or not self.ls_results:
            return
        from dmts_ls_batch import plot_modality_sessions
        self._show_dmts_figure(plot_modality_sessions(self.ls_results), "L&S — Light vs Sound across files", "1250x950")


    def _build_light_matchonly_controls(self, parent):
        """Collect unmodified JSON payloads for later LED testing analysis."""
        self.light_matchonly_results = {}
        self.light_matchonly_maps = {'performance': {}, 'voltage': {}}
        self.light_matchonly_errors = {}
        self.light_matchonly_folder = None
        self._light_matchonly_generation = 0
        self._light_matchonly_busy = False
        self.light_matchonly_folder_var = tk.StringVar(value="No mouse folder selected")
        self.light_matchonly_status_var = tk.StringVar(value="Choose a mouse folder containing JSON files.")
        ttk.Button(parent, text="Select mouse folder", command=self._browse_light_matchonly_folder).pack(anchor="w")
        ttk.Label(parent, textvariable=self.light_matchonly_folder_var, wraplength=300).pack(anchor="w", pady=(6, 8))
        ttk.Label(parent, textvariable=self.light_matchonly_status_var, wraplength=300).pack(anchor="w", pady=(0, 8))
        table = ttk.Frame(parent)
        table.pack(fill="both", expand=True)
        self.light_matchonly_table = ttk.Treeview(table, columns=("file", "status"), show="headings", height=12)
        self.light_matchonly_table.heading("file", text="JSON file")
        self.light_matchonly_table.heading("status", text="Load status")
        self.light_matchonly_table.column("file", width=190)
        self.light_matchonly_table.column("status", width=180)
        self.light_matchonly_table.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(table, orient="vertical", command=self.light_matchonly_table.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(table, orient="horizontal", command=self.light_matchonly_table.xview)
        horizontal.grid(row=1, column=0, sticky="ew")
        self.light_matchonly_table.configure(yscrollcommand=scrollbar.set, xscrollcommand=horizontal.set)
        table.columnconfigure(0, weight=1)
        table.rowconfigure(0, weight=1)
        ttk.Label(parent, text="Files in this folder are loaded into memory for later analysis.", wraplength=300).pack(anchor="w", pady=(8, 0))

    def _plot_light_matchonly_heatmap(self, kind):
        from dmts_light_heatmaps import plot_location_maps
        try:
            settings = {key: value.get().strip() for key, value in self.voltage_heatmap_vars.items()}
            figure = plot_location_maps(self.light_matchonly_maps[kind], kind,
                        title=f'{self.light_matchonly_folder.name} | LED testing {kind}',
                        cmap=settings['cmap'],
                        cmin=float(settings['cmin']) if kind == 'voltage' and settings['cmin'] else None,
                        cmax=float(settings['cmax']) if kind == 'voltage' and settings['cmax'] else None)
        except ValueError as exc:
            messagebox.showerror('LED testing heatmap unavailable', str(exc), parent=self.root)
            return
        self._show_dmts_figure(figure, f'LED testing {kind} heatmap', '950x850')

    def _browse_light_matchonly_folder(self):
        folder = filedialog.askdirectory(parent=self.root, title="Select LED testing mouse folder",
                                         initialdir=str(self.light_matchonly_folder) if self.light_matchonly_folder else self.default_nwb_folder)
        if folder:
            self._load_light_matchonly_folder(Path(folder))

    def _load_light_matchonly_folder(self, folder=None):
        folder = Path(folder) if folder is not None else self.light_matchonly_folder
        if folder is None:
            return
        self._light_matchonly_generation += 1
        generation = self._light_matchonly_generation
        self.light_matchonly_folder = folder
        self.light_matchonly_folder_var.set(str(folder))
        self.light_matchonly_results = {}
        self.light_matchonly_maps = {'performance': {}, 'voltage': {}}
        self.light_matchonly_errors = {}
        self.light_matchonly_table.delete(*self.light_matchonly_table.get_children())
        self._light_matchonly_busy = True
        self.light_matchonly_status_var.set("Loading JSON files...")
        self._draw_dmts_canvas()
        messages = queue.Queue()

        def worker():
            try:
                paths = sorted((p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".json"), key=lambda p: p.name.casefold())
                for path in paths:
                    if generation != self._light_matchonly_generation:
                        return
                    try:
                        with path.open("r", encoding="utf-8-sig") as source:
                            payload = json.load(source)
                        if not isinstance(payload, dict):
                            raise ValueError("Expected a JSON dictionary at the top level.")
                        messages.put(("loaded", path, payload))
                    except Exception as exc:
                        messages.put(("error", path, str(exc)))
            except OSError as exc:
                messages.put(("error", folder, str(exc)))
            finally:
                messages.put(("done", None, None))

        def poll():
            if generation != self._light_matchonly_generation:
                return
            finished = False
            for _ in range(100):
                try:
                    kind, path, payload = messages.get_nowait()
                except queue.Empty:
                    break
                if kind == "done":
                    finished = True
                    break
                key = str(path.resolve())
                if kind == "loaded":
                    self.light_matchonly_results[key] = payload
                    status = "Loaded"
                else:
                    self.light_matchonly_errors[key] = payload
                    status = "Skipped: " + payload
                self.light_matchonly_table.insert("", "end", iid=key, values=(path.name, status))
            loaded, skipped = len(self.light_matchonly_results), len(self.light_matchonly_errors)
            self.light_matchonly_status_var.set(f"{loaded} files loaded; {skipped} skipped" + ("." if finished else " — loading..."))
            if finished:
                self._light_matchonly_busy = False
                from dmts_light_heatmaps import collect_location_maps
                self.light_matchonly_maps = collect_location_maps(self.light_matchonly_results)
                if not loaded and not skipped:
                    self.light_matchonly_status_var.set("No JSON files found in this folder.")
                self._draw_dmts_canvas()
            else:
                self.root.after(100, poll)

        threading.Thread(target=worker, daemon=True).start()
        self.root.after(100, poll)


    def _build_dmts_file_controls(self, dmts_file_tab):
        """Build the DMTS file controls and create the plot-settings page."""
        self.dmts_file_inner_notebook = ttk.Notebook(dmts_file_tab, style="DmtsFile.TNotebook")
        self.dmts_file_inner_notebook.pack(fill="both", expand=True)
        dmts_file_main = ttk.Frame(self.dmts_file_inner_notebook, padding=8)
        dmts_plot_settings = ttk.Frame(self.dmts_file_inner_notebook, padding=8)
        self.dmts_file_inner_notebook.add(dmts_file_main, text="Main")
        self.dmts_file_inner_notebook.add(dmts_plot_settings, text="Plot settings")
        ttk.Label(dmts_file_main, text="Session input:").pack(anchor="w")
        ttk.Button(dmts_file_main, text="Browse NWB", command=self._browse_dmts_nwb).pack(fill="x", pady=(6, 0))
        ttk.Label(dmts_file_main, text="Examples:").pack(anchor="w", pady=(6, 0))
        examples = ttk.Combobox(dmts_file_main, textvariable=self.dmts_example_var,
                               values=("", "Pretraining recording", "MatchOnly recording"), state="readonly")
        examples.pack(fill="x", pady=(3, 6))
        examples.bind("<<ComboboxSelected>>", self._select_dmts_example)
        self.dmts_trial_viewer_button = ttk.Button(
            dmts_file_main, text="Trial Viewer", command=self._open_dmts_trial_viewer, state="disabled")
        self.dmts_trial_viewer_button.pack(fill="x", pady=(6, 0))
        self.dmts_voltage_viewer_button = ttk.Button(
            dmts_file_main, text="Trial voltages (log)",
            command=self._open_dmts_voltage_viewer, state="disabled")
        self.dmts_voltage_viewer_button.pack(fill="x", pady=(6, 0))
        self.dmts_file_var.trace_add("write", lambda *_args: self._update_dmts_voltage_button())
        ttk.Label(dmts_file_main, textvariable=self.dmts_file_var, wraplength=300).pack(
            anchor="w", pady=(6, 0))
        ttk.Label(dmts_file_main, text="Output").pack(anchor="w", pady=(10, 4))
        self.dmts_file_output = scrolledtext.ScrolledText(
            dmts_file_main, wrap="word", width=32, height=8, font=self.app.fonts.tk("output"), state="disabled")
        self.dmts_file_output.pack(fill="both", expand=True)
        return dmts_plot_settings


    def _build_dmts_plot_settings(self, dmts_plot_settings) -> None:
        """Build time-window and trial-aligned lick plotting settings."""
        pretraining_settings = ttk.LabelFrame(dmts_plot_settings, text="Plot Time Window settings", padding=10)
        pretraining_settings.pack(fill="x", pady=(12, 0))
        self.pretraining_vars = {}
        for row, (key, label, default) in enumerate((
            ("t_start", "Start time (s)", "295"),
            ("t_end", "End time (s)", "300"),
            ("threshold_v", "Threshold (V)", "1.0"),
            ("smooth_ms", "Smoothing (ms)", "0"),
        )):
            self.pretraining_vars[key] = tk.StringVar(value=default)
            ttk.Label(pretraining_settings, text=label).grid(row=row, column=0, sticky="w", pady=3)
            ttk.Entry(pretraining_settings, textvariable=self.pretraining_vars[key], width=10).grid(
                row=row, column=1, sticky="ew", padx=(8, 0), pady=3)
        pretraining_settings.columnconfigure(1, weight=1)
        match_settings = ttk.LabelFrame(dmts_plot_settings, text="Plot Trial-Aligned Licks settings", padding=10)
        match_settings.pack(fill="x", pady=(12, 0))
        self.matchonly_vars = {}
        for row, (key, label, default) in enumerate((
            ("threshold_v", "Threshold (V)", "1.0"),
            ("smooth_ms", "Smoothing (ms)", "0"),
            ("bin_width_s", "Bin width (s)", "0.1"),
            ("pre_s", "Before onset (s)", "0.5"),
            ("post_s", "After response (s)", "0.5"),
            ("trace_height", "Trace height", "0.7"),
            ("max_plot_points", "Max drawing points", "800"),
        )):
            self.matchonly_vars[key] = tk.StringVar(value=default)
            ttk.Label(match_settings, text=label).grid(row=row, column=0, sticky="w", pady=2)
            ttk.Entry(match_settings, textvariable=self.matchonly_vars[key], width=10).grid(
                row=row, column=1, sticky="ew", padx=(8, 0), pady=2)
        match_settings.columnconfigure(1, weight=1)
        heatmap_settings = ttk.LabelFrame(dmts_plot_settings, text="Voltage heatmap settings", padding=10)
        heatmap_settings.pack(fill="x", pady=(12, 0))
        self.voltage_heatmap_vars = {}
        for row, (key, label, default) in enumerate((
                ('cmin', 'cmin (V; blank = auto)', ''),
                ('cmax', 'cmax (V; blank = auto)', ''),
                ('cmap', 'Colormap', 'viridis'))):
            var = tk.StringVar(value=default)
            self.voltage_heatmap_vars[key] = var
            ttk.Label(heatmap_settings, text=label).grid(row=row, column=0, sticky='w', pady=3)
            if key == 'cmap':
                widget = ttk.Combobox(heatmap_settings, textvariable=var, state='readonly',
                                      values=sorted(plt.colormaps()), width=15)
            else:
                widget = ttk.Entry(heatmap_settings, textvariable=var, width=10)
            widget.grid(row=row, column=1, sticky='ew', padx=(8, 0), pady=3)
        heatmap_settings.columnconfigure(1, weight=1)


    def _build_dmts_canvas(self, dmts_panels, dmts_plot) -> None:
        """Connect DMTS panel switching and create its plot canvas."""
        def select_dmts_subtab(_event=None):
            selected = self.dmts_file_notebook.select()
            for panel in dmts_panels.values():
                panel.pack_forget()
            dmts_panels[selected].pack(fill="both", expand=True)
            self._draw_dmts_canvas()
        self.dmts_file_notebook.bind("<<NotebookTabChanged>>", select_dmts_subtab)
        ttk.Label(dmts_plot, text="Plot").pack(anchor="w")
        self.canvas_figure = Figure(figsize=(6.5, 4.2), dpi=100)
        self.canvas_ax = self.canvas_figure.add_subplot(1, 1, 1)
        self.canvas_ax.set_facecolor("white")
        self.canvas_ax.set_xticks([])
        self.canvas_ax.set_yticks([])
        for spine in self.canvas_ax.spines.values():
            spine.set_visible(False)
        self.canvas_figure.tight_layout()
        self.canvas = FigureCanvasTkAgg(self.canvas_figure, master=dmts_plot)
        self._draw_dmts_canvas()
        self.canvas.mpl_connect("pick_event", self._handle_dmts_canvas_pick)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill="both", expand=True)


    def _load_dmts_groups(self):
        folder = filedialog.askdirectory(parent=self.root, title="Select folder of DMTS batch PKL exports")
        if not folder:
            return
        from dmts_groups import export_curves
        self.dmts_group_exports = {}
        self.dmts_group_assignments = {}
        self.dmts_group_table.delete(*self.dmts_group_table.get_children())
        errors = []
        self.root.configure(cursor="watch")
        self.root.update_idletasks()
        try:
            for path in sorted(Path(folder).glob("*")):
                if not path.is_file() or path.suffix.lower() != ".pkl":
                    continue
                try:
                    with path.open("rb") as source:
                        payload = pickle.load(source)
                    export_curves(payload)
                    key = str(path)
                    self.dmts_group_exports[key] = payload
                    self.dmts_group_table.insert("", "end", iid=key, values=(path.name, len(payload["sessions"]), "All files"))
                except Exception as exc:
                    errors.append(f"{path.name}: {exc}")
        finally:
            self.root.configure(cursor="")
        self.dmts_group_folder_var.set(f"{folder}\n{len(self.dmts_group_exports)} DMTS exports loaded; {len(errors)} skipped")
        self._draw_dmts_canvas()
        if errors:
            messagebox.showwarning("Skipped PKL files", "\n".join(errors), parent=self.root)


    def _assign_dmts_group(self):
        group = self.dmts_group_name_var.get().strip() or "All files"
        for key in self.dmts_group_table.selection():
            self.dmts_group_assignments[key] = group
            self.dmts_group_table.set(key, "group", group)


    def _plot_dmts_groups(self):
        try:
            from dmts_groups import plot_groups
            figure, self.dmts_group_averages = plot_groups(
                self.dmts_group_exports, self.dmts_group_assignments,
                engaged_only=self.dmts_groups_engaged_var.get(), plot_layout=self.preferences.get("plot_layout", {}))
        except (ValueError, KeyError, TypeError) as exc:
            messagebox.showerror("Group plot unavailable", str(exc), parent=self.root)
            return
        width, height = (round(value) for value in figure.get_size_inches() * figure.dpi)
        self._show_dmts_figure(figure, "DMTS group performance", f"{width}x{height+45}")


    def _draw_dmts_canvas(self):
        if not hasattr(self, "canvas"):
            return
        ax = self.canvas_ax
        ax.clear()
        ax.axis("off")
        if (self.dmts_file_notebook.select() == str(self.dmts_animal_tab)
                and self.dmts_animal_notebook.select() == str(self.dmts_ls_tab)):
            if self.ls_folder is not None:
                busy = self._ls_busy
                self.app._canvas_button(16, 16, "Running..." if busy else "Batch analysis", "dmts_ls_batch",
                                        "#EEEEEE" if busy else "#F3FAF1", "#AAAAAA" if busy else "#59A14F", enabled=not busy, ax=ax)
                if self.ls_results:
                    self.app._canvas_button(182, 16, "Light vs Sound\nacross files", "dmts_ls_plot",
                                            "#EEEEEE" if busy else "#F3FAF1", "#AAAAAA" if busy else "#59A14F", enabled=not busy, ax=ax)
        elif (self.dmts_file_notebook.select() == str(self.dmts_animal_tab)
                and self.dmts_animal_notebook.select() == str(self.dmts_light_matchonly_tab)):
            if self.light_matchonly_folder is not None:
                busy = self._light_matchonly_busy
                self.app._canvas_button(16, 16, "Loading..." if busy else "Reload JSON files",
                                        "dmts_light_load", "#EEEEEE" if busy else "#F3FAF1",
                                        "#AAAAAA" if busy else "#59A14F", enabled=not busy, ax=ax)
                if not busy:
                    for x, kind, label in ((182, 'performance', 'Performance heatmap'),
                                           (348, 'voltage', 'Voltage heatmap')):
                        if self.light_matchonly_maps[kind]:
                            self.app._canvas_button(x, 16, label + '\n10 × 10',
                                    'dmts_light_' + kind, '#F3FAF1', '#59A14F', ax=ax)
        elif self.dmts_file_notebook.select() == str(self.dmts_groups_tab):
            if self.dmts_group_exports:
                self.app._canvas_button(16, 16, "Plot group\naverages", "dmts_groups_plot", "#F3FAF1", "#59A14F", ax=ax)
        elif self.dmts_file_notebook.select() == str(self.dmts_animal_tab):
            if (len(self.dmts_animal_nwb_files) > 1 or self.dmts_batch_results) and self._dmts_folder_scan_poll is None:
                ready = bool(self.dmts_batch_results) and not self._dmts_batch_running
                for x, y, label, action, enabled in (
                    (16, 16, "Running..." if self._dmts_batch_running else "Batch performance", "dmts_batch", not self._dmts_batch_running),
                    (182, 16, "Plot results", "dmts_batch_plot", ready),
                    (16, 82, "Save data", "dmts_batch_save", ready),
                    (182, 82, "Hit by StimID\nacross sessions", "dmts_batch_stim_hit", ready),
                    (182, 148, "HIT and CR counts\nper session", "dmts_batch_outcome_counts", ready),
                ):
                    if action == "dmts_batch" and len(self.dmts_animal_nwb_files) < 2:
                        continue
                    if action != "dmts_batch" and not ready:
                        continue
                    self.app._canvas_button(x, y, label, action, "#F3FAF1" if enabled else "#EEEEEE",
                                        "#59A14F" if enabled else "#AAAAAA", enabled=enabled, ax=ax)
        elif self.dmts_file_var.get():
            self.app._canvas_button(16, 16, "Running..." if self._dmts_file_busy else
                                "Loaded NWB file" if self._dmts_loaded else "Run NWB file",
                                "dmts_load", "#EEEEEE" if self._dmts_file_busy else "#F7FBFF" if self._dmts_loaded else "#F3FAF1",
                                "#AAAAAA" if self._dmts_file_busy else "#4C78A8" if self._dmts_loaded else "#59A14F",
                                enabled=not self._dmts_file_busy, ax=ax)
            actions = [(182, 16, "Plot Session\nRawdata", "dmts_summary"),
                       (182, 82, "Plot Time Window", "dmts_pretraining"),
                       (348, 82, "Plot Trial-Aligned\nLicks", "dmts_matchonly"),
                       (182, 148, "Performance\nby StimID", "dmts_sound_performance"),
                       (348, 148, "Light vs Sound\nperformance", "dmts_modality_performance"),
                       (514, 82, "Trial Examples", "dmts_trial_examples")]
            if self._dmts_export_ready:
                actions.append((16, 82, "Export results", "dmts_file_export"))
            for x, y, label, action in actions:
                if not self._dmts_loaded:
                    continue
                if action not in self._dmts_file_actions and action != "dmts_file_export":
                    continue
                enabled = not self._dmts_file_busy
                self.app._canvas_button(x, y, label, action, "#F3FAF1" if enabled else "#EEEEEE",
                                    "#59A14F" if enabled else "#AAAAAA", enabled=enabled, ax=ax)
            csv_ready = bool(getattr(self, "_dmts_csv_trials", None))
            csv_available = bool(self._dmts_voltage_logs())
            if csv_available:
                self.app._canvas_button(16, 346, "Loaded CSV file" if csv_ready else "Load CSV file",
                                    "dmts_csv_load", "#F7FBFF" if csv_ready else "#F3FAF1",
                                    "#4C78A8" if csv_ready else "#59A14F", ax=ax)
            if csv_ready:
                self.app._canvas_button(182, 346, "Average voltages\nby StimID", "dmts_csv_average",
                                    "#F3FAF1", "#59A14F", ax=ax)
            if getattr(self, '_dmts_voltage_averages', None):
                self.app._canvas_button(348, 346, "Voltage heatmap\n10 × 10", "dmts_csv_heatmap",
                                        "#F3FAF1", "#59A14F", ax=ax)
            if csv_ready and getattr(self, '_dmts_performance_pairs', None):
                self.app._canvas_button(514, 346, "Performance heatmap\n10 × 10", "dmts_performance_heatmap",
                                        "#F3FAF1", "#59A14F", ax=ax)
        self.app._draw_canvas_connections(self.canvas_ax)
        self.canvas.draw_idle()


    def _write_dmts_animal_output(self, text):
        self.dmts_animal_output.configure(state="normal")
        self.dmts_animal_output.insert("end", text)
        self.dmts_animal_output.see("end")
        self.dmts_animal_output.configure(state="disabled")


    def _run_dmts_batch(self):
        if self._dmts_batch_running or len(self.dmts_animal_nwb_files) < 2 or self._dmts_folder_scan_poll is not None:
            return
        try:
            silent_match_threshold = int(self.dmts_silent_match_var.get())
            if silent_match_threshold < 1:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid threshold", "Enter a positive integer for silent match trials.", parent=self.root)
            return
        self._dmts_batch_running = True
        self.dmts_batch_results = []
        self.dmts_batch_errors = []
        generation = self._dmts_batch_generation
        paths = sorted(self.dmts_animal_nwb_files, key=lambda p: str(p).casefold())
        messages = queue.Queue()
        self._draw_dmts_canvas()
        self._write_dmts_animal_output("\nBatch: saved outcomes; plots and exports ordered by NWB session_start_time.\n")

        def worker():
            from dmts_batch import summarize_session
            for index, path in enumerate(paths, 1):
                if generation != self._dmts_batch_generation:
                    return
                try:
                    result = summarize_session(load_session_data_fromFile(path), path, silent_match_threshold=silent_match_threshold)
                    messages.put(("result", result))
                except Exception as exc:
                    messages.put(("error", {"file": str(path), "error": str(exc)}))
                messages.put(("progress", index))
            messages.put(("done", None))

        def poll():
            if generation != self._dmts_batch_generation:
                return
            finished = False
            for _ in range(100):
                try:
                    kind, payload = messages.get_nowait()
                except queue.Empty:
                    break
                if kind == "result":
                    self.dmts_batch_results.append(payload)
                    from dmts_batch import session_sort_key
                    if session_sort_key(payload)[0]:
                        self._write_dmts_animal_output(f"Warning: {payload['file']} has no valid timezone-aware session_start_time; placed last.\n")
                    self._write_dmts_animal_output(f"{len(self.dmts_batch_results)}. {payload['file']}: {payload['total']:.1f}%\n")
                    engagement = payload["engagement"]
                    self._write_dmts_animal_output(
                        f"  Engagement: {engagement['n_periods']} disengaged periods; "
                        f"{engagement['engaged_pct']:.1f}% of eligible trials engaged; "
                        f"{engagement['unknown_eligible_trials']} unknown. Threshold: {engagement['silent_match_threshold']}.\n")
                    if engagement["warning"]:
                        self._write_dmts_animal_output(engagement["warning"] + "\n")
                    blanks = payload["blank_response"]
                    self._write_dmts_animal_output("  Blank responses: " + "; ".join(
                        f"{side}: {blanks[side]['rate_pct']:.1f}% ({blanks[side]['valid_trials']} valid)"
                        for side in ("any", "left", "right")) + "\n")
                elif kind == "error":
                    self.dmts_batch_errors.append(payload)
                    self._write_dmts_animal_output(f"Skipped {payload['file']}: {payload['error']}\n")
                elif kind == "progress":
                    self.dmts_scan_status_var.set(f"Analyzing {payload}/{len(paths)} files")
                else:
                    finished = True
                    self._dmts_batch_running = False
                    from dmts_batch import session_sort_key
                    self.dmts_batch_results.sort(key=session_sort_key)
                    summary = f"Batch complete: {len(self.dmts_batch_results)} sessions; {len(self.dmts_batch_errors)} skipped."
                    self.dmts_scan_status_var.set(summary)
                    self._write_dmts_animal_output(summary + "\n")
                    self._draw_dmts_canvas()
                    break
            if not finished:
                self.root.after(100, poll)
        threading.Thread(target=worker, daemon=True).start()
        self.root.after(100, poll)


    def _plot_dmts_batch(self):
        if not self.dmts_batch_results or self._dmts_batch_running:
            return
        from dmts_batch import plot_batch
        self._show_dmts_figure(plot_batch(self.dmts_batch_results, show_engaged_only=self.dmts_show_engaged_var.get()),
                               "DMTS batch performance", "1300x850")


    def _load_dmts_batch(self):
        filename = filedialog.askopenfilename(parent=self.root, title="Load saved DMTS batch data",
                                              filetypes=[("DMTS batch data", "*.pkl")])
        if not filename:
            return
        try:
            from dmts_groups import export_curves
            from dmts_batch import session_sort_key
            with open(filename, "rb") as source:
                payload = pickle.load(source)
            export_curves(payload)
            sessions = payload["sessions"]
            if not isinstance(sessions, list) or not sessions:
                raise ValueError("The export contains no sessions.")
            for session in sessions:
                if not {"file", "trials", "total", "match", "nonmatch"}.issubset(session):
                    raise ValueError("The export is missing DMTS session results.")
            if any(session.get("session_start_time") for session in sessions):
                sessions = sorted(sessions, key=session_sort_key)
        except Exception as exc:
            messagebox.showerror("Could not load DMTS batch", str(exc), parent=self.root)
            return
        self._dmts_batch_generation += 1
        self._dmts_batch_running = False
        if self._dmts_folder_scan_cancel is not None:
            self._dmts_folder_scan_cancel.set()
        if self._dmts_folder_scan_poll is not None:
            self.root.after_cancel(self._dmts_folder_scan_poll)
            self._dmts_folder_scan_poll = None
        self.dmts_animal_nwb_files = []
        self.dmts_batch_results = sessions
        self.dmts_batch_errors = payload.get("errors", [])
        self.dmts_mouse_folder_var.set(payload.get("mouse_folder") or str(Path(filename).parent))
        self.dmts_show_engaged_var.set(False)
        self.dmts_scan_status_var.set(f"Loaded {len(sessions)} sessions from PKL")
        self._write_dmts_animal_output(f"Loaded DMTS batch data: {filename}\n{len(sessions)} sessions ready for plotting.\n")
        self._draw_dmts_canvas()

    def _save_dmts_batch(self):
        if not self.dmts_batch_results or self._dmts_batch_running:
            return
        filename = filedialog.asksaveasfilename(parent=self.root, title="Save DMTS batch data",
            defaultextension=".pkl", initialfile=Path(self.dmts_mouse_folder_var.get()).name + "_dmts_batch.pkl",
            filetypes=[("Pickle data", "*.pkl")])
        if not filename:
            return
        from dmts_batch import session_sort_key
        payload = dict(format="dmts_batch_v2", outcome_source="saved", rolling_window=25,
                       session_order="session_start_time", mouse_folder=self.dmts_mouse_folder_var.get(),
                       sessions=sorted(self.dmts_batch_results, key=session_sort_key),
                       errors=self.dmts_batch_errors)
        try:
            with open(filename, "wb") as output:
                pickle.dump(payload, output, protocol=pickle.HIGHEST_PROTOCOL)
        except OSError as exc:
            messagebox.showerror("Save failed", str(exc), parent=self.root)
            return
        self._write_dmts_animal_output(f"Saved DMTS batch data: {filename}\n")


    def _handle_dmts_canvas_pick(self, event) -> None:
        if event.artist.get_gid() == "dmts_ls_batch":
            self._run_ls_batch()
            return
        if event.artist.get_gid() == "dmts_ls_plot":
            self._plot_ls_results()
            return
        if event.artist.get_gid() in ('dmts_light_performance', 'dmts_light_voltage'):
            if not self._light_matchonly_busy:
                self._plot_light_matchonly_heatmap(event.artist.get_gid().removeprefix('dmts_light_'))
            return
        if event.artist.get_gid() == "dmts_light_load":
            if not self._light_matchonly_busy:
                self._load_light_matchonly_folder()
            return
        if event.artist.get_gid() == "dmts_performance_heatmap":
            self._open_dmts_performance_heatmap()
            return
        if event.artist.get_gid() == "dmts_csv_heatmap":
            self._open_dmts_csv_heatmap()
            return
        if event.artist.get_gid() == "dmts_csv_load":
            self._load_dmts_csv()
            return
        if event.artist.get_gid() == "dmts_csv_average":
            self._open_dmts_csv_average()
            return
        if event.artist.get_gid() == "dmts_groups_plot":
            self._plot_dmts_groups()
            return
        if event.artist.get_gid() == "dmts_batch":
            self._run_dmts_batch()
        elif event.artist.get_gid() == "dmts_batch_plot":
            self._plot_dmts_batch()
        elif event.artist.get_gid() == "dmts_batch_save":
            self._save_dmts_batch()
        elif event.artist.get_gid() == "dmts_batch_stim_hit":
            self._plot_dmts_batch_stim_hit()
            return
        elif event.artist.get_gid() == "dmts_batch_outcome_counts":
            self._plot_dmts_outcome_counts()
            return
        if event.artist.get_gid() == "dmts_load":
            self._load_dmts_file()
            return
        actions = {"dmts_pretraining": self._run_dmts_pretraining,
                   "dmts_modality_performance": self._open_dmts_modality_performance,
                   "dmts_trial_examples": self._open_dmts_trial_examples,
                   "dmts_matchonly": self._run_dmts_matchonly,
                   "dmts_summary": self._open_dmts_summary,
                   "dmts_sound_performance": self._open_dmts_sound_performance,
                   "dmts_file_export": self._export_dmts_file_results}
        action = event.artist.get_gid()
        if action in actions and self._dmts_loaded and not self._dmts_file_busy and self.dmts_file_var.get():
            if action not in self._dmts_file_actions and not (action == "dmts_file_export" and self._dmts_export_ready):
                return
            self._dmts_file_busy = True
            self._draw_dmts_canvas()
            self.root.update_idletasks()
            try:
                actions[action]()
            finally:
                self._dmts_file_busy = False
                self._draw_dmts_canvas()


    def _plot_dmts_outcome_counts(self):
        if self._dmts_batch_running or not self.dmts_batch_results:
            return
        from dmts_batch import plot_session_outcome_counts
        figure = plot_session_outcome_counts(self.dmts_batch_results)
        self._show_dmts_figure(figure, "DMTS HIT and CR counts per session", "1200x750")

    def _plot_dmts_batch_stim_hit(self):
        if self._dmts_batch_running or not self.dmts_batch_results:
            return
        try:
            from dmts_batch import plot_hit_by_stim_sessions
            figure = plot_hit_by_stim_sessions(self.dmts_batch_results)
        except ValueError as exc:
            messagebox.showerror("Hit by StimID unavailable", str(exc), parent=self.root)
            return
        self._show_dmts_figure(figure, "DMTS Hit by StimID across sessions", "1200x750")


    def _open_dmts_modality_performance(self):
        try:
            from dmts_summary import plot_modality_performance
            figure = plot_modality_performance(self._dmts_session, title=Path(self.dmts_file_var.get()).name)
        except Exception as exc:
            messagebox.showerror('Light vs Sound unavailable', str(exc), parent=self.root)
            return
        self._show_dmts_figure(figure, 'Light vs Sound performance', '1100x700')

    def _open_dmts_sound_performance(self) -> None:
        try:
            from dmts_summary import plot_performance_by_sound, performance_by_stim_data
            name = Path(self.dmts_file_var.get()).name
            figure = plot_performance_by_sound(self._dmts_session, title=name)
            self._dmts_performance_pairs = performance_by_stim_data(self._dmts_session)
        except Exception as exc:
            messagebox.showerror("Performance by StimID unavailable", str(exc), parent=self.root)
            return
        self._show_dmts_figure(figure, f"Performance by StimID - {name}", "1400x850")
        self._draw_dmts_canvas()

    def _open_dmts_performance_heatmap(self):
        if not (getattr(self, '_dmts_performance_pairs', None) and getattr(self, '_dmts_csv_trials', None)):
            return
        try:
            from dmts_summary import plot_performance_position_heatmap
            figure = plot_performance_position_heatmap(self._dmts_performance_pairs,
                        self._dmts_csv_trials, title=f'{Path(self.dmts_file_var.get()).name} | Performance by position',
                        cmap=self.voltage_heatmap_vars['cmap'].get())
        except ValueError as exc:
            messagebox.showerror('Performance heatmap unavailable', str(exc), parent=self.root)
            return
        self._show_dmts_figure(figure, 'Performance heatmap — all positions', '950x850')
        self._dmts_performance_by_location = dict(figure.heatmap_locations)


    def _open_dmts_summary(self) -> None:
        filename = self.dmts_file_var.get()
        self.root.configure(cursor="watch")
        self.root.update_idletasks()
        try:
            from dmts_summary import plot_session_summary
            session = self._dmts_session
            figure = plot_session_summary(session, title=Path(filename).name)
        except Exception as exc:
            messagebox.showerror("Plot Session Rawdata unavailable", str(exc), parent=self.root)
            return
        finally:
            self.root.configure(cursor="")
        from matplotlib.backends.backend_tkagg import NavigationToolbar2Tk
        window = tk.Toplevel(self.root)
        window.title(f"Plot Session Rawdata - {Path(filename).name}")
        window.geometry("1300x800")
        controls = ttk.Frame(window, padding=8)
        controls.pack(fill="x")
        ttk.Label(controls, text="Rolling window (eligible trials):").pack(side="left")
        window_var = tk.StringVar(value="25")
        entry = ttk.Spinbox(controls, from_=1, to=10000, textvariable=window_var, width=7)
        entry.pack(side="left", padx=8)
        plot_frame = ttk.Frame(window)
        plot_frame.pack(fill="both", expand=True)
        state = {"figure": None, "canvas": None, "toolbar": None}

        def display(fig):
            if state["canvas"] is not None:
                state["toolbar"].destroy()
                state["canvas"].get_tk_widget().destroy()
                plt.close(state["figure"])
            canvas = FigureCanvasTkAgg(fig, master=plot_frame)
            toolbar = NavigationToolbar2Tk(canvas, plot_frame, pack_toolbar=False)
            toolbar.pack(side="bottom", fill="x")
            canvas.get_tk_widget().pack(fill="both", expand=True)
            canvas.draw()
            state.update(figure=fig, canvas=canvas, toolbar=toolbar)

        def refresh():
            try:
                fig = plot_session_summary(session, window=int(window_var.get()), title=Path(filename).name)
            except (ValueError, TypeError) as exc:
                messagebox.showerror("Invalid window", str(exc), parent=window)
                return
            display(fig)

        ttk.Button(controls, text="Update", command=refresh).pack(side="left")
        entry.bind("<Return>", lambda _event: refresh())
        display(figure)

        def close():
            plt.close(state["figure"])
            window.destroy()

        window.protocol("WM_DELETE_WINDOW", close)


    def _run_dmts_matchonly(self) -> None:
        filename = self.dmts_file_var.get()
        try:
            settings = {key: float(value.get()) for key, value in self.matchonly_vars.items()}
        except ValueError:
            messagebox.showerror("Invalid settings", "Enter a number for each MatchOnly setting.", parent=self.root)
            return
        self.root.configure(cursor="watch")
        self.root.update_idletasks()
        try:
            from dmts_matchonly import plot_matchonly
            session = self._dmts_session
            figure, self.lick_events, self.lick_histogram, self.trial_order = plot_matchonly(
                session, file_path=filename, **settings)
        except Exception as exc:
            messagebox.showerror("MatchOnly analysis failed", str(exc), parent=self.root)
            return
        finally:
            self.root.configure(cursor="")
        self._write_dmts_file_output(f"Trial-aligned analysis: {len(self.trial_order)} trials, {len(self.lick_events)} aligned lick events")
        self._show_dmts_figure(figure, f"Plot Trial-Aligned Licks - {Path(filename).name}", "1300x850")
        self._dmts_export_ready = True
        self._dmts_export_kind = "aligned"
        self._draw_dmts_canvas()


    def _export_dmts_file_results(self):
        if not self._dmts_export_ready:
            return
        source = Path(self.dmts_file_var.get())
        output_folder = source.parent / f"{source.stem}_lick_analysis"
        try:
            output_folder.mkdir(parents=True, exist_ok=True)
            if self._dmts_export_kind == "pretraining":
                import pandas as pd
                pd.DataFrame({"side": ["Left"] * len(self.left_lick_times) + ["Right"] * len(self.right_lick_times),
                              "time_session_s": np.concatenate((self.left_lick_times, self.right_lick_times))}).to_csv(
                    output_folder / "pretraining_lick_events.csv", index=False)
            else:
                self.lick_events.to_csv(output_folder / "lick_events.csv", index=False)
                self.lick_histogram.to_csv(output_folder / "lick_histogram.csv", index=False)
                self.trial_order.to_csv(output_folder / "trial_order.csv", index=False)
        except OSError as exc:
            messagebox.showwarning("Plot ready; export failed", str(exc), parent=self.root)
        else:
            self._write_dmts_file_output(f"Saved analysis results to: {output_folder}")
            print(f"Saved analysis results to:\n{output_folder}")


    def _open_dmts_trial_examples(self):
        try:
            from dmts_trial_examples import plot_trial_examples
            figure = plot_trial_examples(self._dmts_session, title=Path(self.dmts_file_var.get()).name)
        except Exception as exc:
            messagebox.showerror("Trial Examples unavailable", str(exc), parent=self.root)
            return
        self._show_dmts_figure(figure, "DMTS Trial Examples", "1400x850")


    def _run_dmts_pretraining(self) -> None:
        filename = self.dmts_file_var.get()
        if not filename:
            messagebox.showinfo("Select an NWB file", "Use Browse NWB in the DMTS File tab first.", parent=self.root)
            return
        try:
            settings = {key: float(value.get()) for key, value in self.pretraining_vars.items()}
        except ValueError:
            messagebox.showerror("Invalid settings", "Enter a number for each pretraining setting.", parent=self.root)
            return
        self.root.configure(cursor="watch")
        self.root.update_idletasks()
        try:
            from dmts_pretraining import plot_pretraining
            figure, lick_times = plot_pretraining(filename, loaded_signals=self._dmts_loaded_signals, **settings)
        except Exception as exc:
            messagebox.showerror("Pretraining analysis failed", str(exc), parent=self.root)
            return
        finally:
            self.root.configure(cursor="")
        self.left_lick_times = lick_times["LeftLick"]
        self.right_lick_times = lick_times["RightLick"]
        self._dmts_export_ready = True
        self._dmts_export_kind = "pretraining"
        self._draw_dmts_canvas()
        self._write_dmts_file_output(f"Detected licks: left {len(self.left_lick_times)}, right {len(self.right_lick_times)}")
        print("Left lick times (s):", self.left_lick_times)
        print("Right lick times (s):", self.right_lick_times)

        self._show_dmts_figure(figure, f"Plot Time Window - {Path(filename).name}", "1300x650")


    def _write_dmts_file_output(self, text):
        self.dmts_file_output.configure(state="normal")
        self.dmts_file_output.insert("end", text + "\n")
        self.dmts_file_output.see("end")
        self.dmts_file_output.configure(state="disabled")


    def _show_dmts_figure(self, figure, title, geometry) -> None:
        from matplotlib.backends.backend_tkagg import NavigationToolbar2Tk
        window = tk.Toplevel(self.root)
        window.title(title)
        self._write_dmts_file_output(f"Opened: {title}")
        window.geometry(geometry)
        if hasattr(figure, 'heatmap_locations'):
            # Capture this figure's data so later session changes cannot affect the export.
            locations = dict(figure.heatmap_locations)
            kind = figure.heatmap_kind
            source_stem = Path(self.dmts_file_var.get()).stem
            def save_dictionary():
                filename = filedialog.asksaveasfilename(
                    parent=window, title='Save heatmap dictionary by location',
                    initialfile=f'{source_stem}_{kind}_by_location.json',
                    defaultextension='.json',
                    filetypes=[('JSON dictionary', '*.json'), ('Python dictionary (pickle)', '*.pkl')])
                if not filename:
                    return
                try:
                    if Path(filename).suffix.lower() == '.pkl':
                        with open(filename, 'wb') as output:
                            pickle.dump(locations, output, protocol=pickle.HIGHEST_PROTOCOL)
                    else:
                        import json
                        Path(filename).write_text(json.dumps(locations, indent=2, allow_nan=False), encoding='utf-8')
                except OSError as exc:
                    messagebox.showerror('Save failed', str(exc), parent=window)
                    return
                self._write_dmts_file_output(f'Saved {kind} dictionary by location: {filename}')
            ttk.Button(window, text='Save dictionary by location', command=save_dictionary).pack(side='top', pady=6)
        canvas = FigureCanvasTkAgg(figure, master=window)
        toolbar = NavigationToolbar2Tk(canvas, window, pack_toolbar=False)
        toolbar.update()
        toolbar.pack(side="bottom", fill="x")
        canvas.get_tk_widget().pack(fill="both", expand=True)
        canvas.draw()

        def close():
            plt.close(figure)
            window.destroy()

        window.protocol("WM_DELETE_WINDOW", close)


    def _browse_dmts_mouse_folder(self) -> None:
        previous = self.dmts_mouse_folder_var.get()
        folder = filedialog.askdirectory(parent=self.root, title="Select mouse folder",
                                         initialdir=previous if Path(previous).is_dir() else "Y:/User_folders/Sebastian/behavior_data")
        if folder:
            self._start_dmts_folder_scan(Path(folder))


    def _start_dmts_folder_scan(self, folder) -> None:
        self._dmts_batch_generation += 1
        self._dmts_batch_running = False
        self.dmts_batch_results = []
        self.dmts_batch_errors = []
        if self._dmts_folder_scan_cancel is not None:
            self._dmts_folder_scan_cancel.set()
        if self._dmts_folder_scan_poll is not None:
            self.root.after_cancel(self._dmts_folder_scan_poll)
        cancel = threading.Event()
        self._dmts_folder_scan_cancel = cancel
        results = queue.Queue()
        self.dmts_mouse_folder_var.set(str(folder))
        self.dmts_animal_nwb_files = []
        self.dmts_scan_status_var.set("Scanning subfolders...")
        self.dmts_animal_output.configure(state="normal")
        self.dmts_animal_output.delete("1.0", "end")
        self.dmts_animal_output.insert("end", f"Searching: {folder}\n\n")
        self.dmts_animal_output.configure(state="disabled")

        def worker():
            count = 0
            def warning(exc):
                results.put(("warning", f"Cannot read {exc.filename}: {exc.strerror}"))
            try:
                for directory, dirs, files in os.walk(folder, onerror=warning, followlinks=False):
                    if cancel.is_set():
                        return
                    dirs.sort(key=str.casefold)
                    paths = [Path(directory) / name for name in sorted(files, key=str.casefold)
                             if Path(name).suffix.lower() == ".nwb"]
                    count += 1
                    results.put(("progress", (count, paths)))
            except Exception as exc:
                results.put(("warning", str(exc)))
            finally:
                results.put(("done", None))

        warnings = 0
        def poll():
            nonlocal warnings
            if cancel.is_set():
                return
            finished = False
            self.dmts_animal_output.configure(state="normal")
            for _ in range(100):
                try:
                    kind, payload = results.get_nowait()
                except queue.Empty:
                    break
                if kind == "progress":
                    directories, paths = payload
                    self.dmts_animal_nwb_files.extend(paths)
                    for path in paths:
                        self.dmts_animal_output.insert("end", str(path.relative_to(folder)) + "\n")
                    self.dmts_scan_status_var.set(
                        f"Scanning: {directories} folders; {len(self.dmts_animal_nwb_files)} NWB files")
                elif kind == "warning":
                    warnings += 1
                    self.dmts_animal_output.insert("end", f"Warning: {payload}\n")
                else:
                    finished = True
                    total = len(self.dmts_animal_nwb_files)
                    summary = f"Found {total} NWB file(s)." if total else "No NWB files found."
                    if warnings:
                        summary += f" {warnings} warning(s); search may be incomplete."
                    self.dmts_scan_status_var.set(summary)
                    self.dmts_animal_output.insert("end", "\n" + summary + "\n")
                    break
            self.dmts_animal_output.configure(state="disabled")
            self._dmts_folder_scan_poll = None if finished else self.root.after(100, poll)
            if finished:
                self._draw_dmts_canvas()

        threading.Thread(target=worker, daemon=True).start()
        self._dmts_folder_scan_poll = self.root.after(100, poll)
        self._draw_dmts_canvas()


    def _browse_dmts_nwb(self) -> None:
        current = self.dmts_file_var.get()
        filename = filedialog.askopenfilename(
            parent=self.root, title="Choose a DMTS NWB file",
            initialdir=str(Path(current).parent) if current else self.default_nwb_folder,
            filetypes=[("NWB files", "*.nwb"), ("All files", "*.*")],
        )
        if filename:
            self.dmts_example_var.set("")
            self._select_dmts_file(filename)


    def _select_dmts_example(self, _event=None):
        if not self.dmts_example_var.get():
            if self.dmts_viewer_window is not None and self.dmts_viewer_window.winfo_exists():
                self.dmts_viewer_window.event_generate("<<CloseDMTSViewer>>")
            self._dmts_loaded = False
            self._dmts_session = None
            self._dmts_loaded_signals = None
            self.dmts_file_var.set("")
            self._dmts_file_actions.clear()
            self._dmts_export_ready = False
            self.dmts_trial_viewer_button.configure(state="disabled")
            self._draw_dmts_canvas()
            return
        filename = {"Pretraining recording": DEFAULT_DMTS_FILE,
                    "MatchOnly recording": DEFAULT_DMTS_MATCHONLY_FILE}.get(self.dmts_example_var.get())
        if filename:
            self._select_dmts_file(filename)
            if self.dmts_example_var.get() == "Pretraining recording":
                self._dmts_file_actions.intersection_update({"dmts_pretraining", "dmts_trial_examples"})
                self._draw_dmts_canvas()
            self._load_dmts_file()


    def _load_dmts_file(self):
        if self._dmts_file_busy or not self.dmts_file_var.get():
            return
        filename = self.dmts_file_var.get()
        actions = set(self._dmts_file_actions)
        self._write_dmts_file_output(f"Loading NWB: {filename}")
        self._dmts_loaded = False
        self._dmts_export_ready = False
        self.dmts_trial_viewer_button.configure(state="disabled")
        self._dmts_file_busy = True
        self._draw_dmts_canvas()
        messages = queue.Queue()
        def worker():
            try:
                if not actions:
                    raise ValueError("No supported DMTS signals or trial data found. Select another NWB file.")
                session = load_session_data_fromFile(Path(filename)) if actions & {"dmts_matchonly", "dmts_summary", "dmts_trial_examples"} else None
                signals = None
                if "dmts_pretraining" in actions:
                    import h5py
                    from dmts_pretraining import _read_signal
                    with h5py.File(filename, "r") as handle:
                        signals = {name: _read_signal(handle["acquisition"], name)
                                   for name in ("Reward", "LeftLick", "RightLick")}
                messages.put((session, signals, None))
            except Exception as exc:
                messages.put((None, None, str(exc)))
        def poll():
            try:
                session, signals, error = messages.get_nowait()
            except queue.Empty:
                self.root.after(100, poll)
                return
            self._dmts_file_busy = False
            if filename != self.dmts_file_var.get() or actions != self._dmts_file_actions:
                self._draw_dmts_canvas()
                # An example selected during loading must start after the old load ends.
                example_file = {"Pretraining recording": DEFAULT_DMTS_FILE,
                                "MatchOnly recording": DEFAULT_DMTS_MATCHONLY_FILE}.get(self.dmts_example_var.get())
                if example_file and self.dmts_file_var.get() == example_file:
                    self._load_dmts_file()
                return
            if error:
                self._write_dmts_file_output(f"Loading failed: {error}")
                messagebox.showerror("NWB loading failed", error, parent=self.root)
            else:
                self._dmts_session = session
                self._dmts_loaded_signals = signals
                self._dmts_loaded = True
                self._write_dmts_file_output(f"Loaded NWB: {filename}")
                self.dmts_trial_viewer_button.configure(state="normal" if session is not None else "disabled")
            self._draw_dmts_canvas()
        threading.Thread(target=worker, daemon=True).start()
        self.root.after(100, poll)


    def _select_dmts_file(self, filename):
        if self.dmts_viewer_window is not None and self.dmts_viewer_window.winfo_exists():
            self.dmts_viewer_window.event_generate("<<CloseDMTSViewer>>")
        self.dmts_file_var.set(filename)
        self._write_dmts_file_output(f"Selected: {filename}")
        self._dmts_loaded = False
        self._dmts_session = None
        self._dmts_loaded_signals = None
        self._dmts_file_actions = set()
        self._dmts_export_ready = False
        self.dmts_trial_viewer_button.configure(state="disabled")
        for name in ("lick_events", "lick_histogram", "trial_order", "left_lick_times", "right_lick_times"):
            if hasattr(self, name):
                delattr(self, name)
        try:
            import h5py
            with h5py.File(filename, "r") as handle:
                if all(f"acquisition/{name}/data" in handle for name in ("LeftLick", "RightLick", "Reward")):
                    self._dmts_file_actions.add("dmts_pretraining")
                trials = handle.get("intervals/trials")
                if trials is not None and all(name in trials for name in ("sample_sound_ids", "test_sound_ids", "HMCF")):
                    self._dmts_file_actions.add("dmts_summary")
                    self._dmts_file_actions.add("dmts_sound_performance")
                    self._dmts_file_actions.add("dmts_modality_performance")
                    if all(f"acquisition/{name}/data" in handle for name in ("LeftLick", "RightLick")):
                        self._dmts_file_actions.add("dmts_matchonly")
                        self._dmts_file_actions.add("dmts_trial_examples")
        except Exception as exc:
            messagebox.showerror("Unable to read NWB file", str(exc), parent=self.root)
        self._draw_dmts_canvas()


    def _update_dmts_voltage_button(self):
        self._dmts_voltage_by_location = {}
        self._dmts_performance_by_location = {}
        self._dmts_performance_pairs = {}
        self._dmts_voltage_averages = {}
        self._dmts_csv_trials = []
        self._dmts_csv_path = None
        existing = getattr(self, "dmts_voltage_window", None)
        if existing is not None and existing.winfo_exists():
            self.dmts_voltage_viewer.close()
        logs = self._dmts_voltage_logs()
        self.dmts_voltage_viewer_button.configure(state="normal" if logs else "disabled")


    def _dmts_csv_loaded(self, path, trials):
        self._dmts_voltage_by_location = {}
        self._dmts_performance_by_location = {}
        self._dmts_voltage_averages = {}
        self._dmts_csv_path = path
        self._dmts_csv_trials = trials
        self._write_dmts_file_output(f"Loaded CSV file: {path}")
        self._draw_dmts_canvas()


    def _open_dmts_csv_average(self):
        if not getattr(self, "_dmts_csv_trials", None):
            return
        from types import SimpleNamespace
        from dmts_voltage_viewer import DMTSVoltageViewer, voltage_presentations_by_stim, voltage_position_averages
        self._dmts_voltage_averages = voltage_position_averages(
            voltage_presentations_by_stim(self._dmts_csv_trials))
        state = SimpleNamespace(trials=self._dmts_csv_trials, window=self.root,
                                file_path=tk.StringVar(master=self.root, value=str(self._dmts_csv_path)),
                                summary_closers=[])
        DMTSVoltageViewer.open_stim_summary(state)
        self._draw_dmts_canvas()

    def _open_dmts_csv_heatmap(self):
        if not getattr(self, '_dmts_voltage_averages', None):
            return
        from dmts_voltage_viewer import plot_voltage_position_heatmap
        try:
            settings = {key: value.get().strip() for key, value in self.voltage_heatmap_vars.items()}
            figure = plot_voltage_position_heatmap(self._dmts_voltage_averages,
                        title=f'{Path(self._dmts_csv_path).name} | Average voltage by position',
                        cmin=float(settings['cmin']) if settings['cmin'] else None,
                        cmax=float(settings['cmax']) if settings['cmax'] else None,
                        cmap=settings['cmap'])
        except ValueError as exc:
            messagebox.showerror('Voltage heatmap unavailable', str(exc), parent=self.root)
            return
        self._show_dmts_figure(figure, 'Average voltage heatmap — all positions', '950x850')
        self._dmts_voltage_by_location = dict(figure.heatmap_locations)


    def _dmts_voltage_logs(self):
        filename = self.dmts_file_var.get()
        if not filename or not Path(filename).is_file():
            return []
        try:
            return sorted((path for path in Path(filename).parent.iterdir()
                           if path.is_file() and path.suffix.lower() == ".csv"
                           and path.name.casefold() not in {"triallog.csv", "parameters.csv"}),
                          key=lambda path: path.name.lower())
        except OSError:
            return []


    def _select_dmts_csv_log(self):
        logs = self._dmts_voltage_logs()
        self.dmts_voltage_viewer_button.configure(state="normal" if logs else "disabled")
        if not logs:
            return None
        if len(logs) > 1:
            # Prefer the log sharing the NWB session's date/time tokens.
            tokens = set(re.findall(r"(?<!\d)\d{6,8}(?!\d)", Path(self.dmts_file_var.get()).stem))
            scores = [len(tokens & set(re.findall(r"(?<!\d)\d{6,8}(?!\d)", path.stem))) for path in logs]
            best = max(scores)
            candidates = [path for path, score in zip(logs, scores) if score == best]
            if best > 0 and len(candidates) == 1:
                return candidates[0]
            self._write_dmts_file_output("Multiple CSV logs found; cannot identify a unique session log: "
                                         + ", ".join(path.name for path in logs))
            messagebox.showerror("Multiple CSV logs",
                                 "More than one eligible CSV was found. Keep the corresponding session log in the NWB folder.",
                                 parent=self.root)
            return None
        return logs[0]


    def _load_dmts_csv(self):
        selected = self._select_dmts_csv_log()
        if selected is None:
            return
        from dmts_voltage_viewer import parse_dmts_log_file
        try:
            trials = parse_dmts_log_file(selected)
            if not trials:
                raise ValueError("No DMTS trial presentations were found.")
        except Exception as exc:
            messagebox.showerror("Could not load CSV log", str(exc), parent=self.root)
            return
        self._dmts_csv_loaded(selected, trials)


    def _open_dmts_voltage_viewer(self) -> None:
        existing = getattr(self, "dmts_voltage_window", None)
        if existing is not None and existing.winfo_exists():
            existing.lift()
            return
        selected = getattr(self, "_dmts_csv_path", None) or self._select_dmts_csv_log()
        if selected is None:
            return
        from dmts_voltage_viewer import DMTSVoltageViewer
        window = tk.Toplevel(self.root)
        window.geometry("1400x800")
        self.dmts_voltage_window = window
        self.dmts_voltage_viewer = DMTSVoltageViewer(window, default_file=selected,
                                                    on_loaded=self._dmts_csv_loaded)


    def _open_dmts_trial_viewer(self) -> None:
        if self.dmts_viewer_window is not None and self.dmts_viewer_window.winfo_exists():
            self.dmts_viewer_window.lift()
            return
        filename = self.dmts_file_var.get()
        if not filename:
            return
        self.root.configure(cursor="watch")
        self.root.update_idletasks()
        try:
            session = self._dmts_session
            ir_events, trial_analysis, _ = analyze_session_responses(session, "Licks")
            count = (len(session["dmts_analysis"]["trials"]) if "dmts_analysis" in session
                     else int((np.asarray(session["trialID"]["full"]) == 99).sum()))
            if not count:
                raise ValueError("No trials found in this file.")
        except Exception as exc:
            messagebox.showerror("Unable to open trials", str(exc), parent=self.root)
            return
        finally:
            self.root.configure(cursor="")

        from behavior_plots import plot_trial_ir_and_sound
        window = tk.Toplevel(self.root)
        self.dmts_viewer_window = window
        window.title(f"DMTS Trial Viewer - {Path(filename).name}")
        window.geometry("760x920")
        controls = ttk.Frame(window, padding=10)
        controls.pack(fill="x")
        index_var = tk.StringVar(value="0")
        status_var = tk.StringVar()
        plot_frame = ttk.Frame(window, padding=10)
        plot_frame.pack(fill="both", expand=True)
        state = {"figure": None, "canvas": None, "index": 0}

        def close(_event=None):
            if state["figure"] is not None:
                plt.close(state["figure"])
            window.destroy()
            self.dmts_viewer_window = None

        def render(delta=0):
            try:
                index = int(index_var.get())
            except ValueError:
                index = state["index"]
            index = min(max(index + delta, 0), count - 1)
            try:
                figure = plot_trial_ir_and_sound(
                    session, trial_ir_analysis=trial_analysis, ir_events=ir_events,
                    trial_index=index, show=False, block=False)
            except Exception as exc:
                messagebox.showerror("Unable to plot trial", str(exc), parent=window)
                return
            if state["canvas"] is not None:
                state["canvas"].get_tk_widget().destroy()
            if state["figure"] is not None:
                plt.close(state["figure"])
            state.update(figure=figure, index=index)
            state["canvas"] = FigureCanvasTkAgg(figure, master=plot_frame)
            state["canvas"].draw()
            state["canvas"].get_tk_widget().pack(fill="both", expand=True)
            index_var.set(str(index))
            status_var.set(f"Showing {index} / {count - 1}")

        ttk.Label(controls, text="Trial index:").pack(side="left")
        entry = ttk.Entry(controls, textvariable=index_var, width=8)
        entry.pack(side="left", padx=4)
        entry.bind("<Return>", lambda _event: render())
        for label, command in (("Go", render), ("Previous", lambda: render(-1)), ("Next", lambda: render(1))):
            ttk.Button(controls, text=label, command=command).pack(side="left", padx=3)
        ttk.Label(controls, textvariable=status_var).pack(side="left", padx=8)
        window.protocol("WM_DELETE_WINDOW", close)
        window.bind("<<CloseDMTSViewer>>", close)
        render()

