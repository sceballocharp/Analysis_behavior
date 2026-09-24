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
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
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
        self.root.title("BEHAVIOR v8")
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        window_width = int(screen_width * 0.75)
        window_height = int(screen_height * 0.90)
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
        self.active_input = "folder"
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
            show_guide = True
        self.show_guide_at_startup = tk.BooleanVar(value=show_guide)
        self._build_ui()
        self.folder_var.trace_add("write", lambda *_: self._sync_current_input_label())
        self.file_var.trace_add("write", lambda *_: self._sync_current_input_label())
        self._sync_current_input_label()
        self._write_output("GUI ready. Choose a folder or NWB file, then click its Run rectangle in the Plot panel.\n")

    def _save_guide_preference(self) -> None:
        try:
            self.guide_settings_path.write_text(
                json.dumps({"show_guide_at_startup": self.show_guide_at_startup.get()}, indent=2),
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
        window.title("Getting started - BEHAVIOR v8")
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
            ("Optional: analyze several sessions", "Open the Animal tab and enter Animal name. Click Find NWB files or Find folders, then choose the parent folder to search. Check the matches in Output. Click Run All NWB or Run All Folders for the corresponding results. Use Batch performance in the Plot panel when it becomes available."),
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

        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill="x", pady=(0, 8))

        input_tab = ttk.Frame(notebook, padding=10)
        meta_tab = ttk.Frame(notebook, padding=10)
        notebook.add(input_tab, text="Folder or File")
        notebook.add(meta_tab, text="Animal")

        ttk.Label(input_tab, text="Session input:").grid(
            row=0, column=0, sticky="w", padx=(0, 10)
        )

        browse_button = ttk.Button(
            input_tab, text="Browse FOLDER", command=self._browse_folder
        )
        browse_button.grid(row=0, column=1, padx=(0, 10))

        browse_button2 = ttk.Button(
            input_tab, text="Browse NWB", command=self._browse_nwb
        )
        browse_button2.grid(row=0, column=2, padx=(0, 10))

        self.trial_viewer_button = ttk.Button(
            input_tab,
            text="Trial viewer",
            command=self._open_trial_viewer,
            state="disabled",
        )
        self.trial_viewer_button.grid(row=0, column=3, padx=(10, 0))

        ttk.Label(input_tab, text="Hit source:").grid(
            row=1, column=0, sticky="w", pady=(10, 0), padx=(0, 10)
        )
        ttk.Radiobutton(
            input_tab,
            text="IR",
            variable=self.hit_source_var,
            value="IR",
        ).grid(row=1, column=1, sticky="w", pady=(10, 0))
        ttk.Radiobutton(
            input_tab,
            text="Licks",
            variable=self.hit_source_var,
            value="Licks",
        ).grid(row=1, column=2, sticky="w", pady=(10, 0))

        ttk.Label(meta_tab, text="Animal name:").grid(
            row=0, column=0, sticky="w", padx=(0, 10)
        )
        animal_entry = ttk.Entry(meta_tab, textvariable=self.animal_var, width=30)
        animal_entry.grid(row=0, column=1, sticky="ew")
        find_nwb_button = ttk.Button(
            meta_tab,
            text="Find NWB files",
            command=self._find_nwb_files_for_animal,
        )
        find_nwb_button.grid(row=0, column=2, padx=(10, 0))
        run_batch_button = ttk.Button(
            meta_tab,
            text="Run All NWB",
            command=self._run_all_found_nwb_files,
        )
        run_batch_button.grid(row=0, column=3, padx=(10, 0))
        find_folder_button = ttk.Button(
            meta_tab,
            text="Find folders",
            command=self._find_session_folders_for_animal,
        )
        find_folder_button.grid(row=1, column=2, padx=(10, 0), pady=(10, 0))
        run_folder_batch_button = ttk.Button(
            meta_tab,
            text="Run All Folders",
            command=self._run_all_found_session_folders,
        )
        run_folder_batch_button.grid(row=1, column=3, padx=(10, 0), pady=(10, 0))
        meta_tab.columnconfigure(1, weight=1)

        ttk.Label(main_frame, text="Current session folder:").pack(anchor="w", pady=(8, 0))
        current_folder_label = ttk.Label(
            main_frame,
            textvariable=self.current_folder_var,
            wraplength=860,
        )
        current_folder_label.pack(anchor="w")

        status_frame = ttk.Frame(main_frame)
        status_frame.pack(fill="x", pady=(12, 10))
        ttk.Label(status_frame, text="Status:").pack(side="left")
        ttk.Label(status_frame, textvariable=self.status_var).pack(side="left", padx=(6, 0))
        
        # --- Bottom split: output text (left) + plot (right) ---
        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.pack(fill="both", expand=True, pady=(6, 0))
        bottom_frame.columnconfigure(0, weight=1)
        bottom_frame.columnconfigure(1, weight=1)
        bottom_frame.rowconfigure(1, weight=1)  # row 1 = the content row

        # Labels in row 0
        ttk.Label(bottom_frame, text="Output").grid(row=0, column=0, sticky="w")
        ttk.Label(bottom_frame, text="Plot").grid(row=0, column=1, sticky="w")

        # Scrolled text in row 1, column 0
        self.output_text = scrolledtext.ScrolledText(
            bottom_frame,
            wrap="word",
            height=20,
            font=("Consolas", 10),
        )
        self.output_text.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        self.output_text.configure(state="disabled")
        
        # Right: blank matplotlib canvas for v8 layout work
        right_frame = ttk.Frame(bottom_frame)
        right_frame.grid(row=1, column=1, sticky="nsew")

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

    def _reset_session(self) -> None:
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
            self.file_var.set(selected)
            self._sync_current_input_label()
            self._draw_selected_input_box()

    @staticmethod
    def _infer_animal_name_from_nwb_filename(nwb_path: Path) -> str | None:
        stem = Path(nwb_path).stem
        patterns = [
            r"(?:^|[_-])sub[_-]?([A-Za-z]*\d+[A-Za-z0-9]*)(?=$|[_-])",
            r"(?:^|[_-])(M\d+[A-Za-z0-9]*)(?=$|[_-])",
        ]
        for pattern in patterns:
            match = re.search(pattern, stem, flags=re.IGNORECASE)
            if match:
                return match.group(1)
        return None

    def _infer_animal_name_from_nwb_files(self, nwb_files: list[Path]) -> str | None:
        inferred_names = [
            animal_name
            for nwb_path in nwb_files
            if (animal_name := self._infer_animal_name_from_nwb_filename(nwb_path))
        ]
        if not inferred_names:
            return None

        counts = Counter(inferred_names)
        most_common = counts.most_common()
        if len(most_common) == 1 or most_common[0][1] > most_common[1][1]:
            return most_common[0][0]

        tied_names = ", ".join(name for name, count in most_common if count == most_common[0][1])
        messagebox.showinfo(
            "Multiple animals found",
            "Several animal names were inferred equally often from NWB filenames:\n"
            f"{tied_names}\n\nPlease enter one animal name manually.",
        )
        self._write_output(
            f"Could not choose one inferred animal name. Candidates: {tied_names}\n"
        )
        return None

    def _find_nwb_files_for_animal(self) -> None:
        animal_name = self.animal_var.get().strip()

        root_dir = filedialog.askdirectory(initialdir=self.file_var.get() or ".")
        if not root_dir:
            return

        root_path = Path(root_dir)
        if not animal_name:
            nwb_files = sorted(root_path.rglob("*.nwb"))
            if not nwb_files:
                messagebox.showinfo("No NWB found", f"No .nwb files found in:\n{root_path}")
                self._write_output(f"No NWB files found under {root_path}\n")
                return

            animal_name = self._infer_animal_name_from_nwb_files(nwb_files)
            if not animal_name:
                messagebox.showerror(
                    "Missing animal name",
                    "Could not infer an animal name from the NWB filenames. "
                    "Please enter one manually.",
                )
                return

            self.animal_var.set(animal_name)
            self._write_output(
                f"Inferred animal name '{animal_name}' from NWB filenames.\n"
            )

        matching_files = find_nwb_files_for_animal(root_path, animal_name)

        if not matching_files:
            messagebox.showinfo(
                "No NWB found",
                f"No .nwb files found for animal '{animal_name}' in:\n{root_path}",
            )
            self._write_output(
                f"No NWB files found for animal '{animal_name}' under {root_path}\n"
            )
            return

        matching_files = sorted(matching_files)
        self.found_nwb_files = matching_files
        self.found_session_folders = []
        selected_file = self.found_nwb_files[0]
        self.file_var.set(str(selected_file))
        self.active_input = "file"
        self._sync_current_input_label()
        self._write_output(f"Found {len(self.found_nwb_files)} NWB file(s) for '{animal_name}'. \n")
        for nwbfiletmp in self.found_nwb_files:
            self._write_output(nwbfiletmp.name.lower() + "\n")
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
        selected_folder = self.found_session_folders[0]
        self.folder_var.set(str(selected_folder))
        self.active_input = "folder"
        self._sync_current_input_label()
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
                ir_events = detect_ir_events(data_session_dict["dataIR"]["full"])
                trial_ir_analysis = analyze_ir_by_trial(data_session_dict, ir_events)
                single_hit_by_sound = hit_by_sound_func(
                    data_session_dict,
                    trial_ir_analysis,
                )
                session_key = str(nwb_path)
                self.batch_performance_by_file[session_key] = single_session_performance
                results_table = data_session_dict["ResultsTable"]
                trial_type = np.asarray(results_table["TrialType"], dtype=int)
                hit = np.asarray(results_table["Hit"], dtype=int)
                cr = np.asarray(results_table["CR"], dtype=int)
                correct = np.full(len(results_table), np.nan, dtype=float)
                correct[trial_type == 1] = hit[trial_type == 1]
                correct[trial_type == 2] = cr[trial_type == 2]
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
                ir_events = detect_ir_events(data_session_dict["dataIR"]["full"])
                trial_ir_analysis = analyze_ir_by_trial(data_session_dict, ir_events)
                single_hit_by_sound = hit_by_sound_func(
                    data_session_dict,
                    trial_ir_analysis,
                )
                session_key = str(session_folder)
                self.batch_performance_by_file[session_key] = single_session_performance
                results_table = data_session_dict["ResultsTable"]
                trial_type = np.asarray(results_table["TrialType"], dtype=int)
                hit = np.asarray(results_table["Hit"], dtype=int)
                cr = np.asarray(results_table["CR"], dtype=int)
                correct = np.full(len(results_table), np.nan, dtype=float)
                correct[trial_type == 1] = hit[trial_type == 1]
                correct[trial_type == 2] = cr[trial_type == 2]
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
            ir_events = detect_ir_events(data_session_dict["dataIR"]["full"])
            trial_ir_analysis = analyze_ir_by_trial(data_session_dict, ir_events)
            hit_by_sound_func = _get_hit_by_sound_func(hit_source)
            hit_by_sound = hit_by_sound_func(data_session_dict, trial_ir_analysis)
            
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
        ir_events: dict,
        trial_ir_analysis: dict,
    ) -> None:
        
        self.session_target_folder = target_folder
        self.single_session_datadict = data_session_dict
        self.single_session_performance = single_session_performance
        self.single_session_hit_by_sound = hit_by_sound
        self.single_session_ir_events = ir_events
        self.single_session_trial_ir_analysis = trial_ir_analysis

        self._write_output('nTrials: ' + str(data_session_dict['nTotalTrials']) + '\n')
        self._write_output(f"IR valid events: {len(ir_events['debut_fork'])}\n")
        self._write_output(f"Analyzed trials (IRxTrial): {trial_ir_analysis['n_analyzed_trials']}\n")
        self._write_output(f"Stay>={trial_ir_analysis['stay_threshold_ms']:g}ms at reward window "
                           f"(percIRFork={trial_ir_analysis['perc_ir_fork']:g}%): "
                           f"{trial_ir_analysis['pct_above_threshold']:.1f}%\n")
        if hit_by_sound:
            self._write_output("Hit by SoundId:\n")
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
    def _draw_selected_input_box(self) -> None:
        if self.main_canvas_ax is None or self.main_canvas is None:
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

        rect = Rectangle(
            (0.06, 0.76),
            0.28,
            0.18,
            facecolor="#F7FBFF",
            edgecolor="#4C78A8",
            linewidth=1.5,
            picker=not self.is_running,
        )
        rect.set_gid("run_session")
        ax.add_patch(rect)
        ax.text(
            0.08,
            0.90,
            "Running..." if self.is_running else f"Run {input_label}",
            fontsize=10,
            fontweight="bold",
            color="#222222",
            va="top",
        )
        ax.text(
            0.08,
            0.83,
            display_name,
            fontsize=9,
            color="#333333",
            va="top",
            wrap=True,
        )

        if hasattr(self, "single_session_datadict"):
            variable_names = [
                "single_session_datadict",
                "single_session_performance",
                "single_session_hit_by_sound",
                "single_session_ir_events",
                "single_session_trial_ir_analysis",
            ]
            line_height = 0.035
            header_height = 0.075
            padding = 0.045
            rect_height = header_height + padding + (len(variable_names) * line_height)
            rect_y = 0.76 - rect_height - 0.04
            result_rect = Rectangle(
                (0.06, rect_y),
                0.42,
                rect_height,
                facecolor="#F6FFF5",
                edgecolor="#59A14F",
                linewidth=1.5,
            )
            result_rect.set_picker(True)
            result_rect.set_gid("session_console")
            ax.add_patch(result_rect)
            ax.text(
                0.08,
                rect_y + rect_height - 0.04,
                "Session variables (click to inspect)",
                fontsize=10,
                fontweight="bold",
                color="#222222",
                va="top",
            )
            ax.text(
                0.08,
                rect_y + rect_height - 0.105,
                "\n".join(variable_names),
                fontsize=8.5,
                color="#333333",
                va="top",
                linespacing=1.25,
            )
            plot_node = Rectangle(
                (0.58, 0.58),
                0.24,
                0.13,
                facecolor="#FFF8F0",
                edgecolor="#E15759",
                linewidth=1.5,
                picker=True,
            )
            plot_node.set_gid("plot_ir_occupancy_by_sound")
            ax.add_patch(plot_node)
            point, = ax.plot(
                [0.61],
                [0.645],
                marker="o",
                markersize=8,
                color="#E15759",
                picker=8,
            )
            point.set_gid("plot_ir_occupancy_by_sound")
            ax.text(
                0.64,
                0.665,
                "IR occupancy",
                fontsize=10,
                fontweight="bold",
                color="#222222",
                va="top",
            )
            ax.text(
                0.64,
                0.62,
                "click to plot",
                fontsize=8.5,
                color="#555555",
                va="top",
            )
            performance_node = Rectangle(
                (0.58, 0.40),
                0.24,
                0.13,
                facecolor="#F3FAF1",
                edgecolor="#59A14F",
                linewidth=1.5,
                picker=True,
            )
            performance_node.set_gid("plot_performance")
            ax.add_patch(performance_node)
            perf_point, = ax.plot(
                [0.61],
                [0.465],
                marker="o",
                markersize=8,
                color="#59A14F",
                picker=8,
            )
            perf_point.set_gid("plot_performance")
            ax.text(
                0.64,
                0.485,
                "Performance",
                fontsize=10,
                fontweight="bold",
                color="#222222",
                va="top",
            )
            ax.text(
                0.64,
                0.44,
                "click to plot",
                fontsize=8.5,
                color="#555555",
                va="top",
            )
            hit_node = Rectangle(
                (0.58, 0.22),
                0.24,
                0.13,
                facecolor="#F4F7FF",
                edgecolor="#4C78A8",
                linewidth=1.5,
                picker=True,
            )
            hit_node.set_gid("plot_hit_by_sound")
            ax.add_patch(hit_node)
            hit_point, = ax.plot(
                [0.61],
                [0.285],
                marker="o",
                markersize=8,
                color="#4C78A8",
                picker=8,
            )
            hit_point.set_gid("plot_hit_by_sound")
            ax.text(
                0.64,
                0.305,
                "Hit by sound",
                fontsize=10,
                fontweight="bold",
                color="#222222",
                va="top",
            )
            ax.text(
                0.64,
                0.26,
                "click to plot",
                fontsize=8.5,
                color="#555555",
                va="top",
            )
        if self.batch_performance_by_file:
            batch_node = Rectangle(
                (0.58, 0.04),
                0.24,
                0.13,
                facecolor="#FFF7E6",
                edgecolor="#F28E2B",
                linewidth=1.5,
                picker=True,
            )
            batch_node.set_gid("plot_batch_session_performance")
            ax.add_patch(batch_node)
            batch_point, = ax.plot(
                [0.61],
                [0.105],
                marker="o",
                markersize=8,
                color="#F28E2B",
                picker=8,
            )
            batch_point.set_gid("plot_batch_session_performance")
            ax.text(
                0.64,
                0.125,
                "Batch performance",
                fontsize=10,
                fontweight="bold",
                color="#222222",
                va="top",
            )
            ax.text(
                0.64,
                0.08,
                "click to plot",
                fontsize=8.5,
                color="#555555",
                va="top",
            )
        self.main_canvas.draw()

    def _handle_main_canvas_pick(self, event) -> None:
        if event.artist.get_gid() == "run_session":
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
    ir_events = detect_ir_events(data_session_dict["dataIR"]["full"])
    trial_ir_analysis = analyze_ir_by_trial(data_session_dict, ir_events)
    single_hit_by_sound = hit_by_sound_func(
        data_session_dict,
        trial_ir_analysis,
    )
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
    ir_events = detect_ir_events(session_data["dataIR"]["full"])
    trial_ir_analysis = analyze_ir_by_trial(session_data, ir_events)
    hit_by_sound_func = _get_hit_by_sound_func(hit_source)
    hit_by_sound = hit_by_sound_func(session_data, trial_ir_analysis)

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
