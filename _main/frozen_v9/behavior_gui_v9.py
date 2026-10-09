# -*- coding: utf-8 -*-

from pathlib import Path
from collections import Counter
import threading
import ast
import io
import traceback
from contextlib import redirect_stdout, redirect_stderr
import sys
import argparse
import json
import pickle
import re
import os
import queue
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.transforms import Affine2D, ScaledTranslation
import numpy as np

CODE_folder = str(Path(__file__).resolve().parent)
sys.path.append(CODE_folder)

from behavior_functions import (
    load_session_data_fromFolder,
    load_session_data_fromFile,
    extract_performance,
    extract_hit_by_sound_IR,
    extract_hit_by_sound_licks,
    detect_ir_events,
    analyze_ir_by_trial,
    analyze_session_responses,
    analyze_lick_events_by_trial,
    find_nwb_files_for_animal,
    run_nwb_batch_analysis,
)
DEFAULT_SESSION_FOLDER = (
    r"C:/Users/seceball/Dropbox/__idA/BathellierLab/Behavior/_DATA/M588/20250526/112810_Data/"
)

DEFAULT_SESSION_FILE = (
    r"Y:/Bathellierlab_gaia/BASIL/BASIL_FAIR/BASILapp/NWB/SC_fmGO/"
)
DEFAULT_ANIMAL_NAME = ""
DEFAULT_DMTS_FILE = (
    "Y:/User_folders/Sebastian/behavior_data/M986/20260930/121733_Data/"
    "Sebastian_M986_121733_Data.nwb"
)
DEFAULT_DMTS_MATCHONLY_FILE = (
    "Y:/User_folders/Sebastian/behavior_data/M986/20261002/122447_Data/"
    "Sebastian_M986_122447_Data.nwb"
)

GUI_IMPORT_ERROR = None
if "--nogui" not in sys.argv:
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, scrolledtext, ttk
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    except Exception as exc:  # pragma: no cover - optional GUI deps
        GUI_IMPORT_ERROR = exc


def _get_plot_session_visualizations(force_agg: bool = False):
    if force_agg:
        import matplotlib
        matplotlib.use("Agg", force=True)
    from behavior_plots import plot_session_visualizations
    return plot_session_visualizations


class ScanMediaFoldersApp:
    def __init__(self, root, initial_folder: str | None = None, initial_file: str | None = None) -> None:
        self.root = root
        self.root.title("BEHAVIOR v9")
        window_width = 1500
        window_height = 800
        window_x = 0
        window_y = 0
        self.root.geometry(f"{window_width}x{window_height}+{window_x}+{window_y}")
        self.root.minsize(1200, 600)

        folder_startup_value = (initial_folder or "").strip() or DEFAULT_SESSION_FOLDER
        file_startup_value = (initial_file or "").strip() or DEFAULT_SESSION_FILE
        animal_startup_value = DEFAULT_ANIMAL_NAME
        print('__init__','folder_startup_value',folder_startup_value)
        print('__init__','file_startup_value',file_startup_value)
        
        self.folder_var = tk.StringVar(value=folder_startup_value)
        self.file_var = tk.StringVar(value=file_startup_value)
        self.animal_var = tk.StringVar(value=animal_startup_value)
        self.hit_source_var = tk.StringVar(value="IR")
        self.hit_source_status_var = tk.StringVar(value="Select an NWB file to detect its hit source.")
        self.active_input = "folder"
        self._single_input_selected = False
        self.nwb_groups: dict[str, list[Path]] = {}
        self.group_assignments = {}
        self.group_name_var = tk.StringVar(value="")
        self.group_exports = {}
        self.group_folder = None
        self.groups_loading = False
        self.group_folder_var = tk.StringVar(value="No folder selected")
        self.nwb_search_root = None
        self.nwb_loading = False
        self.nwb_scanned_files: list[Path] = []
        self.nwb_group_var = tk.StringVar(value="")
        self.found_nwb_files: list[Path] = []
        self.found_session_folders: list[Path] = []
        self.batch_performance_by_file: dict[str, dict] = {}
        self.batch_trial_performance_by_file: dict[str, dict] = {}
        self.batch_trials_by_sound_id: dict[int, list[dict]] = {}
        self.batch_hit_by_sound: dict[int, dict] = {}
        self.current_folder_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="Ready")
        self.is_running = False
        self.scan_generation = 0
        self.trial_viewer_button: ttk.Button | None = None
        self.trial_viewer_window = None
        self.trial_viewer_canvas = None
        self.trial_viewer_figure = None
        self.trial_plot_frame = None
        self.trial_index_var = None
        self.trial_viewer_status_var = None
        self.main_canvas_figure = None
        self.main_canvas = None
        self.main_canvas_ax = None
        self.main_canvas_pick_cid = None

        self.console_window = None
        self.console_namespace = {}
        self.console_session = None
        self.guide_window = None
        self.guide_settings_path = Path(CODE_folder) / "gui_preferences.json"
        try:
            preferences = json.loads(self.guide_settings_path.read_text(encoding="utf-8"))
            show_guide = preferences.get("show_guide_at_startup", True)
            if not isinstance(show_guide, bool):
                show_guide = True
        except (OSError, ValueError, AttributeError):
            preferences = {}
            show_guide = True
        self.preferences = preferences
        default_nwb_folder = preferences.get("default_nwb_folder", ".")
        self.default_nwb_folder = default_nwb_folder if isinstance(default_nwb_folder, str) and default_nwb_folder.strip() else "."
        self.show_guide_at_startup = tk.BooleanVar(value=show_guide)
        self._build_ui()
        self.folder_var.trace_add("write", lambda *_: self._sync_current_input_label())
        self.file_var.trace_add("write", lambda *_: self._sync_current_input_label())
        self._sync_current_input_label()
        self._write_output("GUI ready. Choose a folder or NWB file, then click its Run rectangle in the Plot panel.\n")

    def _save_guide_preference(self) -> None:
        try:
            self.preferences["show_guide_at_startup"] = self.show_guide_at_startup.get()
            self.guide_settings_path.write_text(
                json.dumps(self.preferences, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            messagebox.showwarning(
                "Preference not saved",
                f"The guide setting applies for this session, but could not be saved:\n{exc}",
                parent=self.guide_window,
            )

    def _show_getting_started(self) -> None:
        if self.guide_window is not None and self.guide_window.winfo_exists():
            self.guide_window.deiconify()
            self.guide_window.lift()
            return
        window = tk.Toplevel(self.root)
        self.guide_window = window
        window.title("Getting started - BEHAVIOR v9")
        window.geometry("740x680")
        window.minsize(480, 360)
        frame = ttk.Frame(window, padding=20)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Your first session", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(frame, text="Follow these steps, then keep this guide open while you work.").pack(
            anchor="w", pady=(4, 12)
        )
        body = scrolledtext.ScrolledText(
            frame, wrap="word", font=("Segoe UI", 11), padx=12, pady=12,
            relief="flat", borderwidth=0, width=60, height=18,
        )
        body.pack(fill="both", expand=True)
        body.tag_configure("heading", font=("Segoe UI", 12, "bold"), foreground="#245783",
                           spacing1=12, spacing3=5)
        body.tag_configure("paragraph", spacing3=10)
        sections = [
            ("1. Choose a session", "Open the Folder or File tab. Click Browse FOLDER for a raw session folder, or Browse NWB for a .nwb file. Check the path under Current session folder before continuing."),
            ("2. Choose how hits are counted", "Under Hit source, choose IR for infrared sensor responses or Licks for lick responses. Choose the source appropriate for your experiment before clicking the Run rectangle in the Plot panel. To change it later, select the other source and run the analysis again."),
            ("3. Run the analysis", "Click the selected session rectangle labeled Run in the Plot panel. Status shows Running... while the session is processed. After a successful run, Output shows trial counts and analysis results, and Trial viewer becomes available. If an error appears, read the error message and Output, check your input, and try again."),
            ("4. Explore the results", "Read the summary in Output. In the Plot panel, click the colored boxes or dots for IR occupancy, Performance, or Hit by sound to open the available charts."),
            ("5. Look at individual trials", "Click Trial viewer after running a session. Use Previous and Next, or enter a Trial index and click Go. Indices start at 0, so index 0 is the first trial."),
            ("6. Keep your results", "In a separate plot window, use the Save icon on the Matplotlib toolbar to choose an image filename and location. The GUI has no CSV/JSON export button; those exports are available through terminal mode (--nogui with --outdir)."),
            ("Optional: analyze several sessions", "Open the Animal tab. Click Find NWB files and choose a parent folder; files are grouped by animal automatically. Choose a Detected animal and check its files in Output, then click Run All NWB Files in the canvas. For raw folders, enter Animal name, click Find folders, and click Run All Folders in the canvas. Use Batch performance in the Plot panel when it becomes available."),
            ("Need this guide again?", "Open Help > Getting started. Clear the checkbox below if you prefer to open the guide only when you need it."),
        ]
        for heading, paragraph in sections:
            body.insert("end", heading + "\n", "heading")
            body.insert("end", paragraph + "\n\n", "paragraph")
        body.configure(state="disabled")
        footer = ttk.Frame(frame)
        footer.pack(fill="x", pady=(14, 0))
        ttk.Checkbutton(
            footer, text="Show this guide at startup", variable=self.show_guide_at_startup,
            command=self._save_guide_preference,
        ).pack(side="left")
        ttk.Button(footer, text="Close guide", command=window.destroy).pack(side="right")
        window.bind("<Escape>", lambda _event: window.destroy())

    def _build_ui(self) -> None:
        menu_bar = tk.Menu(self.root)
        help_menu = tk.Menu(menu_bar, tearoff=False)
        help_menu.add_command(label="Getting started", command=self._show_getting_started)
        menu_bar.add_cascade(label="Help", menu=help_menu)
        self.root.configure(menu=menu_bar)
        main_frame = ttk.Frame(self.root, padding=16)
        main_frame.pack(fill="both", expand=True)
        title_label = ttk.Label(
            main_frame,
            text="Check Single Sessions",
            font=("Segoe UI", 14, "bold"),
        )
        title_label.pack(anchor="w")

        description_label = ttk.Label(
            main_frame,
            text=(
                "Choose a folder or NWB file, then click its Run rectangle in the Plot panel. "                
            ),
            wraplength=700,
        )
        description_label.pack(anchor="w", pady=(4, 14))

        self.main_notebook = ttk.Notebook(main_frame)
        self.main_notebook.pack(fill="both", expand=True, pady=(0, 8))
        self.main_tab = ttk.Frame(self.main_notebook)
        self.main_notebook.add(self.main_tab, text="Go/noGo")
        self.dmts_tab = ttk.Frame(self.main_notebook)
        self.main_notebook.add(self.dmts_tab, text="DMTS")

        # The subtab strip stays above both the full-width table and lower panels.
        notebook = ttk.Notebook(self.main_tab, height=0)
        self.notebook = notebook
        notebook.pack(fill="x")
        self.input_tab = ttk.Frame(notebook)
        self.animal_tab = ttk.Frame(notebook)
        self.groups_tab = ttk.Frame(notebook)
        notebook.add(self.input_tab, text="Folder or File")
        notebook.add(self.animal_tab, text="Animal")
        notebook.add(self.groups_tab, text="Groups")

        self.gonogo_vertical_split = ttk.Panedwindow(self.main_tab, orient="vertical")
        self.gonogo_vertical_split.pack(fill="both", expand=True)
        self.groups_table_panel = ttk.Frame(self.gonogo_vertical_split, padding=10, height=240)
        self._groups_table_height = 240
        self.layout_split = ttk.Panedwindow(self.gonogo_vertical_split, orient="horizontal")
        self.gonogo_vertical_split.add(self.layout_split, weight=1)
        controls_frame = ttk.Frame(self.layout_split, width=360, padding=(0, 8, 10, 0))
        right_frame = ttk.Frame(self.layout_split, padding=(10, 8, 0, 0))
        self.layout_split.add(controls_frame, weight=1)
        self.layout_split.add(right_frame, weight=3)
        self._initial_split_pending = True

        self.input_controls_host = ttk.Frame(controls_frame)
        self.input_controls_host.pack(fill="x")
        input_tab = ttk.Frame(self.input_controls_host, padding=10)
        meta_tab = ttk.Frame(self.input_controls_host, padding=10)
        groups_controls = ttk.Frame(self.input_controls_host, padding=10)
        self._gonogo_control_panels = {
            str(self.input_tab): input_tab,
            str(self.animal_tab): meta_tab,
            str(self.groups_tab): groups_controls,
        }
        input_tab.pack(fill="x")
        ttk.Button(self.groups_table_panel, text="Select PKL folder", command=self._load_group_folder).pack(anchor="w")
        ttk.Label(self.groups_table_panel, textvariable=self.group_folder_var, wraplength=1300).pack(anchor="w", pady=(6, 8))
        group_list_frame = ttk.Frame(self.groups_table_panel)
        group_list_frame.pack(fill="both", expand=True)
        self.group_file_list = ttk.Treeview(
            group_list_frame, columns=("animal", "file", "sessions", "trials", "group"), show="headings", height=5, selectmode="extended",
        )
        for key, label, width in (("animal", "Animal", 120), ("file", "PKL file", 400),
                                  ("sessions", "Sessions", 90), ("trials", "Trials", 90), ("group", "Group", 140)):
            self.group_file_list.heading(key, text=label)
            self.group_file_list.column(key, width=width, stretch=key == "file")
        group_scroll = ttk.Scrollbar(group_list_frame, orient="vertical", command=self.group_file_list.yview)
        self.group_file_list.configure(yscrollcommand=group_scroll.set)
        group_horizontal = ttk.Scrollbar(group_list_frame, orient="horizontal", command=self.group_file_list.xview)
        self.group_file_list.configure(xscrollcommand=group_horizontal.set)
        group_list_frame.columnconfigure(0, weight=1)
        group_list_frame.rowconfigure(0, weight=1)
        self.group_file_list.grid(row=0, column=0, sticky="nsew")
        group_scroll.grid(row=0, column=1, sticky="ns")
        group_horizontal.grid(row=1, column=0, sticky="ew")
        assignment_controls = ttk.Frame(groups_controls)
        assignment_controls.pack(fill="x", pady=(8, 0))
        ttk.Label(assignment_controls, text="Group:").pack(anchor="w")
        self.group_name_selector = ttk.Combobox(assignment_controls, textvariable=self.group_name_var, width=20)
        self.group_name_selector.pack(fill="x", pady=(3, 6))
        group_actions = ttk.Frame(assignment_controls)
        group_actions.pack(fill="x")
        group_actions.columnconfigure((0, 1), weight=1, uniform="group_actions")
        for index, (label, command) in enumerate((
            ("Assign to group", self._assign_selected_group),
            ("Remove assignment", self._remove_selected_group),
            ("Save assignments", self._save_group_assignments),
            ("Load assignments", self._load_group_assignments),
        )):
            ttk.Button(group_actions, text=label, command=command).grid(
                row=index // 2, column=index % 2, sticky="ew",
                padx=(0, 4) if index % 2 == 0 else (4, 0), pady=2,
            )
        ttk.Label(groups_controls, text="Select multiple files with Ctrl or Shift. Assignments are saved separately from PKL data.", wraplength=300).pack(anchor="w", pady=(5, 0))
        notebook.bind("<<NotebookTabChanged>>", self._select_gonogo_layout)

        ttk.Label(input_tab, text="Session input:").grid(
            row=0, column=0, sticky="w", padx=(0, 10)
        )

        browse_row = ttk.Frame(input_tab)
        browse_row.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        browse_row.columnconfigure((0, 1), weight=1, uniform="browse")
        browse_button = ttk.Button(
            browse_row, text="Browse FOLDER", command=self._browse_folder
        )
        browse_button.grid(row=0, column=1, sticky="ew", padx=(4, 0))

        browse_button2 = ttk.Button(
            browse_row, text="Browse NWB", command=self._browse_nwb
        )
        browse_button2.grid(row=0, column=0, sticky="ew", padx=(0, 4))

        self.trial_viewer_button = ttk.Button(
            input_tab,
            text="Trial viewer",
            command=self._open_trial_viewer,
            state="disabled",
        )
        self.trial_viewer_button.grid(row=3, column=0, sticky="ew", pady=(6, 0))
        input_tab.columnconfigure(0, weight=1)

        ttk.Label(input_tab, text="Hit source:").grid(
            row=4, column=0, sticky="w", pady=(10, 0), padx=(0, 10)
        )
        ttk.Radiobutton(
            input_tab,
            text="IR",
            variable=self.hit_source_var,
            value="IR",
            command=self._manual_hit_source,
        ).grid(row=5, column=0, sticky="w", pady=(4, 0))
        ttk.Radiobutton(
            input_tab,
            text="Licks",
            variable=self.hit_source_var,
            value="Licks",
            command=self._manual_hit_source,
        ).grid(row=6, column=0, sticky="w", pady=(4, 0))
        ttk.Label(input_tab, textvariable=self.hit_source_status_var, wraplength=300).grid(
            row=7, column=0, sticky="w", pady=(6, 0))

        ttk.Label(meta_tab, text="Animal name (override):").grid(
            row=2, column=0, sticky="w", pady=(10, 0)
        )
        animal_entry = ttk.Entry(meta_tab, textvariable=self.animal_var, width=30)
        animal_entry.grid(row=3, column=0, sticky="ew", pady=(4, 0))
        animal_entry.bind("<Return>", self._search_nwb_animal_override)
        ttk.Button(meta_tab, text="Search name", command=self._search_nwb_animal_override).grid(
            row=4, column=0, sticky="ew", pady=(6, 0)
        )
        search_buttons = ttk.Frame(meta_tab)
        search_buttons.grid(row=0, column=0, sticky="w")
        ttk.Button(
            search_buttons, text="Find NWB files", command=self._find_nwb_files_for_animal,
        ).pack(side="left")
        ttk.Button(
            search_buttons, text="Find folders", command=self._find_session_folders_for_animal,
        ).pack(side="left", padx=(8, 0))
        detected_animal_frame = ttk.Frame(meta_tab)
        detected_animal_frame.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        ttk.Label(detected_animal_frame, text="Detected animal:").pack(anchor="w")
        self.nwb_group_selector = ttk.Combobox(
            detected_animal_frame, textvariable=self.nwb_group_var, state="readonly", width=30,
        )
        self.nwb_group_selector.pack(side="left", fill="x", expand=True)
        self.nwb_group_selector.bind("<<ComboboxSelected>>", self._select_nwb_group)
        meta_tab.columnconfigure(0, weight=1)

        ttk.Label(controls_frame, text="Current session folder:").pack(anchor="w", pady=(8, 0))
        current_folder_label = ttk.Label(
            controls_frame,
            textvariable=self.current_folder_var,
            wraplength=300,
        )
        current_folder_label.pack(anchor="w")

        status_frame = ttk.Frame(controls_frame)
        status_frame.pack(fill="x", pady=(12, 10))
        ttk.Label(status_frame, text="Status:").pack(side="left")
        ttk.Label(status_frame, textvariable=self.status_var, wraplength=260).pack(side="left", padx=(6, 0))
        
        ttk.Label(controls_frame, text="Output").pack(anchor="w")
        self.output_text = scrolledtext.ScrolledText(
            controls_frame, wrap="word", width=32, height=6,
            font=("Consolas", 10),
        )
        self.output_text.pack(fill="both", expand=True, pady=(4, 0))
        self.output_text.configure(state="disabled")
        ttk.Label(right_frame, text="Plot").pack(anchor="w")

        self.main_canvas_figure = Figure(figsize=(6.5, 4.2), dpi=100)
        self.main_canvas_ax = self.main_canvas_figure.add_subplot(1, 1, 1)
        self.main_canvas_ax.set_facecolor("white")
        self.main_canvas_ax.set_xticks([])
        self.main_canvas_ax.set_yticks([])
        for spine in self.main_canvas_ax.spines.values():
            spine.set_visible(False)
        self.main_canvas_figure.tight_layout()
        self.main_canvas = FigureCanvasTkAgg(self.main_canvas_figure, master=right_frame)
        self.main_canvas_pick_cid = self.main_canvas.mpl_connect(
            "pick_event",
            self._handle_main_canvas_pick,
        )
        self.main_canvas.draw()
        self.main_canvas.get_tk_widget().pack(fill="both", expand=True)

        self.dmts_file_notebook = ttk.Notebook(self.dmts_tab, height=0)
        self.dmts_file_notebook.pack(fill="x")
        self.dmts_layout_split = ttk.Panedwindow(self.dmts_tab, orient="horizontal")
        self.dmts_layout_split.pack(fill="both", expand=True)
        dmts_controls = ttk.Frame(self.dmts_layout_split, width=360, padding=(0, 8, 10, 0))
        dmts_plot = ttk.Frame(self.dmts_layout_split, padding=(10, 8, 0, 0))
        self.dmts_layout_split.add(dmts_controls, weight=1)
        self.dmts_layout_split.add(dmts_plot, weight=3)
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
        self.dmts_mouse_folder_var = tk.StringVar(value="No mouse folder selected")
        self.dmts_scan_status_var = tk.StringVar(value="Choose a mouse folder")
        self.dmts_silent_match_var = tk.StringVar(value="5")
        self.dmts_show_engaged_var = tk.BooleanVar(value=False)
        self.dmts_animal_nwb_files = []
        self._dmts_folder_scan_cancel = None
        self._dmts_folder_scan_poll = None
        ttk.Button(dmts_animal_tab, text="Select mouse folder", command=self._browse_dmts_mouse_folder).pack(anchor="w")
        ttk.Label(dmts_animal_tab, textvariable=self.dmts_mouse_folder_var, wraplength=300).pack(
            anchor="w", pady=(6, 8))
        ttk.Label(dmts_animal_tab, textvariable=self.dmts_scan_status_var, wraplength=300).pack(anchor="w")
        ttk.Label(dmts_animal_tab, text="Silent match trials allowed before disengagement:", wraplength=300).pack(anchor="w", pady=(8, 0))
        ttk.Spinbox(dmts_animal_tab, from_=1, to=1000, textvariable=self.dmts_silent_match_var, width=8).pack(anchor="w")
        ttk.Label(dmts_animal_tab, text="5 starts marking at the 6th silent match. Rerun batch after changing.", wraplength=300).pack(anchor="w")
        ttk.Checkbutton(dmts_animal_tab, text="Show engaged-only performance", variable=self.dmts_show_engaged_var).pack(anchor="w")
        ttk.Label(dmts_animal_tab, text="Output").pack(anchor="w", pady=(8, 4))
        self.dmts_animal_output = scrolledtext.ScrolledText(
            dmts_animal_tab, wrap="word", width=32, height=12, font=("Consolas", 10), state="disabled")
        self.dmts_animal_output.pack(fill="both", expand=True)
        self.dmts_file_inner_notebook = ttk.Notebook(dmts_file_tab)
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
        ttk.Label(dmts_file_main, textvariable=self.dmts_file_var, wraplength=300).pack(
            anchor="w", pady=(6, 0))
        ttk.Label(dmts_file_main, text="Output").pack(anchor="w", pady=(10, 4))
        self.dmts_file_output = scrolledtext.ScrolledText(
            dmts_file_main, wrap="word", width=32, height=8, font=("Consolas", 10), state="disabled")
        self.dmts_file_output.pack(fill="both", expand=True)
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
        def select_dmts_subtab(_event=None):
            selected = self.dmts_file_notebook.select()
            for panel in dmts_panels.values():
                panel.pack_forget()
            dmts_panels[selected].pack(fill="both", expand=True)
            self._draw_dmts_canvas()
        self.dmts_file_notebook.bind("<<NotebookTabChanged>>", select_dmts_subtab)
        ttk.Label(dmts_plot, text="Plot").pack(anchor="w")
        self.dmts_canvas_figure = Figure(figsize=(6.5, 4.2), dpi=100)
        self.dmts_canvas_ax = self.dmts_canvas_figure.add_subplot(1, 1, 1)
        self.dmts_canvas_ax.set_facecolor("white")
        self.dmts_canvas_ax.set_xticks([])
        self.dmts_canvas_ax.set_yticks([])
        for spine in self.dmts_canvas_ax.spines.values():
            spine.set_visible(False)
        self.dmts_canvas_figure.tight_layout()
        self.dmts_canvas = FigureCanvasTkAgg(self.dmts_canvas_figure, master=dmts_plot)
        self._draw_dmts_canvas()
        self.dmts_canvas.mpl_connect("pick_event", self._handle_dmts_canvas_pick)
        self.dmts_canvas.draw()
        self.dmts_canvas.get_tk_widget().pack(fill="both", expand=True)

        # Debounce geometry events so divider drags produce readable console output.
        self._layout_report_job = None
        self._last_layout_sizes = None
        self.root.bind("<Configure>", self._queue_layout_size_report, add="+")
        self.layout_split.bind("<Configure>", self._queue_layout_size_report, add="+")
        controls_frame.bind("<Configure>", self._queue_layout_size_report, add="+")
        right_frame.bind("<Configure>", self._queue_layout_size_report, add="+")
        self.layout_split.bind("<ButtonRelease-1>", self._queue_layout_size_report, add="+")
        self.dmts_layout_split.bind("<ButtonRelease-1>", self._queue_layout_size_report, add="+")
        self.main_notebook.bind("<<NotebookTabChanged>>", self._queue_layout_size_report, add="+")
        self._queue_layout_size_report()

    def _select_gonogo_layout(self, _event=None) -> None:
        selected = self.notebook.select()
        for key, panel in self._gonogo_control_panels.items():
            if key == selected:
                panel.pack(fill="x")
            else:
                panel.pack_forget()
        panes = self.gonogo_vertical_split.panes()
        table_visible = str(self.groups_table_panel) in panes
        if selected == str(self.groups_tab) and not table_visible:
            self.gonogo_vertical_split.insert(0, self.groups_table_panel, weight=0)
            self.root.after_idle(self._restore_groups_table_height)
        elif selected != str(self.groups_tab) and table_visible:
            self._groups_table_height = self.gonogo_vertical_split.sashpos(0)
            self.gonogo_vertical_split.forget(self.groups_table_panel)
        self._draw_selected_input_box()

    def _restore_groups_table_height(self) -> None:
        if str(self.groups_table_panel) in self.gonogo_vertical_split.panes():
            height = self.gonogo_vertical_split.winfo_height()
            self.gonogo_vertical_split.sashpos(0, min(self._groups_table_height, max(100, height - 300)))

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
        if not hasattr(self, "dmts_canvas"):
            return
        ax = self.dmts_canvas_ax
        ax.clear()
        ax.axis("off")
        if self.dmts_file_notebook.select() == str(self.dmts_groups_tab):
            if self.dmts_group_exports:
                self._canvas_button(16, 16, "Plot group\naverages", "dmts_groups_plot", "#F3FAF1", "#59A14F", ax=ax)
        elif self.dmts_file_notebook.select() == str(self.dmts_animal_tab):
            if len(self.dmts_animal_nwb_files) > 1 and self._dmts_folder_scan_poll is None:
                ready = bool(self.dmts_batch_results) and not self._dmts_batch_running
                for x, y, label, action, enabled in (
                    (16, 16, "Running..." if self._dmts_batch_running else "Batch performance", "dmts_batch", not self._dmts_batch_running),
                    (182, 16, "Plot results", "dmts_batch_plot", ready),
                    (16, 82, "Save data", "dmts_batch_save", ready),
                ):
                    if action != "dmts_batch" and not ready:
                        continue
                    self._canvas_button(x, y, label, action, "#F3FAF1" if enabled else "#EEEEEE",
                                        "#59A14F" if enabled else "#AAAAAA", enabled=enabled, ax=ax)
        elif self.dmts_file_var.get():
            self._canvas_button(16, 16, "Running..." if self._dmts_file_busy else
                                "Loaded NWB file" if self._dmts_loaded else "Run NWB file",
                                "dmts_load", "#EEEEEE" if self._dmts_file_busy else "#F7FBFF" if self._dmts_loaded else "#F3FAF1",
                                "#AAAAAA" if self._dmts_file_busy else "#4C78A8" if self._dmts_loaded else "#59A14F",
                                enabled=not self._dmts_file_busy, ax=ax)
            actions = [(16, "Plot Time Window", "dmts_pretraining"),
                       (82, "Plot Trial-Aligned\nLicks", "dmts_matchonly"),
                       (148, "Plot Session\nRawdata", "dmts_summary")]
            if self._dmts_export_ready:
                actions.append((214, "Export results", "dmts_file_export"))
            for y, label, action in actions:
                if not self._dmts_loaded:
                    continue
                if action not in self._dmts_file_actions and action != "dmts_file_export":
                    continue
                enabled = not self._dmts_file_busy
                self._canvas_button(182, y, label, action, "#F3FAF1" if enabled else "#EEEEEE",
                                    "#59A14F" if enabled else "#AAAAAA", enabled=enabled, ax=ax)
        self.dmts_canvas.draw_idle()

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
        if event.artist.get_gid() == "dmts_groups_plot":
            self._plot_dmts_groups()
            return
        if event.artist.get_gid() == "dmts_batch":
            self._run_dmts_batch()
        elif event.artist.get_gid() == "dmts_batch_plot":
            self._plot_dmts_batch()
        elif event.artist.get_gid() == "dmts_batch_save":
            self._save_dmts_batch()
        if event.artist.get_gid() == "dmts_load":
            self._load_dmts_file()
            return
        actions = {"dmts_pretraining": self._run_dmts_pretraining,
                   "dmts_matchonly": self._run_dmts_matchonly,
                   "dmts_summary": self._open_dmts_summary,
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
                self._dmts_file_actions.intersection_update({"dmts_pretraining"})
                self._draw_dmts_canvas()

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
                session = load_session_data_fromFile(Path(filename)) if actions & {"dmts_matchonly", "dmts_summary"} else None
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
                    if all(f"acquisition/{name}/data" in handle for name in ("LeftLick", "RightLick")):
                        self._dmts_file_actions.add("dmts_matchonly")
        except Exception as exc:
            messagebox.showerror("Unable to read NWB file", str(exc), parent=self.root)
        self._draw_dmts_canvas()

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

    def _queue_layout_size_report(self, _event=None) -> None:
        if self._layout_report_job is not None:
            self.root.after_cancel(self._layout_report_job)
        self._layout_report_job = self.root.after(150, self._print_layout_sizes)

    def _print_layout_sizes(self) -> None:
        self._layout_report_job = None
        dmts_selected = self.main_notebook.select() == str(self.dmts_tab)
        split = self.dmts_layout_split if dmts_selected else self.layout_split
        canvas = self.dmts_canvas if dmts_selected else self.main_canvas
        pending_attr = "_dmts_initial_split_pending" if dmts_selected else "_initial_split_pending"
        if not split.winfo_ismapped():
            return
        panels = [self.root.nametowidget(name) for name in split.panes()]
        if getattr(self, pending_attr):
            setattr(self, pending_attr, False)
            available_width = sum(panel.winfo_width() for panel in panels)
            split.sashpos(0, round(available_width * 0.25))
            self._queue_layout_size_report()
            return
        widgets = [self.root, split, *panels, canvas.get_tk_widget()]
        sizes = tuple((widget.winfo_width(), widget.winfo_height()) for widget in widgets)
        if sizes == self._last_layout_sizes:
            return
        self._last_layout_sizes = sizes
        panel_width = sum(width for width, _height in sizes[2:4])
        parts = []
        for index, (label, (width, height)) in enumerate(zip(
            ("GUI", "Resizable area", "Left controls", "Right plot panel", "Canvas"), sizes
        )):
            share = f" ({width / panel_width:.1%})" if index in (2, 3) and panel_width else ""
            parts.append(f"{label}: {width} x {height} px{share}")
        print("[Layout] " + " | ".join(parts), flush=True)

    def _reset_session(self) -> None:
        self._single_input_selected = False
        # Ignore any worker results belonging to the previous selection.
        self._close_session_console()
        self.console_namespace = {}
        self.console_session = None
        self.scan_generation += 1
        self.is_running = False
        self._close_trial_viewer()
        for name in (
            "session_target_folder", "single_session_datadict", "single_session_performance",
            "single_session_hit_by_sound", "single_session_ir_events", "single_session_trial_ir_analysis",
        ):
            if hasattr(self, name):
                delattr(self, name)
        self.found_nwb_files = []
        self.found_session_folders = []
        self.batch_performance_by_file = {}
        self.batch_trial_performance_by_file = {}
        self.batch_trials_by_sound_id = {}
        self.batch_hit_by_sound = {}
        self.folder_var.set("")
        self.file_var.set("")
        self.animal_var.set("")
        self.status_var.set("Ready - choose a session")
        self.trial_viewer_button.configure(state="disabled")
        self.main_canvas_ax.clear()
        self.main_canvas_ax.set_xticks([])
        self.main_canvas_ax.set_yticks([])
        for spine in self.main_canvas_ax.spines.values():
            spine.set_visible(False)
        self.main_canvas.draw()

    def _browse_folder(self) -> None:
        initial_dir = self.folder_var.get() or "."
        self._reset_session()
        selected = filedialog.askdirectory(initialdir=initial_dir)
        if selected:
            self.active_input = "folder"
            if not self.hit_source_var.get():
                self.hit_source_var.set("IR")
            self.hit_source_status_var.set("Folder input: choose IR or Licks manually.")
            self._single_input_selected = True
            self.folder_var.set(selected)
            self._sync_current_input_label()
            self._draw_selected_input_box()

    def _browse_nwb(self):
        initial_dir = self.file_var.get() or "."
        self._reset_session()
        selected = filedialog.askopenfilename(
            initialdir=initial_dir,
            filetypes=[("NWB files", "*.nwb"), ("All files", "*.*")],
        )
        if selected:
            self.active_input = "file"
            self._single_input_selected = True
            self.file_var.set(selected)
            self._detect_nwb_hit_source(selected)
            self._sync_current_input_label()
            self._draw_selected_input_box()

    def _manual_hit_source(self):
        self.hit_source_status_var.set(f"Manual override: {self.hit_source_var.get()} (rerun to apply).")

    @staticmethod
    def _normalize_trigger_type(value):
        if isinstance(value, bytes):
            value = value.decode("utf-8", errors="replace")
        value = str(value).strip().casefold()
        return {"ir": "IR", "infrared": "IR", "irfork": "IR", "lick": "Licks", "licks": "Licks"}.get(value)

    def _detect_nwb_hit_source(self, filename):
        self.hit_source_var.set("")
        source = None
        detail = "TriggerType missing"
        try:
            import h5py
            with h5py.File(filename, "r") as handle:
                group = handle.get("acquisition/Parameters")
                if group is not None and "key" in group and "value" in group:
                    for key, value in zip(group["key"][:], group["value"][:]):
                        key = key.decode("utf-8", errors="replace") if isinstance(key, bytes) else str(key)
                        if key.strip().casefold().replace("_", "") == "triggertype":
                            source = self._normalize_trigger_type(value)
                            raw = value.decode("utf-8", errors="replace") if isinstance(value, bytes) else str(value)
                            detail = f"TriggerType={raw}"
                            break
        except (OSError, ValueError, TypeError) as exc:
            detail = f"Cannot read metadata: {exc}"
        if source:
            self.hit_source_var.set(source)
            message = f"Detected {source} ({detail}). Manual override available."
        else:
            message = f"Hit source unknown ({detail}). Select IR or Licks before running."
        self.hit_source_status_var.set(message)
        self._write_output(message + "\n")

    @staticmethod
    def _infer_animal_name_from_nwb_filename(nwb_path: Path) -> str | None:
        stem = Path(nwb_path).stem
        patterns = [
            r"(?:^|[_-])sub[_-]?([A-Za-z0-9]+)(?=$|[_-])",
            r"(?:^|[_-])(M\d+[A-Za-z0-9]*)(?=$|[_-])",
        ]
        for pattern in patterns:
            match = re.search(pattern, stem, flags=re.IGNORECASE)
            if match:
                return match.group(1)
        # Other common names: animal_session-1, animal_ses-2, animal_20260930.
        match = re.match(r"^(.+?)[_-](?:ses(?:sion)?[_-]?\d+|20\d{6})(?:[_-]|$)", stem, re.IGNORECASE)
        if match:
            return match.group(1)
        return None

    @classmethod
    def _group_nwb_files(cls, paths):
        groups = {}
        names = {}
        unidentified = []
        for path in sorted(paths):
            animal = cls._infer_animal_name_from_nwb_filename(path)
            if not animal:
                unidentified.append(path)
                continue
            canonical = names.setdefault(animal.casefold(), animal)
            groups.setdefault(canonical, []).append(path)
        return groups, unidentified

    def _select_nwb_group(self, _event=None) -> None:
        animal = self.nwb_group_var.get()
        files = self.nwb_groups.get(animal, [])
        if not files:
            return
        self._reset_session()
        self.animal_var.set(animal)
        self.found_nwb_files = list(files)
        self.active_input = "file"
        self.current_folder_var.set(f"Animal {animal} | {len(files)} NWB files")
        self.status_var.set(f"{animal}: {len(files)} NWB file(s) ready")
        self._write_output(f"Selected animal {animal}: {len(files)} NWB file(s).\n")
        for path in files:
            self._write_output(f"  {path}\n")
        self._draw_selected_input_box()

    def _search_nwb_animal_override(self, _event=None) -> None:
        animal = self.animal_var.get().strip()
        if not animal:
            messagebox.showinfo("Animal name", "Enter an animal name to search.")
            return
        if self.nwb_search_root is None:
            messagebox.showinfo("Choose a folder", "Click Find NWB files to scan a folder first, then search the animal name.")
            return
        # Search every scanned path, including files automatic detection could not identify.
        matches = [path for path in self.nwb_scanned_files
                   if animal.casefold() in str(path).casefold()]
        self._reset_session()
        self.animal_var.set(animal)
        self.nwb_group_var.set("")
        if not matches:
            self.status_var.set(f"No NWB files match {animal}")
            self._write_output(f"Manual search: no NWB files match '{animal}' under {self.nwb_search_root}.\n")
            return
        self.found_nwb_files = sorted(matches)
        self.active_input = "file"
        self.current_folder_var.set(f"Animal {animal} | {len(matches)} NWB files")
        self.status_var.set(f"Manual search: {animal}, {len(matches)} NWB file(s)")
        self._write_output(f"Manual name search '{animal}': {len(matches)} matching NWB paths.\n")
        for path in self.found_nwb_files:
            self._write_output(f"  {path}\n")
        self._draw_selected_input_box()

    def _find_nwb_files_for_animal(self) -> None:
        root_dir = filedialog.askdirectory(
            title="Choose a folder containing NWB sessions",
            initialdir=self.default_nwb_folder,
        )
        if not root_dir:
            return
        root_path = Path(root_dir)
        self._reset_session()
        self.nwb_groups = {}
        self.nwb_scanned_files = []
        self.nwb_search_root = None
        self.nwb_group_var.set("")
        self.nwb_group_selector.configure(values=())
        self.nwb_loading = True
        self.status_var.set("Loading ...")
        self._draw_selected_input_box()
        self.root.update_idletasks()
        try:
            paths = [path for path in root_path.rglob("*")
                     if path.is_file() and path.suffix.lower() == ".nwb"]
            groups, unidentified = self._group_nwb_files(paths)
        except OSError as exc:
            self.status_var.set("NWB search failed")
            messagebox.showerror("NWB search failed", str(exc))
            return
        finally:
            self.nwb_loading = False
            self._draw_selected_input_box()
        self.nwb_scanned_files = paths
        self.nwb_search_root = root_path
        self.nwb_groups = groups
        animals = sorted(groups, key=str.casefold)
        self.nwb_group_selector.configure(values=animals)
        self.nwb_group_var.set("")
        self._write_output(f"Scanned {root_path}: {len(paths)} NWB file(s), {len(groups)} animal group(s).\n")
        for animal in animals:
            self._write_output(f"  {animal}: {len(groups[animal])} file(s)\n")
        if unidentified:
            self._write_output("Animal could not be identified for these files (not included in Run All NWB):\n")
            for path in unidentified:
                self._write_output(f"  {path}\n")
        if animals:
            self.status_var.set(f"Found {len(animals)} animals - select an animal")
        else:
            self.status_var.set("No identifiable NWB animal groups found")
            messagebox.showinfo("No animal groups", "No identifiable NWB animal groups found. See Output for details.")
        self._draw_selected_input_box()

    def _find_session_folders_for_animal(self) -> None:
        animal_name = self.animal_var.get().strip()
        if not animal_name:
            messagebox.showerror("Missing animal name", "Please enter an animal name first.")
            return

        root_dir = filedialog.askdirectory(initialdir=self.folder_var.get() or ".")
        if not root_dir:
            return

        root_path = Path(root_dir)
        matching_folders = _find_session_folders_for_animal(root_path, animal_name)

        if not matching_folders:
            messagebox.showinfo(
                "No folders found",
                f"No raw session folders found for animal '{animal_name}' in:\n{root_path}",
            )
            self._write_output(
                f"No raw session folders found for animal '{animal_name}' under {root_path}\n"
            )
            return

        self.found_session_folders = matching_folders
        self.found_nwb_files = []
        self.active_input = "folder"
        self.current_folder_var.set(f"Animal {animal_name} | {len(matching_folders)} session folders")
        self._write_output(f"Found {len(self.found_session_folders)} session folder(s) for '{animal_name}'. \n")
        for folder in self.found_session_folders:
            self._write_output(str(folder) + "\n")
        self._draw_selected_input_box()

    def _run_all_found_nwb_files(self) -> None:
        if not self.found_nwb_files:
            messagebox.showerror(
                "No NWB files",
                "No NWB files in memory. Use 'Find NWB files' first.",
            )
            return

        self.batch_performance_by_file = {}
        self.batch_trial_performance_by_file = {}
        self.batch_trials_by_sound_id = {}
        self.batch_hit_by_sound = {}
        hit_source = self.hit_source_var.get()
        hit_by_sound_func = _get_hit_by_sound_func(hit_source)
        self._write_output("-----------------------------------\n")
        self._write_output(
            f"Running batch performance on {len(self.found_nwb_files)} NWB file(s)...\n"
        )
        self._write_output(f"Hit source: {hit_source}\n")

        for nwb_path in self.found_nwb_files:
            try:
                data_session_dict = load_session_data_fromFile(nwb_path)
                single_session_performance = extract_performance(data_session_dict)
                ir_events, trial_ir_analysis, single_hit_by_sound = analyze_session_responses(
                    data_session_dict, hit_source)
                session_key = str(nwb_path)
                self.batch_performance_by_file[session_key] = single_session_performance
                results_table = data_session_dict["ResultsTable"]
                trial_type = np.asarray(results_table["TrialType"], dtype=int)
                hit = np.asarray(results_table["Hit"], dtype=int)
                cr = np.asarray(results_table["CR"], dtype=int)
                correct = np.full(len(results_table), np.nan, dtype=float)
                correct[trial_type == 1] = hit[trial_type == 1]
                correct[trial_type == 2] = cr[trial_type == 2]
                if 'DMTSOutcome' in results_table:
                    outcome = results_table['DMTSOutcome']
                    correct = np.where(outcome.isin(['Hit', 'Correct']), 1.,
                                       np.where(outcome.isin(['Miss', 'FalseAlarm']), 0., np.nan))
                self.batch_trial_performance_by_file[session_key] = {
                    "trial_type": trial_type,
                    "correct": correct,
                }
                _append_trials_by_sound_id(
                    self.batch_trials_by_sound_id,
                    data_session_dict,
                    nwb_path,
                )
                _merge_hit_by_sound(self.batch_hit_by_sound, single_hit_by_sound)
                self._write_output(f"OK: {nwb_path.name} -> {single_session_performance}\n")
            except Exception as exc:
                self._write_output(f"ERROR: {nwb_path.name} -> {exc}\n")

        self._write_output(
            f"Batch finished. Stored {len(self.batch_performance_by_file)} performances.\n"
        )
        self._write_output("Trials grouped by SoundId across sessions:\n")
        for sound_id in sorted(self.batch_trials_by_sound_id):
            n_trials = len(self.batch_trials_by_sound_id[sound_id])
            self._write_output(f"  Sound {sound_id}: {n_trials} trial(s)\n")
        self._write_output("Hit by SoundId across sessions:\n")
        for sound_id in sorted(self.batch_hit_by_sound):
            stats = self.batch_hit_by_sound[sound_id]
            self._write_output(
                f"  Sound {sound_id}: {stats['n_FAs']}/{stats['n_trials']} "
                f"({stats['FAs_pct']:.2f}%)\n"
            )
        self._draw_selected_input_box()

    def _run_all_found_session_folders(self) -> None:
        if not self.found_session_folders:
            messagebox.showerror(
                "No folders",
                "No session folders in memory. Use 'Find folders' first.",
            )
            return

        self.batch_performance_by_file = {}
        self.batch_trial_performance_by_file = {}
        self.batch_trials_by_sound_id = {}
        self.batch_hit_by_sound = {}
        hit_source = self.hit_source_var.get()
        hit_by_sound_func = _get_hit_by_sound_func(hit_source)
        self._write_output("-----------------------------------\n")
        self._write_output(
            f"Running batch performance on {len(self.found_session_folders)} session folder(s)...\n"
        )
        self._write_output(f"Hit source: {hit_source}\n")

        for session_folder in self.found_session_folders:
            try:
                data_session_dict = load_session_data_fromFolder(session_folder)
                single_session_performance = extract_performance(data_session_dict)
                ir_events, trial_ir_analysis, single_hit_by_sound = analyze_session_responses(
                    data_session_dict, hit_source)
                session_key = str(session_folder)
                self.batch_performance_by_file[session_key] = single_session_performance
                results_table = data_session_dict["ResultsTable"]
                trial_type = np.asarray(results_table["TrialType"], dtype=int)
                hit = np.asarray(results_table["Hit"], dtype=int)
                cr = np.asarray(results_table["CR"], dtype=int)
                correct = np.full(len(results_table), np.nan, dtype=float)
                correct[trial_type == 1] = hit[trial_type == 1]
                correct[trial_type == 2] = cr[trial_type == 2]
                if 'DMTSOutcome' in results_table:
                    outcome = results_table['DMTSOutcome']
                    correct = np.where(outcome.isin(['Hit', 'Correct']), 1.,
                                       np.where(outcome.isin(['Miss', 'FalseAlarm']), 0., np.nan))
                self.batch_trial_performance_by_file[session_key] = {
                    "trial_type": trial_type,
                    "correct": correct,
                }
                _append_trials_by_sound_id(
                    self.batch_trials_by_sound_id,
                    data_session_dict,
                    session_folder,
                )
                _merge_hit_by_sound(self.batch_hit_by_sound, single_hit_by_sound)
                self._write_output(f"OK: {session_folder.name} -> {single_session_performance}\n")
            except Exception as exc:
                self._write_output(f"ERROR: {session_folder} -> {exc}\n")

        self._write_output(
            f"Batch finished. Stored {len(self.batch_performance_by_file)} performances.\n"
        )
        self._write_output("Trials grouped by SoundId across sessions:\n")
        for sound_id in sorted(self.batch_trials_by_sound_id):
            n_trials = len(self.batch_trials_by_sound_id[sound_id])
            self._write_output(f"  Sound {sound_id}: {n_trials} trial(s)\n")
        self._write_output("Hit by SoundId across sessions:\n")
        for sound_id in sorted(self.batch_hit_by_sound):
            stats = self.batch_hit_by_sound[sound_id]
            self._write_output(
                f"  Sound {sound_id}: {stats['n_FAs']}/{stats['n_trials']} "
                f"({stats['FAs_pct']:.2f}%)\n"
            )
        self._draw_selected_input_box()

    def _start_scan(self) -> None:
        if self.is_running:
            return
        folder_text = self.folder_var.get().strip()
        file_text = self.file_var.get().strip()

        target_folder = Path(folder_text) if folder_text else None
        target_file = Path(file_text) if file_text else None

        is_valid_folder = bool(
            target_folder is not None
            and target_folder.exists()
            and target_folder.is_dir()
        )
        is_valid_file = bool(
            target_file is not None
            and target_file.exists()
            and target_file.is_file()
            and target_file.suffix.lower() == ".nwb"
        )

        if not (is_valid_folder or is_valid_file):
            messagebox.showerror(
                "Invalid input",
                (
                    "Input must be an existing session folder or .nwb file."
                ),
            )
            return

        use_file = self.active_input == "file" and is_valid_file
        use_folder = self.active_input == "folder" and is_valid_folder
        if not (use_file or use_folder):
            # Fallback if active input is stale.
            use_file = is_valid_file
            use_folder = not use_file and is_valid_folder

        selected_path = target_file if use_file else target_folder

        if self.hit_source_var.get() not in ("IR", "Licks"):
            messagebox.showinfo("Hit source unknown", "Select IR or Licks before running the analysis.", parent=self.root)
            return

        self._set_running_state(True)
        self._sync_current_input_label()
        animal_name = self.animal_var.get().strip()
        self._write_output("-----------------------------------\n")
        if animal_name:
            self._write_output(f"Animal: {animal_name}\n")
        hit_source = self.hit_source_var.get()
        self._write_output(f"Hit source: {hit_source}\n")
        self._write_output(f"Starting scan for: {selected_path}\n")

        worker = threading.Thread(
            target=self._run_scan_worker,
            args=(selected_path, hit_source, self.scan_generation),
            daemon=True,
        )
        
        worker.start()

    def _deliver_scan_result(self, generation, callback, *args) -> None:
        if generation == self.scan_generation:
            callback(*args)

    def _run_scan_worker(self, target_path: Path, hit_source: str, generation: int) -> None:
        try:
            is_valid_folder = target_path.is_dir()
            is_valid_file = target_path.is_file() and target_path.suffix.lower() == ".nwb"
            print('_run_scan_worker', is_valid_folder, is_valid_file)

            if is_valid_folder:
                data_session_dict = load_session_data_fromFolder(target_path)
            elif is_valid_file:
                data_session_dict = load_session_data_fromFile(target_path)
            else:
                raise ValueError(f"Unsupported input: {target_path}")
            
            single_session_performance = extract_performance(data_session_dict)
            
            print('extract_performance ok')
            ir_events, trial_ir_analysis, hit_by_sound = analyze_session_responses(
                data_session_dict, hit_source)
            
            self.root.after(
                0,
                self._deliver_scan_result,
                generation,
                self._handle_scan_success,
                target_path,
                data_session_dict,
                single_session_performance,
                hit_by_sound,
                ir_events,
                trial_ir_analysis,
            )
        except Exception as exc:  # pragma: no cover - GUI error path
            self.root.after(0, self._deliver_scan_result, generation, self._handle_scan_error, target_path, exc)

    def _handle_scan_success(
        self,
        target_folder: Path,
        data_session_dict: dict,
        single_session_performance: dict,
        hit_by_sound: dict,
        ir_events: dict | None,
        trial_ir_analysis: dict | None,
    ) -> None:
        
        self.session_target_folder = target_folder
        self.single_session_datadict = data_session_dict
        self.single_session_performance = single_session_performance
        self.single_session_hit_by_sound = hit_by_sound
        self.single_session_ir_events = ir_events
        self.single_session_trial_ir_analysis = trial_ir_analysis

        self._write_output('nTrials: ' + str(data_session_dict['nTotalTrials']) + '\n')
        if trial_ir_analysis is not None:
            self._write_output(f"IR valid events: {len(ir_events['debut_fork'])}\n")
            self._write_output(f"Analyzed trials (IRxTrial): {trial_ir_analysis['n_analyzed_trials']}\n")
            self._write_output(f"Stay>={trial_ir_analysis['stay_threshold_ms']:g}ms at reward window "
                               f"(percIRFork={trial_ir_analysis['perc_ir_fork']:g}%): "
                               f"{trial_ir_analysis['pct_above_threshold']:.1f}%\n")
        elif 'dmts_analysis' in data_session_dict:
            dmts = data_session_dict['dmts_analysis']
            self._write_output(f"DMTS: dual-channel lick analysis; minimum {dmts['minimum']} lick(s).\n")
            self._write_output(f"Match: {single_session_performance['n_go']}; nonmatch: {single_session_performance['n_nogo']}; blank: {single_session_performance['n_blank']}.\n")
            self._write_output(f"Recalculated / saved outcome differences: {dmts['mismatch_count']}.\n")
            if dmts['missing_channels']:
                self._write_output("Missing channels: " + ', '.join(dmts['missing_channels']) + ".\n")
            if dmts['saved_fallback_count']:
                self._write_output(f"Using saved outcomes for {dmts['saved_fallback_count']} trials without complete dual-channel data.\n")
            self._write_output("Trial timing uses recorded sound onset or coarse trial markers plus protocol durations.\n")
        else:
            self._write_output("Licks: counting signal events; IR occupancy analysis skipped.\n")
        if hit_by_sound:
            self._write_output("DMTS accuracy by test SoundId:\n" if 'dmts_analysis' in data_session_dict else "Hit by SoundId:\n")
            for sid, stats in hit_by_sound.items():
                self._write_output(
                    f"  Sound {sid}: {stats['n_FAs']}/{stats['n_trials']} "
                    f"({stats['FAs_pct']:.2f}%)\n"
                )
        self._draw_selected_input_box()
        if self.trial_viewer_button is not None:
            self.trial_viewer_button.configure(state="normal")
        if self.trial_viewer_window is not None and self.trial_viewer_window.winfo_exists():
            self._render_trial_viewer_plot()
        self._finish_scan(target_folder)

    def _handle_scan_error(self, target_folder: Path, exc: Exception) -> None:
        self._write_output(f"Error while scanning {target_folder}: {exc}\n")
        messagebox.showerror("Scan error", f"Could not process folder:\n{target_folder}\n\n{exc}")
        self._finish_scan(target_folder)

    def _finish_scan(
        self,
        target_folder: Path) -> None:
        
        self._set_running_state(False)
        self.status_var.set(f"Done: {target_folder.name}")

    def _sync_current_input_label(self) -> None:
        folder_text = self.folder_var.get().strip()
        file_text = self.file_var.get().strip()

        if self.active_input == "file":
            if file_text:
                self.current_folder_var.set(f"NWB | {file_text}")
            elif folder_text:
                self.current_folder_var.set(f"Folder | {folder_text}")
            else:
                self.current_folder_var.set("(none)")
            return

        if folder_text:
            self.current_folder_var.set(f"Folder | {folder_text}")
        elif file_text:
            self.current_folder_var.set(f"NWB | {file_text}")
        else:
            self.current_folder_var.set("(none)")
        
    def _set_running_state(self, is_running: bool) -> None:
        self.is_running = is_running
        self._draw_selected_input_box()
        if self.trial_viewer_button is not None:
            has_session = hasattr(self, "single_session_datadict")
            state = "disabled" if is_running or not has_session else "normal"
            self.trial_viewer_button.configure(state=state)
        if is_running:
            self.status_var.set("Running...")
        self.root.update_idletasks()

    def _write_output(self, text: str) -> None:
        self.output_text.configure(state="normal")
        self.output_text.insert("end", text)
        self.output_text.see("end")
        self.output_text.configure(state="disabled")
        self.root.update_idletasks()

    # Visualizations 
    @staticmethod
    def _read_group_export(path):
        with Path(path).open("rb") as stream:
            payload = pickle.load(stream)
        required = {"schema_version", "animal_name", "performance_by_file",
                    "trial_performance_by_file", "trials_by_sound_id", "hit_by_sound", "rolling_trial_data"}
        if not isinstance(payload, dict) or not required.issubset(payload):
            raise ValueError("Not a batch export from this GUI")
        if payload["schema_version"] != 1:
            raise ValueError("Unsupported batch export version")
        if not isinstance(payload["performance_by_file"], dict):
            raise ValueError("Invalid session performance data")
        rolling = payload["rolling_trial_data"]
        if not isinstance(rolling, dict) or "trial_index" not in rolling:
            raise ValueError("Missing rolling trial data")
        return payload

    def _load_group_folder(self) -> None:
        selected = filedialog.askdirectory(
            title="Select a folder containing batch PKL exports",
            initialdir=str(self.group_folder) if self.group_folder else ".",
        )
        if not selected:
            return
        folder = Path(selected)
        self.group_exports = {}
        self.group_assignments = {}
        self.group_name_var.set("")
        self.group_name_selector.configure(values=())
        self.group_folder = folder
        self.group_folder_var.set(str(folder))
        for item in self.group_file_list.get_children():
            self.group_file_list.delete(item)
        self.groups_loading = True
        self._draw_selected_input_box()
        self.root.update_idletasks()
        failures = 0
        try:
            paths = sorted(path for path in folder.iterdir()
                           if path.is_file() and path.suffix.lower() == ".pkl")
            for path in paths:
                try:
                    payload = self._read_group_export(path)
                    n_trials = len(payload["rolling_trial_data"]["trial_index"])
                    n_sessions = len(payload["performance_by_file"])
                    self.group_exports[str(path)] = payload
                    self.group_file_list.insert("", "end", iid=str(path), values=(payload["animal_name"], path.name, n_sessions, n_trials, "Unassigned"))
                    self._write_output(f"Loaded PKL: {path.name} | animal {payload['animal_name']} | {n_sessions} sessions | {n_trials} trials\n")
                except Exception as exc:
                    failures += 1
                    self._write_output(f"Skipped PKL {path.name}: {exc}\n")
            self.status_var.set(f"Groups: {len(self.group_exports)} PKL files loaded; {failures} skipped")
            self._write_output(f"Groups folder: {folder} | {len(self.group_exports)} files loaded; {failures} skipped.\n")
        except OSError as exc:
            self.status_var.set("Groups folder could not be read")
            messagebox.showerror("Folder load failed", str(exc), parent=self.root)
        finally:
            self.groups_loading = False
            self._draw_selected_input_box()

    def _refresh_group_assignments(self):
        for key in self.group_exports:
            self.group_file_list.set(key, "group", self.group_assignments.get(key, "Unassigned"))
        self.group_name_selector.configure(values=sorted(set(self.group_assignments.values()), key=str.casefold))
        self._draw_selected_input_box()

    def _assign_selected_group(self):
        selection = self.group_file_list.selection()
        name = self.group_name_var.get().strip()
        if not selection or not name or name.casefold() == "unassigned":
            messagebox.showinfo("Assign group", "Select files and enter a group name other than Unassigned.", parent=self.root)
            return
        name = next((existing for existing in self.group_assignments.values()
                     if existing.casefold() == name.casefold()), name)
        for key in selection:
            self.group_assignments[key] = name
        self._refresh_group_assignments()
        self._write_output(f"Assigned {len(selection)} PKL file(s) to {name}. Save group assignments to keep these changes.\n")

    def _remove_selected_group(self):
        for key in self.group_file_list.selection():
            self.group_assignments.pop(key, None)
        self._refresh_group_assignments()

    def _save_group_assignments(self):
        if self.group_folder is None or not self.group_exports:
            messagebox.showinfo("Groups", "Load a PKL folder first.", parent=self.root)
            return
        filename = filedialog.asksaveasfilename(parent=self.root, title="Save group assignments",
            initialdir=str(self.group_folder), initialfile="group_assignments.json",
            defaultextension=".json", filetypes=[("JSON files", "*.json")])
        if not filename:
            return
        try:
            data = {"schema_version": 1, "assignments": {
                Path(key).relative_to(self.group_folder).as_posix(): self.group_assignments.get(key)
                for key in self.group_exports}}
            Path(filename).write_text(json.dumps(data, indent=2), encoding="utf-8")
        except (OSError, ValueError) as exc:
            messagebox.showerror("Save failed", str(exc), parent=self.root)
            return
        self._write_output(f"Saved group assignments: {filename}\n")

    def _load_group_assignments(self):
        if self.group_folder is None or not self.group_exports:
            messagebox.showinfo("Groups", "Load a PKL folder first.", parent=self.root)
            return
        filename = filedialog.askopenfilename(parent=self.root, title="Load group assignments",
            initialdir=str(self.group_folder), filetypes=[("JSON files", "*.json")])
        if not filename:
            return
        try:
            data = json.loads(Path(filename).read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("schema_version") != 1 or not isinstance(data.get("assignments"), dict):
                raise ValueError("Invalid group assignments file")
            mapping = data["assignments"]
            if any(value is not None and (not isinstance(value, str) or not value.strip() or value.casefold() == "unassigned") for value in mapping.values()):
                raise ValueError("Each assignment must be a group name or null")
            known = {Path(key).relative_to(self.group_folder).as_posix(): key for key in self.group_exports}
            loaded = {known[name]: group.strip() for name, group in mapping.items() if name in known and group is not None}
        except (OSError, ValueError) as exc:
            messagebox.showerror("Load failed", str(exc), parent=self.root)
            return
        self.group_assignments = loaded
        self._refresh_group_assignments()
        self._write_output(f"Loaded {len(loaded)} assignments; {len(set(mapping) - set(known))} file(s) absent from this folder.\n")

    def _open_group_average_plot(self):
        try:
            from behavior_plots import plot_group_average_performance
            figure = plot_group_average_performance(self.group_exports, self.group_assignments,
                                                    plot_layout=self.preferences.get("plot_layout", {}))
            if figure is None:
                messagebox.showinfo("Group averages", "Assign files with trial data to a group first.", parent=self.root)
                return
            self._write_output("Opened group averages: grey individual animals, colored group means; aligned by cumulative trial index. Multiple exports per animal are averaged first.\n")
        except (ValueError, KeyError, TypeError) as exc:
            messagebox.showerror("Group plot unavailable", str(exc), parent=self.root)

    def _canvas_button(self, x, y, label, action, facecolor, edgecolor, enabled=True, ax=None):
        """Draw a 150 x 50 display-pixel button, anchored to the axes' top left."""
        ax = self.main_canvas_ax if ax is None else ax
        transform = Affine2D().scale(1, -1) + ScaledTranslation(0, 1, ax.transAxes)
        button = Rectangle((x, y), 150, 50, transform=transform,
                           facecolor=facecolor, edgecolor=edgecolor,
                           linewidth=1, picker=enabled)
        button.set_gid(action)
        ax.add_patch(button)
        ax.text(x + 75, y + 25, label, transform=transform,
                ha="center", va="center", fontsize=8, fontweight="bold",
                color="#222222")
        return button

    def _draw_groups_canvas(self) -> None:
        ax = self.main_canvas_ax
        ax.clear()
        ax.axis("off")
        if self.groups_loading:
            text = "Loading ..."
        elif self.group_exports:
            summary = {}
            for key, payload in self.group_exports.items():
                group = self.group_assignments.get(key, "Unassigned")
                row = summary.setdefault(group, {"files": 0, "animals": set()})
                row["files"] += 1
                animal = str(payload.get("animal_name", "")).strip()
                if animal:
                    row["animals"].add(animal.casefold())
            rows = [[group, item["files"], len(item["animals"])] for group, item in sorted(summary.items())]
            table = ax.table(cellText=rows, colLabels=["Group", "PKL files", "Unique animals"],
                             bbox=[0.10, 0.90 - min(0.40, 0.065 * (len(rows) + 1)),
                                   0.80, min(0.40, 0.065 * (len(rows) + 1))], cellLoc="center")
            table.auto_set_font_size(False)
            table.set_fontsize(9)
            ax.set_title("Group assignments", loc="left")
            if self.group_assignments:
                self._canvas_button(16, min(300, max(16, ax.bbox.height - 60)), "Plot group\naverages", "plot_group_averages",
                                    "#F3FAF1", "#59A14F")
            self.main_canvas.draw()
            return
        else:
            text = "Select a folder containing batch PKL exports."
        ax.text(0.5, 0.5, text, ha="center", va="center", fontsize=13, transform=ax.transAxes, wrap=True)
        self.main_canvas.draw()

    def _draw_animal_canvas(self) -> None:
        ax = self.main_canvas_ax
        ax.clear()
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis("off")
        if self.nwb_loading:
            ax.text(0.5, 0.5, "Loading ...", ha="center", va="center",
                    fontsize=16, fontweight="bold", transform=ax.transAxes)
            self.main_canvas.draw()
            return
        files = self.found_nwb_files
        folders = self.found_session_folders
        if not files and not folders:
            ax.text(0.06, 0.88, "Select an animal from Detected animal to begin." if self.nwb_groups else "Find sessions and select an animal to begin.",
                    transform=ax.transAxes, fontsize=11, wrap=True)
        else:
            label = "Run All NWB Files" if files else "Run All Folders"
            action = "run_all_nwb" if files else "run_all_folders"
            label = "Run all NWB\nfiles" if files else "Run all\nfolders"
            self._canvas_button(16, 16, label, action, "#F3FAF1", "#59A14F")
            if self.batch_performance_by_file:
                self._canvas_button(182, 16, "Plot Batch\nPerformance", "plot_batch_session_performance",
                                    "#F3FAF1", "#59A14F")
                self._canvas_button(16, 82, "Export batch\ndata (.pkl)", "export_batch_data",
                                    "#F3FAF1", "#59A14F")
        self.main_canvas.draw()

    def _draw_selected_input_box(self) -> None:
        if self.main_canvas_ax is None or self.main_canvas is None:
            return

        if self.notebook.select() == str(self.groups_tab):
            self._draw_groups_canvas()
            return
        if self.notebook.select() == str(self.animal_tab):
            self._draw_animal_canvas()
            return
        self.main_canvas_ax.set_axis_on()
        if not self._single_input_selected or (not self.file_var.get().strip() and not self.folder_var.get().strip()):
            self.main_canvas_ax.clear()
            self.main_canvas_ax.axis("off")
            self.main_canvas.draw()
            return

        if self.active_input == "file":
            selected_path = Path(self.file_var.get().strip())
            input_label = "NWB file"
        else:
            selected_path = Path(self.folder_var.get().strip())
            input_label = "Folder"

        if self.active_input == "file" and self.found_nwb_files:
            n_files = len(self.found_nwb_files)
            display_name = f"{n_files} NWB file" + ("" if n_files == 1 else "s") + " found"
        elif self.active_input == "folder" and self.found_session_folders:
            n_folders = len(self.found_session_folders)
            display_name = f"{n_folders} session folder" + ("" if n_folders == 1 else "s") + " found"
        else:
            display_name = selected_path.name or str(selected_path)

        ax = self.main_canvas_ax
        ax.clear()
        ax.set_facecolor("white")
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_visible(False)

        loaded_nwb = self.active_input == "file" and hasattr(self, "single_session_datadict")
        run_label = "Loaded NWB file" if loaded_nwb else f"Run {input_label}"
        self._canvas_button(16, 16, "Running..." if self.is_running else run_label,
                            "run_session", "#EEEEEE" if self.is_running else "#F7FBFF" if loaded_nwb else "#F3FAF1",
                            "#AAAAAA" if self.is_running else "#4C78A8" if loaded_nwb else "#59A14F",
                            enabled=not self.is_running)
        if hasattr(self, "single_session_datadict"):
            self._canvas_button(16, 82, "Session\nvariables", "session_console", "#F3FAF1", "#59A14F")
            self._canvas_button(182, 16, "IR occupancy", "plot_ir_occupancy_by_sound", "#F3FAF1", "#59A14F")
            self._canvas_button(182, 82, "Performance", "plot_performance", "#F3FAF1", "#59A14F")
            self._canvas_button(182, 148, "Hit by sound", "plot_hit_by_sound", "#F3FAF1", "#59A14F")
        self.main_canvas.draw()

    def _handle_main_canvas_pick(self, event) -> None:
        if event.artist.get_gid() == "run_all_nwb":
            self._run_all_found_nwb_files()
        elif event.artist.get_gid() == "run_all_folders":
            self._run_all_found_session_folders()
        elif event.artist.get_gid() == "plot_group_averages":
            self._open_group_average_plot()
        elif event.artist.get_gid() == "export_batch_data":
            self._export_batch_data()
        elif event.artist.get_gid() == "run_session":
            if self.notebook.select() != str(self.animal_tab):
                self._start_scan()
        elif event.artist.get_gid() == "session_console":
            self._open_session_console()
        elif event.artist.get_gid() == "plot_ir_occupancy_by_sound":
            self._open_ir_occupancy_plot()
        elif event.artist.get_gid() == "plot_performance":
            self._open_performance_plot()
        elif event.artist.get_gid() == "plot_hit_by_sound":
            self._open_hit_by_sound_plot()
        elif event.artist.get_gid() == "plot_batch_session_performance":
            self._open_batch_session_performance_plot()

    def _close_session_console(self) -> None:
        if self.console_window is not None and self.console_window.winfo_exists():
            self.console_window.destroy()
        self.console_window = None

    def _open_session_console(self) -> None:
        if not hasattr(self, "single_session_datadict"):
            return
        if self.console_window is not None and self.console_window.winfo_exists():
            self.console_window.deiconify()
            self.console_window.lift()
            return
        window = tk.Toplevel(self.root)
        self.console_window = window
        window.title("Session variables - Python console")
        window.geometry("720x380")
        window.minsize(480, 260)
        window.protocol("WM_DELETE_WINDOW", self._close_session_console)
        frame = ttk.Frame(window, padding=14)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Inspect the loaded session", font=("Segoe UI", 13, "bold")).pack(anchor="w")
        ttk.Label(frame, text="Write Python below, then click Execute. Results appear in Output.").pack(anchor="w", pady=(4, 8))
        self.console_input = scrolledtext.ScrolledText(frame, wrap="none", font=("Consolas", 11), height=8)
        self.console_input.pack(fill="both", expand=True)
        self.console_input.insert("1.0", "print(single_session_datadict.keys())")
        ttk.Label(frame, text="Commands run as Python and can modify session data and files.").pack(anchor="w", pady=(8, 4))
        controls = ttk.Frame(frame)
        controls.pack(fill="x")
        ttk.Button(controls, text="Execute", command=self._execute_session_command).pack(side="left")
        ttk.Button(controls, text="Close", command=self._close_session_console).pack(side="right")
        self.console_input.focus_set()

    def _execute_session_command(self) -> None:
        if self.is_running or not hasattr(self, "single_session_datadict"):
            self._write_output("Console: load a session and wait for analysis to finish first.\n")
            return
        source = self.console_input.get("1.0", "end-1c").strip()
        if not source:
            return
        if self.console_session is not self.single_session_datadict:
            self.console_namespace = {"np": np, "__name__": "__session_console__"}
            self.console_session = self.single_session_datadict
        for name in (
            "single_session_datadict", "single_session_performance", "single_session_hit_by_sound",
            "single_session_ir_events", "single_session_trial_ir_analysis",
        ):
            self.console_namespace[name] = getattr(self, name)
        self._write_output("\n>>> " + source.replace("\n", "\n... ") + "\n")
        captured = io.StringIO()
        with redirect_stdout(captured), redirect_stderr(captured):
            try:
                tree = ast.parse(source, filename="<session console>", mode="exec")
                # Display a final expression, as in an interactive Python console.
                expression = tree.body.pop() if tree.body and isinstance(tree.body[-1], ast.Expr) else None
                exec(compile(tree, "<session console>", "exec"), self.console_namespace)
                if expression is not None:
                    result = eval(compile(ast.Expression(expression.value), "<session console>", "eval"), self.console_namespace)
                    if result is not None:
                        print(repr(result))
            except BaseException:
                traceback.print_exc()
        self._write_output(captured.getvalue() or "Command completed (no output).\n")

    def _open_ir_occupancy_plot(self) -> None:
        if not hasattr(self, "single_session_datadict"):
            messagebox.showinfo(
                "No session loaded",
                "Run a session before opening the IR occupancy plot.",
            )
            return

        from behavior_plots import plot_ir_occupancy_by_sound

        fig = plot_ir_occupancy_by_sound(
            self.single_session_datadict,
            self.single_session_trial_ir_analysis,
            plot_layout=self.preferences.get("plot_layout", {}),
            show=True,
            block=False,
        )
        if fig is None:
            messagebox.showinfo(
                "No IR occupancy",
                "No IR occupancy data are available for this session.",
            )
            return
        self._write_output("Opened IR occupancy by sound plot.\n")

    def _open_performance_plot(self) -> None:
        if not hasattr(self, "single_session_datadict"):
            messagebox.showinfo(
                "No session loaded",
                "Run a session before opening the performance plot.",
            )
            return

        from behavior_plots import plot_performance

        plot_performance(
            self.single_session_performance,
            self.single_session_datadict,
            trial_ir_analysis=self.single_session_trial_ir_analysis,
            plot_layout=self.preferences.get("plot_layout", {}),
            show=True,
            block=False,
        )
        self._write_output("Opened performance plot.\n")

    def _open_hit_by_sound_plot(self) -> None:
        if not hasattr(self, "single_session_hit_by_sound"):
            messagebox.showinfo(
                "No session loaded",
                "Run a session before opening the hit-by-sound plot.",
            )
            return

        from behavior_plots import plot_hit_by_sound

        fig = plot_hit_by_sound(
            self.single_session_hit_by_sound,
            show=True,
            block=False,
        )
        if fig is None:
            messagebox.showinfo(
                "No hit-by-sound data",
                "No hit-by-sound data are available for this session.",
            )
            return
        self._write_output("Opened hit by sound plot.\n")

    def _export_batch_data(self) -> None:
        if not self.batch_performance_by_file:
            return
        filename = filedialog.asksaveasfilename(
            parent=self.root, title="Export batch analysis",
            defaultextension=".pkl", filetypes=[("Pickle files", "*.pkl")],
            initialfile=f"{_safe_name(self.animal_var.get() or 'animal')}_batch_analysis.pkl",
        )
        if not filename:
            return
        try:
            from behavior_plots import batch_rolling_trial_data
            payload = {
                "schema_version": 1,
                "animal_name": self.animal_var.get(),
                "performance_by_file": self.batch_performance_by_file,
                "trial_performance_by_file": self.batch_trial_performance_by_file,
                "trials_by_sound_id": self.batch_trials_by_sound_id,
                "hit_by_sound": self.batch_hit_by_sound,
                "rolling_trial_data": batch_rolling_trial_data(
                    self.batch_performance_by_file, self.batch_trial_performance_by_file, window=25),
            }
            with Path(filename).open("wb") as output:
                pickle.dump(payload, output, protocol=pickle.HIGHEST_PROTOCOL)
        except Exception as exc:
            self._write_output(f"Batch export failed: {exc}\n")
            messagebox.showerror("Export failed", str(exc), parent=self.root)
            return
        self._write_output(f"Exported batch data and 25-trial rolling averages to: {filename}\n")

    def _open_batch_session_performance_plot(self) -> None:
        if not self.batch_performance_by_file:
            messagebox.showinfo(
                "No batch data",
                "Run all NWB files for one animal before opening the batch performance plot.",
            )
            return

        from behavior_plots import plot_batch_session_performance

        fig = plot_batch_session_performance(
            self.batch_performance_by_file,
            trial_performance_by_file=self.batch_trial_performance_by_file,
            plot_layout=self.preferences.get("plot_layout", {}),
            show=True,
            block=False,
        )
        if fig is None:
            messagebox.showinfo(
                "No batch performance",
                "No valid batch performance data are available.",
            )
            return
        self._write_output("Opened batch performance plot.\n")

    def _open_trial_viewer(self) -> None:
        if not hasattr(self, "single_session_datadict"):
            messagebox.showinfo(
                "No session loaded",
                "Run a session first, then open the trial viewer.",
            )
            return

        if self.trial_viewer_window is not None and self.trial_viewer_window.winfo_exists():
            self.trial_viewer_window.lift()
            return

        self.trial_viewer_window = tk.Toplevel(self.root)
        self.trial_viewer_window.title("Trial viewer")
        self.trial_viewer_window.geometry("760x920")
        self.trial_viewer_window.protocol("WM_DELETE_WINDOW", self._close_trial_viewer)

        controls = ttk.Frame(self.trial_viewer_window, padding=10)
        controls.pack(fill="x")
        trial_row = ttk.Frame(controls)
        trial_row.pack(fill="x")
        nav_row = ttk.Frame(controls)
        nav_row.pack(fill="x", pady=(8, 0))

        ttk.Label(trial_row, text="Trial index:").pack(side="left", padx=(0, 4))
        self.trial_index_var = tk.StringVar(value="0")
        trial_entry = ttk.Entry(trial_row, textvariable=self.trial_index_var, width=8)
        trial_entry.pack(side="left")
        trial_entry.bind("<Return>", lambda _event: self._render_trial_viewer_plot())
        ttk.Button(trial_row, text="Go", command=self._render_trial_viewer_plot).pack(
            side="left", padx=(6, 0)
        )
        ttk.Button(nav_row, text="Previous", command=lambda: self._change_trial(-1)).pack(
            side="left"
        )
        ttk.Button(nav_row, text="Next", command=lambda: self._change_trial(1)).pack(
            side="left", padx=(6, 0)
        )
        self.trial_viewer_status_var = tk.StringVar(value="")
        ttk.Label(nav_row, textvariable=self.trial_viewer_status_var).pack(
            side="left", padx=(14, 0)
        )

        self.trial_plot_frame = ttk.Frame(self.trial_viewer_window, padding=(10, 0, 10, 10))
        self.trial_plot_frame.pack(fill="both", expand=True)
        self._render_trial_viewer_plot()

    def _close_trial_viewer(self) -> None:
        if self.trial_viewer_figure is not None:
            plt.close(self.trial_viewer_figure)
        self.trial_viewer_figure = None
        self.trial_viewer_canvas = None
        if self.trial_viewer_window is not None:
            self.trial_viewer_window.destroy()
        self.trial_viewer_window = None

    def _trial_count(self) -> int:
        if 'dmts_analysis' in self.single_session_datadict:
            return len(self.single_session_datadict['dmts_analysis']['trials'])
        data_trial_id = np.asarray(self.single_session_datadict["trialID"]["full"])
        return int((data_trial_id == 99).sum())

    def _get_trial_index_from_viewer(self) -> int:
        max_index = max(self._trial_count() - 1, 0)
        try:
            trial_index = int(self.trial_index_var.get())
        except (TypeError, ValueError):
            trial_index = 0
        trial_index = min(max(trial_index, 0), max_index)
        self.trial_index_var.set(str(trial_index))
        return trial_index

    def _change_trial(self, delta: int) -> None:
        current_index = self._get_trial_index_from_viewer()
        max_index = max(self._trial_count() - 1, 0)
        next_index = min(max(current_index + delta, 0), max_index)
        self.trial_index_var.set(str(next_index))
        self._render_trial_viewer_plot()

    def _render_trial_viewer_plot(self) -> None:
        if self.trial_plot_frame is None:
            return

        from behavior_plots import plot_trial_ir_and_sound

        trial_index = self._get_trial_index_from_viewer()
        if self.trial_viewer_canvas is not None:
            self.trial_viewer_canvas.get_tk_widget().destroy()
            self.trial_viewer_canvas = None
        if self.trial_viewer_figure is not None:
            plt.close(self.trial_viewer_figure)
            self.trial_viewer_figure = None

        self.trial_viewer_figure = plot_trial_ir_and_sound(
            self.single_session_datadict,
            trial_ir_analysis=self.single_session_trial_ir_analysis,
            ir_events=self.single_session_ir_events,
            trial_index=trial_index,
            result_fields=["TrialsId", "SoundId", "TrialType", "Hit", "Miss", "CR", "FA"],
            show=False,
            block=False,
        )
        self.trial_viewer_canvas = FigureCanvasTkAgg(
            self.trial_viewer_figure,
            master=self.trial_plot_frame,
        )
        self.trial_viewer_canvas.draw()
        self.trial_viewer_canvas.get_tk_widget().pack(fill="both", expand=True)
        if self.trial_viewer_status_var is not None:
            self.trial_viewer_status_var.set(
                f"Showing {trial_index} / {max(self._trial_count() - 1, 0)}"
            )

    def _update_plots(self) -> None:
        plot_session_visualizations = _get_plot_session_visualizations(force_agg=False)
        plot_session_visualizations(
            self.single_session_datadict,
            self.single_session_performance,
            self.single_session_ir_events,
            self.single_session_trial_ir_analysis,
            hit_by_sound=getattr(self, "single_session_hit_by_sound", None),
            show=True,
            block=False,
        )

def _safe_name(text: str) -> str:
    return "".join(char if char.isalnum() else "_" for char in text).strip("_")


def _to_json_key(key):
    key = _to_builtin(key)
    if isinstance(key, (str, int, float, bool)) or key is None:
        return key
    return str(key)


def _to_builtin(value):
    if isinstance(value, dict):
        return {_to_json_key(key): _to_builtin(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_builtin(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (bytes, bytearray)):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return value.hex()
    if hasattr(value, "to_dict"):
        try:
            if hasattr(value, "columns"):
                return _to_builtin(value.to_dict(orient="records"))
            return _to_builtin(value.to_dict())
        except TypeError:
            pass
    if hasattr(value, "item"):
        return _to_builtin(value.item())
    if isinstance(value, float) and value != value:
        return None
    return value


def _get_hit_by_sound_func(hit_source: str):
    if hit_source == "Licks":
        return extract_hit_by_sound_licks
    return extract_hit_by_sound_IR


def _get_session_date(data_session_dict: dict, source_path: Path) -> str:
    parameters = data_session_dict.get("parameters", {})
    if isinstance(parameters, dict):
        return str(parameters.get("date", source_path.stem))
    if hasattr(parameters, "columns") and "date" in parameters.columns:
        try:
            return str(parameters["date"].iloc[0])
        except Exception:
            pass
    if source_path.parent.name:
        return source_path.parent.name
    try:
        return str(parameters["date"])
    except Exception:
        return source_path.stem


def _append_trials_by_sound_id(
    trials_by_sound_id: dict[int, list[dict]],
    data_session_dict: dict,
    source_path: Path,
) -> None:
    results_table = data_session_dict.get("ResultsTable")
    if results_table is None or results_table.empty:
        return

    session_date = _get_session_date(data_session_dict, source_path)
    for trial_index, row in results_table.iterrows():
        try:
            sound_id = int(row["SoundId"])
        except (KeyError, TypeError, ValueError):
            continue

        trials_by_sound_id.setdefault(sound_id, []).append(
            {
                "session_date": session_date,
                "nwb_file": source_path.name,
                "nwb_path": str(source_path),
                "trial_index": int(trial_index),
                "trial": _to_builtin(row.to_dict()),
            }
        )


def _merge_hit_by_sound(
    batch_hit_by_sound: dict[int, dict],
    single_hit_by_sound: dict,
) -> None:
    for sound_id, stats in single_hit_by_sound.items():
        sound_id = int(sound_id)
        current = batch_hit_by_sound.setdefault(
            sound_id,
            {
                "n_trials": 0,
                "n_FAs": 0,
                "FAs_pct": 0.0,
            },
        )
        current["n_trials"] += int(stats.get("n_trials", 0))
        current["n_FAs"] += int(stats.get("n_FAs", 0))

    for stats in batch_hit_by_sound.values():
        n_trials = stats["n_trials"]
        if n_trials > 0:
            stats["FAs_pct"] = round((stats["n_FAs"] / n_trials) * 100.0, 2)


def _is_session_folder(folder: Path) -> bool:
    required_files = [
        "parameters.dat",
        "TrialType.bin",
        "TTLtrigsounds.bin",
        "Trial_log.csv",
    ]
    return all((folder / filename).exists() for filename in required_files)


def _find_session_folders_for_animal(folder_root: Path, animal_name: str) -> list[Path]:
    animal_l = (animal_name or "").strip().lower()
    session_folders = []
    candidate_folders = [folder_root] if _is_session_folder(folder_root) else []
    candidate_folders.extend(path.parent for path in folder_root.rglob("Trial_log.csv"))

    seen = set()
    for folder in candidate_folders:
        if folder in seen:
            continue
        seen.add(folder)
        if not _is_session_folder(folder):
            continue
        if animal_l and animal_l not in str(folder).lower():
            continue
        session_folders.append(folder)
    return sorted(session_folders)


def _process_batch_session(
    source_path: Path,
    data_session_dict: dict,
    hit_by_sound_func,
    trials_by_sound_id: dict[int, list[dict]],
    batch_hit_by_sound: dict[int, dict],
) -> tuple[dict, dict]:
    single_session_performance = extract_performance(data_session_dict)
    if 'dmts_analysis' in data_session_dict:
        single_hit_by_sound = data_session_dict['dmts_analysis']['hit_by_sound']
    else:
        ir_events = detect_ir_events(data_session_dict["dataIR"]["full"])
        trial_ir_analysis = (
            analyze_lick_events_by_trial(data_session_dict, ir_events)
            if hit_by_sound_func is extract_hit_by_sound_licks
            else analyze_ir_by_trial(data_session_dict, ir_events)
        )
        single_hit_by_sound = hit_by_sound_func(data_session_dict, trial_ir_analysis)
    _append_trials_by_sound_id(
        trials_by_sound_id,
        data_session_dict,
        source_path,
    )
    _merge_hit_by_sound(batch_hit_by_sound, single_hit_by_sound)
    return single_session_performance, single_hit_by_sound


def run_nogui(
    folder: Path,
    nwb_file: Path,
    outdir: Path,
    show_plots: bool = False,
    hit_source: str = "IR",
) -> None:
    use_folder = folder.exists() and folder.is_dir()
    use_file = nwb_file.exists() and nwb_file.is_file() and nwb_file.suffix.lower() == ".nwb"
    if not (use_folder or use_file):
        raise FileNotFoundError(f"Invalid session input: folder={folder} file={nwb_file}")

    session_data = load_session_data_fromFile(nwb_file) if use_file else load_session_data_fromFolder(folder)
    source_path = nwb_file if use_file else folder

    performance = extract_performance(session_data)
    ir_events, trial_ir_analysis, hit_by_sound = analyze_session_responses(
        session_data, hit_source)

    outdir.mkdir(parents=True, exist_ok=True)
    session_id = _safe_name(f"{source_path.parent.name}_{source_path.name}")
    results_csv = outdir / f"{session_id}_results_table.csv"
    summary_json = outdir / f"{session_id}_summary.json"

    session_data["ResultsTable"].to_csv(results_csv, index=False)
    summary = {
        "folder": str(source_path),
        "nTotalTrials": int(session_data["nTotalTrials"]),
        "performance": _to_builtin(performance),
        "hit_source": hit_source,
        "hit_by_sound": _to_builtin(hit_by_sound),
        "trial_types": _to_builtin(list(session_data["trialID"]["types"])),
    }
    summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"Session folder: {source_path}")
    print(f"nTotalTrials: {summary['nTotalTrials']}")
    print(f"Performance: {performance}")
    print(f"Hit source: {hit_source}")
    print(f"Saved results table: {results_csv}")
    print(f"Saved summary: {summary_json}")

    if show_plots:
        plot_session_visualizations = _get_plot_session_visualizations(force_agg=True)
        figures = plot_session_visualizations(
            session_data,
            performance,
            ir_events,
            trial_ir_analysis,
            hit_by_sound=hit_by_sound,
            show=False,
            block=False,
        )
        saved_plot_paths = []
        for idx, fig in enumerate(figures, start=1):
            plot_path = outdir / f"{session_id}_plot_{idx}.png"
            fig.savefig(plot_path, dpi=150, bbox_inches="tight")
            saved_plot_paths.append(plot_path)
        try:
            import matplotlib.pyplot as plt
            plt.close("all")
        except Exception:
            pass
        print("Saved plots:")
        for plot_path in saved_plot_paths:
            print(f"- {plot_path}")

    return session_data,performance,ir_events,trial_ir_analysis,hit_by_sound


def run_nogui_folder_batch(
    folder_root: Path,
    animal_name: str,
    outdir: Path,
    hit_source: str = "IR",
) -> dict:
    if not folder_root.exists() or not folder_root.is_dir():
        raise FileNotFoundError(f"Invalid folder root: {folder_root}")

    matching_folders = _find_session_folders_for_animal(folder_root, animal_name)
    if not matching_folders:
        raise FileNotFoundError(
            f"No session folders found for animal '{animal_name}' under {folder_root}"
        )

    performance_by_session: dict[str, dict] = {}
    trials_by_sound_id: dict[int, list[dict]] = {}
    batch_hit_by_sound: dict[int, dict] = {}
    hit_by_sound_func = _get_hit_by_sound_func(hit_source)

    for session_folder in matching_folders:
        datatmp = {}
        datatmp["data"] = []
        datatmp["params"] = []
        try:
            data_session_dict = load_session_data_fromFolder(session_folder)
            single_session_performance, single_hit_by_sound = _process_batch_session(
                session_folder,
                data_session_dict,
                hit_by_sound_func,
                trials_by_sound_id,
                batch_hit_by_sound,
            )
            session_key = _safe_name(
                f"{session_folder.parent.name}_{session_folder.name}"
            )
            unique_key = session_key
            suffix_idx = 2
            while unique_key in performance_by_session:
                unique_key = f"{session_key}_{suffix_idx}"
                suffix_idx += 1

            datatmp["params"] = _to_builtin(data_session_dict["parameters"])
            datatmp["data"] = _to_builtin(single_session_performance)
            datatmp["hit_by_sound"] = _to_builtin(single_hit_by_sound)
            datatmp["folder"] = str(session_folder)
            performance_by_session[unique_key] = datatmp
            print(f"OK: {session_folder}")
        except Exception as exc:
            performance_by_session[str(session_folder)] = {"error": str(exc)}
            print(f"ERROR: {session_folder} -> {exc}")

    outdir.mkdir(parents=True, exist_ok=True)
    batch_id = _safe_name(f"{animal_name}_folder_batch")
    batch_json = outdir / f"{batch_id}_performance.json"
    payload = {
        "animal_name": animal_name,
        "folder_root": str(folder_root),
        "n_sessions": len(matching_folders),
        "hit_source": hit_source,
        "performance_by_session": performance_by_session,
        "hit_by_sound": _to_builtin(batch_hit_by_sound),
        "trials_by_sound_id": _to_builtin(trials_by_sound_id),
    }
    batch_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Saved folder batch performance: {batch_json}")
    return payload


def save_batch_dict(batch_dict: dict, save_path: Path) -> Path:
    save_path = Path(save_path)
    save_path.parent.mkdir(parents=True, exist_ok=True)
    with save_path.open("wb") as file:
        pickle.dump(batch_dict, file)
    print(f"Saved batch dict: {save_path}")
    return save_path


def load_batch_dict(save_path: Path) -> dict:
    save_path = Path(save_path)
    with save_path.open("rb") as file:
        batch_dict = pickle.load(file)
    print(f"Loaded batch dict: {save_path}")
    return batch_dict


def load_batch_dicts(batch_paths) -> list[dict]:
    if isinstance(batch_paths, (str, Path)):
        batch_path = Path(batch_paths)
        if batch_path.is_dir():
            paths = sorted(batch_path.glob("*.pkl"))
        else:
            paths = [batch_path]
    else:
        paths = [Path(path) for path in batch_paths]

    if not paths:
        raise FileNotFoundError("No .pkl batch files found.")

    batch_dicts = []
    for path in paths:
        batch_dict = load_batch_dict(path)
        batch_dict["_pkl_path"] = str(path)
        batch_dicts.append(batch_dict)
    return batch_dicts










def run_nogui_nwb_batch(
                        nwb_root: Path,
                        animal_name: str,
                        outdir: Path,
                        hit_source: str = "IR",
                        ) -> dict:
    batch_payload = run_nwb_batch_analysis(
        nwb_root,
        animal_name,
        hit_source=hit_source,
        continue_on_error=True,
        verbose=True,
    )

    outdir.mkdir(parents=True, exist_ok=True)
    batch_id = _safe_name(f"{batch_payload['animal_name']}_nwb_batch")
    batch_json = outdir / f"{batch_id}_performance.json"
    payload = {
        "animal_name": batch_payload["animal_name"],
        "nwb_root": batch_payload["nwb_root"],
        "n_files": batch_payload["n_files"],
        "hit_source": batch_payload["hit_source"],
        "performance_by_file": _to_builtin(batch_payload["performance_by_file"]),
        "hit_by_sound": _to_builtin(batch_payload["hit_by_sound"]),
        "trials_by_sound_id": _to_builtin(batch_payload["trials_by_sound_id"]),
    }
    batch_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Saved batch performance: {batch_json}")
    return payload

def main() -> None:
    
    parser = argparse.ArgumentParser(description="Behavior session GUI and no-GUI runner")
    parser.add_argument(
        "--nogui",
        action="store_true",
        help="Run session extraction in terminal mode and save analysis files.",
    )
    parser.add_argument(
        "--folder",
        type=Path,
        default=Path(DEFAULT_SESSION_FOLDER),
        help="Session folder to process.",
    )
    parser.add_argument(
        "--file",
        type=Path,
        default=Path(DEFAULT_SESSION_FILE),
        help="Session file to process.",
    )
    parser.add_argument(
        "--outdir",
        type=Path,
        default=Path("analysis_exports"),
        help="Output folder for no-GUI exports.",
    )
    parser.add_argument(
        "--show-plots",
        action="store_true",
        help="When using --nogui, generate plots via behavior_plots.py and save PNG files in outdir.",
    )
    parser.add_argument(
        "--hit-source",
        choices=["IR", "Licks"],
        default="IR",
        help="Source used for hit-by-sound analysis.",
    )
    parser.add_argument(
        "--batch-nwb",
        action="store_true",
        help="In --nogui mode: run batch NWB processing by animal name.",
    )
    parser.add_argument(
        "--batch-folder",
        action="store_true",
        help="In --nogui mode: run batch processing on raw session folders by animal name.",
    )
    parser.add_argument(
        "--animal",
        type=str,
        default="",
        help="Animal name filter for --batch-nwb.",
    )
    parser.add_argument(
        "--nwb-root",
        type=Path,
        default=Path(DEFAULT_SESSION_FILE),
        help="Root folder where NWB files are searched for --batch-nwb.",
    )
    parser.add_argument(
        "--folder-root",
        type=Path,
        default=Path(DEFAULT_SESSION_FOLDER).parent.parent,
        help="Root folder where raw session folders are searched for --batch-folder.",
    )
    args = parser.parse_args()

    if args.nogui:
        if args.batch_folder:
            run_nogui_folder_batch(
                args.folder_root,
                args.animal,
                args.outdir,
                hit_source=args.hit_source,
            )
            return
        if args.batch_nwb:
            run_nogui_nwb_batch(
                args.nwb_root,
                args.animal,
                args.outdir,
                hit_source=args.hit_source,
            )
            return
        run_nogui(
            args.folder,
            args.file,
            args.outdir,
            show_plots=args.show_plots,
            hit_source=args.hit_source,
        )
        return

    if GUI_IMPORT_ERROR is not None:
        raise RuntimeError(
            f"GUI dependencies are not available in this Python environment: {GUI_IMPORT_ERROR}"
        ) from GUI_IMPORT_ERROR

    # Spyder/IPython reruns can keep a stale default Tk root alive.
    if tk._default_root is not None:
        try:
            tk._default_root.destroy()
        except Exception:
            pass
        try:
            plt.close("all")
        except Exception:
            pass

    root = tk.Tk()
    app = ScanMediaFoldersApp(root, initial_folder=str(args.folder), initial_file = str(args.file))
    if app.show_guide_at_startup.get():
        root.after_idle(app._show_getting_started)
    root.mainloop()


if __name__ == "__main__":
    main()

