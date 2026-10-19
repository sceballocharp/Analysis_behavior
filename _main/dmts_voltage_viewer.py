"""DMTS log voltage viewer adapted from pyBEHAVIOR/braincodec/plot_trial_voltages.py.
Measurements use the DMTS driver's P1-P10 channel order.
"""
from pathlib import Path
import csv
from tkinter import StringVar, Toplevel, filedialog, messagebox, ttk
import re
from matplotlib.figure import Figure
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

def parse_dmts_log_file(path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.reader(handle))
    starts = [index for index, row in enumerate(rows)
              if row and row[0].strip() == "Trial:"]
    trials = {}
    for block_index, start in enumerate(starts):
        end = starts[block_index + 1] if block_index + 1 < len(starts) else len(rows)
        block = rows[start:end]
        fields = {row[0].strip(): row[1].strip()
                  for row in block if len(row) >= 2}
        trial_number = int(fields["Trial:"])
        trial_id = fields.get("Trial ID:") or str(trial_number)
        trial = trials.setdefault(trial_id, {"trial": trial_number,
                                             "trial_id": trial_id})
        phase = fields.get("Presentation:", "").lower()
        if phase not in ("sample", "test"):
            raise ValueError(f"Trial {trial_number}: unknown presentation {phase!r}.")
        if phase in trial:
            raise ValueError(f"Trial {trial_number}: duplicate {phase} presentation.")
        pattern = fields.get("LED pattern:", "").upper().split()
        for position in pattern:
            row, col = parse_position(position)
            if not (0 <= row < 10 and 0 <= col < 10):
                raise ValueError(f"Trial {trial_number}: invalid LED position {position}.")
        voltages = None
        for index, row in enumerate(block):
            if row and row[0].strip() == "Measured voltages (V):":
                # The driver puts a message on the header when no measurement exists.
                if len(row) == 1 and index + 1 < len(block):
                    try:
                        values = [float(value) for value in block[index + 1]
                                  if value.strip()]
                    except ValueError:
                        values = []
                    if len(values) >= 10:
                        voltages = values
                break
        trial[phase] = {
            "stimulus": fields.get("Stimulus:", "Unknown"),
            "pattern": pattern,
            "voltages": voltages,
            "completed": fields.get("Presentation completed:", "").lower() == "true",
            "trigger_time": fields.get("Trigger detected, starting stimulus", ""),
            "fault_reg_a": fields.get("Fault reg A:", "unavailable"),
            "fault_reg_b": fields.get("Fault reg B:", "unavailable"),
        }
    return list(trials.values())


def led_labels_grid(shape=(10, 10)):
    labels = np.empty(shape, dtype=object)
    for n_number in range(1, shape[0] + 1):
        for p_number in range(1, shape[1] + 1):
            labels[n_number - 1, p_number - 1] = f"P{p_number}N{n_number}"
    return labels


def parse_position(position):
    p_text, n_text = position.upper().split("N", maxsplit=1)
    p_number = int(p_text.replace("P", ""))
    n_number = int(n_text)
    return n_number - 1, p_number - 1


def voltages_to_pattern_grid(voltages, pattern, channel_order=tuple(range(10))):
    if len(voltages) < 10:
        raise ValueError(f"Expected at least 10 voltage values, found {len(voltages)}.")

    reordered_voltages = np.array(voltages[:10], dtype=float)[list(channel_order)]
    voltage_grid = np.tile(reordered_voltages, 10).reshape(10, 10)

    labels = led_labels_grid()
    pattern_mask = np.isin(labels, pattern)
    voltage_grid[~pattern_mask] = np.nan
    return voltage_grid


def voltage_presentations_by_stim(trials):
    """Pool sample and test measurements, counting each presentation once."""
    groups = {}
    for trial in trials:
        for phase in ("sample", "test"):
            presentation = trial.get(phase)
            if presentation is None:
                continue
            stim = presentation["stimulus"].strip()
            group = groups.setdefault(stim, dict(total=0, valid=0, positions={}))
            group["total"] += 1
            if presentation["voltages"] is None or not presentation["pattern"]:
                continue
            grid = voltages_to_pattern_grid(presentation["voltages"], presentation["pattern"])
            valid = False
            for position in dict.fromkeys(presentation["pattern"]):
                row, col = parse_position(position)
                value = grid[row, col]
                if np.isfinite(value):
                    group["positions"].setdefault(position, []).append(float(value))
                    valid = True
            group["valid"] += int(valid)
    return groups


def plot_voltage_stim_summary(groups, stimuli, title="CSV voltage summary"):
    """Individual presentations and mean ± population SD at each active position."""
    if not stimuli:
        raise ValueError("No stimuli found in the CSV log.")
    columns = min(4, int(np.ceil(np.sqrt(len(stimuli)))))
    rows = (len(stimuli) + columns - 1) // columns
    fig = Figure(figsize=(max(9, columns * 4.5), max(5, rows * 3.6 + 1)))
    axes = np.asarray(fig.subplots(rows, columns, squeeze=False)).ravel()
    all_values = [v for group in groups.values() for values in group["positions"].values() for v in values]
    low = min(0, min(all_values, default=0))
    high = max(9, max(all_values, default=9))
    rng = np.random.default_rng(0)
    for ax, stim in zip(axes, stimuli):
        group = groups[stim]
        positions = sorted(group["positions"], key=lambda p: parse_position(p)[::-1])
        for index, position in enumerate(positions):
            values = np.asarray(group["positions"][position])
            ax.scatter(index + rng.uniform(-.18, .18, len(values)), values,
                       s=14, alpha=.3, color="#2F6F9F", edgecolors="none")
            ax.errorbar(index, values.mean(), yerr=values.std(), fmt="o", color="black",
                        capsize=4, markersize=5)
        ax.set_xticks(range(len(positions)), positions, rotation=60, ha="right")
        ax.set(xlabel="Active LED position", ylabel="Measured voltage (V)",
               ylim=(low - .2, high + .2), title=f"{stim} | {group['valid']}/{group['total']} valid presentations")
        ax.grid(axis="y", alpha=.25)
        if not positions:
            ax.text(.5, .5, "No valid voltage measurements", transform=ax.transAxes, ha="center")
    for ax in axes[len(stimuli):]:
        ax.set_visible(False)
    fig.suptitle(title, fontsize=12)
    fig.text(.5, .015, "Dots: every sample/test presentation pooled by stimulus. Black: mean ± SD.\n"
             "Counts are presentations; missing/non-finite measurements excluded. Positions on the same P channel share its measurement.",
             ha="center", fontsize=9)
    fig.tight_layout(rect=(0, .075, 1, .95))
    return fig


class DMTSVoltageViewer:
    def __init__(self, root, default_file=None, on_loaded=None):
        self.root = root
        self.on_loaded = on_loaded
        self.window = root.winfo_toplevel()
        self.window.title("DMTS Trial Voltages (log)")
        self.trials = []
        self.current_index = 0
        self.summary_closers = []
        self.file_path = StringVar(master=root, value=str(default_file) if default_file else "")
        self.trial_entry = StringVar(master=root, value="")
        self.status = StringVar(master=root, value="Select a DMTS CSV log")
        self.summary = StringVar(master=root, value="")
        self.loaded_csv = StringVar(master=root, value="No CSV file loaded")
        self.build_layout()
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        if default_file is not None:
            self.load_file(Path(default_file))

    def close(self):
        for close_summary in list(self.summary_closers):
            close_summary()
        plt.close(self.figure)
        self.window.destroy()

    def browse_file(self):
        selected = filedialog.askopenfilename(
            initialdir=str(Path(self.file_path.get()).parent),
            title="Select log CSV file",
            filetypes=(("CSV files", "*.csv"), ("All files", "*.*")),
        )
        if selected:
            self.load_file(Path(selected))


    def previous_trial(self):
        if not self.trials:
            return
        self.current_index = max(0, self.current_index - 1)
        self.update_plot()


    def next_trial(self):
        if not self.trials:
            return
        self.current_index = min(len(self.trials) - 1, self.current_index + 1)
        self.update_plot()


    def go_to_trial(self):
        try:
            trial_number = int(self.trial_entry.get())
        except ValueError:
            messagebox.showwarning("Invalid trial", "Enter a numeric trial number.")
            return

        for index, trial in enumerate(self.trials):
            if trial["trial"] == trial_number:
                self.current_index = index
                self.update_plot()
                return

        messagebox.showwarning(
            "Trial not found",
            f"Trial {trial_number} was not found in this log.",
        )


    def draw_voltage_grid(self, ax, voltage_grid, title, annotate):
        ax.clear()

        masked_voltages = np.ma.masked_invalid(voltage_grid)
        cmap = plt.colormaps["viridis"].with_extremes(bad="lightgray")
        heatmap_image = ax.imshow(
            masked_voltages, cmap=cmap, interpolation="nearest", vmin=0, vmax=9
        )

        ax.set_title(title)
        ax.set_xlabel("P channel")
        ax.set_ylabel("N channel")
        ax.set_xticks(np.arange(10), labels=[f"P{i}" for i in range(1, 11)])
        ax.set_yticks(np.arange(10), labels=[f"N{i}" for i in range(1, 11)])
        ax.tick_params(axis="x", rotation=45)

        if annotate:
            for row in range(voltage_grid.shape[0]):
                for col in range(voltage_grid.shape[1]):
                    if np.isnan(voltage_grid[row, col]):
                        continue
                    ax.text(
                        col,
                        row,
                        f"{voltage_grid[row, col]:.2f}",
                        ha="center",
                        va="center",
                        color="white" if voltage_grid[row, col] < 5 else "black",
                        fontsize=8,
                    )
        return heatmap_image


    def build_layout(self):
        root_frame = ttk.Frame(self.root, padding=10)
        root_frame.pack(fill="both", expand=True)
        file_frame = ttk.Frame(root_frame)
        file_frame.pack(fill="x")
        ttk.Button(file_frame, text="Browse file", command=self.browse_file).pack(side="left")
        file_entry = ttk.Entry(file_frame, textvariable=self.file_path)
        file_entry.pack(side="left", fill="x", expand=True, padx=8)
        file_entry.bind("<Return>", lambda _event: self.load_file(Path(self.file_path.get())))
        ttk.Button(file_frame, text="Load", command=lambda: self.load_file(
            Path(self.file_path.get()))).pack(side="left", padx=(0, 6))
        ttk.Button(file_frame, text="Quit", command=lambda: self.close()).pack(side="left")
        controls = ttk.Frame(root_frame)
        controls.pack(fill="x", pady=(8, 4))
        self.prev_button = ttk.Button(controls, text="Previous Trial",
                                     command=self.previous_trial, state="disabled")
        self.prev_button.pack(side="left")
        self.next_button = ttk.Button(controls, text="Next Trial",
                                     command=self.next_trial, state="disabled")
        self.next_button.pack(side="left", padx=(6, 14))
        ttk.Label(controls, text="Trial").pack(side="left")
        trial_entry = ttk.Entry(controls, textvariable=self.trial_entry, width=8)
        trial_entry.pack(side="left", padx=6)
        trial_entry.bind("<Return>", lambda _event: self.go_to_trial())
        ttk.Button(controls, text="Go", command=self.go_to_trial).pack(side="left")
        ttk.Label(controls, textvariable=self.summary).pack(side="left", padx=18)
        self.figure, axes = plt.subplots(1, 2, figsize=(12, 6))
        self.figure.subplots_adjust(left=0.06, right=0.94, bottom=0.14,
                                    top=0.85, wspace=0.38)
        self.phase_axes = dict(zip(("sample", "test"), axes))
        self.phase_colorbars = {}
        for phase, ax in self.phase_axes.items():
            image = self.draw_voltage_grid(ax, np.full((10, 10), np.nan),
                                           phase.title(), annotate=False)
            colorbar = self.figure.colorbar(image, ax=ax, fraction=0.035,
                                            pad=0.025, shrink=0.82)
            colorbar.set_label("Measured voltage (V)")
            self.phase_colorbars[phase] = colorbar
        self.canvas = FigureCanvasTkAgg(self.figure, master=root_frame)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, pady=(8, 4))
        self.toolbar = NavigationToolbar2Tk(self.canvas, root_frame, pack_toolbar=False)
        self.toolbar.pack(fill="x")
        ttk.Label(root_frame, textvariable=self.status).pack(fill="x")


    def load_file(self, path):
        try:
            trials = parse_dmts_log_file(path)
            if not trials:
                raise ValueError("No DMTS trial presentations were found.")
        except Exception as error:
            messagebox.showerror("Could not load DMTS file", str(error))
            return
        self.trials = trials
        self.current_index = 0
        self.file_path.set(str(path))
        self.loaded_csv.set(f"Loaded CSV file: {path.name}")
        if self.on_loaded is not None:
            self.on_loaded(path, trials)
        self.update_plot()

    def open_stim_summary(self):
        if not self.trials:
            return
        groups = voltage_presentations_by_stim(self.trials)
        def natural(value):
            return [(0, int(part)) if part.isdigit() else (1, part.lower())
                    for part in re.split(r"(\d+)", value)]
        stimuli = sorted(groups, key=natural)
        window = Toplevel(self.window)
        window.title("Average voltages by StimID")
        window.geometry("1400x950")
        fig = plot_voltage_stim_summary(groups, stimuli,
                title=f"{Path(self.file_path.get()).name} | Sample + test presentations")
        canvas = FigureCanvasTkAgg(fig, master=window)
        toolbar = NavigationToolbar2Tk(canvas, window, pack_toolbar=False)
        toolbar.pack(side="bottom", fill="x")
        canvas.get_tk_widget().pack(fill="both", expand=True)
        canvas.draw()
        def close():
            plt.close(fig)
            window.destroy()
            self.summary_closers.remove(close)
        self.summary_closers.append(close)
        window.protocol("WM_DELETE_WINDOW", close)


    def update_plot(self):
        trial = self.trials[self.current_index]
        notices = []
        for phase, ax in self.phase_axes.items():
            presentation = trial.get(phase)
            grid = np.full((10, 10), np.nan)
            title = f"Trial {trial['trial']} | {phase.title()}"
            message = None
            if presentation is None:
                message = "Missing presentation"
            else:
                title += (f" | {presentation['stimulus']}\n"
                          f"fault A={presentation['fault_reg_a']}, "
                          f"B={presentation['fault_reg_b']}")
                if not presentation["completed"]:
                    notices.append(f"{phase}: presentation not completed")
                if presentation["voltages"] is None:
                    message = "No voltage measurement"
                elif not presentation["pattern"]:
                    message = "BLANK" if presentation["stimulus"].upper() == "BLANK" else "Empty LED pattern"
                else:
                    # DMTS diagnostics are logged in P1-P10 order, without pair swaps.
                    grid = voltages_to_pattern_grid(presentation["voltages"],
                                                   presentation["pattern"],
                                                   channel_order=list(range(10)))
            image = self.draw_voltage_grid(ax, grid, title, annotate=True)
            self.phase_colorbars[phase].update_normal(image)
            if message:
                ax.text(0.5, 0.5, message, transform=ax.transAxes,
                        ha="center", va="center")
                if message != "BLANK":
                    notices.append(f"{phase}: {message.lower()}")
        self.prev_button.configure(state="normal" if self.current_index > 0 else "disabled")
        self.next_button.configure(state="normal" if self.current_index < len(self.trials) - 1 else "disabled")
        self.trial_entry.set(str(trial["trial"]))
        self.summary.set(f"{self.current_index + 1}/{len(self.trials)} trials")
        self.status.set(" | ".join(notices) if notices else f"Trial ID: {trial['trial_id']}")
        self.canvas.draw_idle()


