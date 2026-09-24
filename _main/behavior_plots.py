# -*- coding: utf-8 -*-
"""
Shared plotting utilities for behavior session visualization.

These functions are intentionally GUI-agnostic so they can be reused by:
- Tk GUI flow (`behavior_gui_v3.py`)
- `--nogui` command-line flow
"""

from pathlib import Path
import re

import numpy as np
import matplotlib.pyplot as plt

from scipy.optimize import curve_fit

# -----------------------------------------------------------------------------
# General utilities
# -----------------------------------------------------------------------------

DEFAULT_FIGURE_FOLDER = Path(
    "C:/Users/seceball/Dropbox/__idA/BathellierLab/Behavior/Figures"
)


def _natural_sort_key(value):
    return [
        int(part) if part.isdigit() else part.lower()
        for part in re.split(r"(\d+)", str(value))
    ]


def save_figure_pdf(
    fig,
    save_path,
    folder=DEFAULT_FIGURE_FOLDER,
    dpi=300,
    bbox_inches="tight",
    transparent=False,
):
    """
    Save a matplotlib figure as a PDF.

    Parameters
    ----------
    fig : matplotlib.figure.Figure
        Figure to save. Use plt.gcf() if you want the current active figure.
    save_path : str or pathlib.Path
        Output filename or full path. If only a filename is given, it is saved
        inside `folder`. If no .pdf suffix is given, it is added automatically.
    folder : str or pathlib.Path
        Default folder used when `save_path` is only a filename.
    dpi : int
        Resolution used for rasterized elements inside the PDF.
    bbox_inches : str or None
        Use "tight" to trim whitespace around the figure.
    transparent : bool
        Save with transparent background when True.

    Returns
    -------
    pathlib.Path
        Final saved PDF path.
    """
    save_path = Path(save_path)
    if save_path.parent == Path("."):
        save_path = Path(folder) / save_path
    if save_path.suffix.lower() != ".pdf":
        save_path = save_path.with_suffix(".pdf")
    save_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(
        save_path,
        format="pdf",
        dpi=dpi,
        bbox_inches=bbox_inches,
        transparent=transparent,
    )
    return save_path


# -----------------------------------------------------------------------------
# ResultsTable and trial text helpers
# -----------------------------------------------------------------------------

def _to_sound_ids(results_table):
    sound_ids = results_table["SoundId"].to_numpy()
    try:
        return sound_ids.astype(int)
    except ValueError:
        return np.array([int(float(val)) for val in sound_ids], dtype=int)

def _to_ttypes_ids(results_table):
    ttype = results_table["TrialType"].to_numpy()
    try:
        return ttype.astype(int)
    except ValueError:
        return np.array([int(float(val)) for val in ttype], dtype=int)

def _format_results_table_value(value):
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float):
        if np.isnan(value):
            return "nan"
        return f"{value:.3g}"
    return str(value)

def _format_results_table_row(results_table, trial_index, result_fields=None):
    if results_table is None or results_table.empty:
        return "ResultsTable: empty"
    if trial_index < 0 or trial_index >= len(results_table):
        return f"ResultsTable: no row for trial {trial_index}"

    row = results_table.iloc[trial_index]
    if result_fields is None:
        result_fields = list(row.index)

    lines = ["ResultsTable"]
    for field in result_fields:
        if field in row.index:
            lines.append(f"{field}: {_format_results_table_value(row[field])}")
    return "\n".join(lines)

def _format_trial_ir_times(trial_ir_analysis, trial_index):
    if trial_ir_analysis is None:
        return []

    try:
        trial_ir_data = trial_ir_analysis["dict_data_IRxTrial"][trial_index]
    except KeyError:
        return [f"IRxTrial: no data for trial {trial_index}"]

    lines = [
        f"DebutRW: {int(trial_ir_data['DebutRW'])}",
        f"FinRW: {int(trial_ir_data['FinRW'])}",
    ]
    timestamps = np.asarray(trial_ir_data["forks_timestamps"])
    if timestamps.size == 0:
        lines.append("forks_timestamps: []")
    else:
        timestamps_ms = [str(int(val)) for val in timestamps.tolist()]
        lines.append(f"forks_timestamps: [{', '.join(timestamps_ms)}]")

    timespent = np.asarray(trial_ir_data["timespent_each_time"])
    timespent = np.asarray(timespent)
    if timespent.size == 0:
        lines.append("timespent_each_time: []")
        return lines

    times_ms = [str(int(val)) for val in timespent.tolist()]
    lines.append(f"timespent_each_time: [{', '.join(times_ms)}]")
    return lines


# -----------------------------------------------------------------------------
# Performance plots
# -----------------------------------------------------------------------------

def plot_performance(perf_data, info_data, trial_ir_analysis=None, show=True, block=False):
    has_trial_ir = trial_ir_analysis is not None and "dict_data_IRxTrial" in trial_ir_analysis
    if has_trial_ir:
        fig, axes = plt.subplots(1, 2, figsize=(9.5, 4.2), gridspec_kw={"width_ratios": [1, 1.2]})
        ax = axes[0]
        ax_time = axes[1]
    else:
        fig = plt.figure()
        ax = fig.add_subplot(111)
    ax.set_title("Waiting for data...")
    ax.set_xlabel("Session")
    ax.set_ylabel("Perf")

    xloc = 1
    n_trials = info_data.get("nTotalTrials", 0)
    y_go = perf_data.get("go", 0)
    y_nogo = perf_data.get("nogo", 0)
    y_total = perf_data.get("total", 0)

    ax.plot(xloc, y_go, marker="o", linewidth=1.5, color="b", markersize=3)
    ax.plot(xloc, y_nogo, marker="o", linewidth=1.5, color="r", markersize=3)
    ax.plot(xloc, y_total, marker="o", linewidth=1.5, color="k", markersize=3)
    ax.set_title(f"Session - {n_trials} trials")
    ax.set_ylim(-10, 110)
    ax.set_yticks([0, 50, 100])
    ax.legend(["Go", "NoGo", "Total"], frameon=False)

    if has_trial_ir:
        results_table = info_data["ResultsTable"]
        trial_types = _to_ttypes_ids(results_table)
        rng = np.random.default_rng(3)
        go_times = []
        nogo_times = []

        for trial_idx, trial_type in enumerate(trial_types):
            trial_data = trial_ir_analysis["dict_data_IRxTrial"].get(trial_idx)
            if trial_data is None:
                total_time = 0.0
            else:
                times = np.asarray(trial_data.get("timespent_each_time", []), dtype=float)
                total_time = float(np.nansum(times)) if times.size else 0.0

            if int(trial_type) == 1:
                go_times.append(total_time)
            elif int(trial_type) == 2:
                nogo_times.append(total_time)

        if go_times:
            x_go = np.ones(len(go_times)) + rng.uniform(-0.06, 0.06, len(go_times))
            ax_time.scatter(
                x_go,
                go_times,
                s=24,
                facecolors="white",
                edgecolors="b",
                linewidths=1.2,
                alpha=0.85,
                label="Go",
            )
        if nogo_times:
            x_nogo = np.full(len(nogo_times), 2.0) + rng.uniform(-0.06, 0.06, len(nogo_times))
            ax_time.scatter(
                x_nogo,
                nogo_times,
                s=24,
                facecolors="white",
                edgecolors="r",
                linewidths=1.2,
                alpha=0.85,
                label="NoGo",
            )

        ax_time.set_title("Reward-window IR time")
        ax_time.set_xticks([1, 2])
        ax_time.set_xticklabels(["Go", "NoGo"])
        ax_time.set_xlim(0.5, 2.5)
        ax_time.set_ylabel("Time spent in fork (ms)")
        ax_time.grid(True, axis="y", color="#E1E1E1", linewidth=0.7)
        ax_time.spines["top"].set_visible(False)
        ax_time.spines["right"].set_visible(False)
        y_values = go_times + nogo_times
        if y_values:
            y_max = max(y_values)
            ax_time.set_ylim(0, max(100, y_max + max(y_max * 0.12, 80)))

    fig.tight_layout()
    if show:
        plt.show(block=block)
    return fig

def plot_batch_session_performance(
    performance_by_file,
    trial_performance_by_file=None,
    show=True,
    block=False,
):
    """
    Plot Go, NoGo, and total performance across sessions from a batch GUI run.
    """
    if not performance_by_file:
        return None

    session_labels = []
    go_values = []
    nogo_values = []
    total_values = []
    sorted_sessions = sorted(
        performance_by_file.items(),
        key=lambda item: _natural_sort_key(Path(item[0]).stem or str(item[0])),
    )

    for session_key, perf_data in sorted_sessions:
        if not isinstance(perf_data, dict) or "error" in perf_data:
            continue
        session_labels.append(Path(session_key).stem or str(session_key))
        go_values.append(float(perf_data.get("go", np.nan)))
        nogo_values.append(float(perf_data.get("nogo", np.nan)))
        total_values.append(float(perf_data.get("total", np.nan)))

    if not session_labels:
        return None

    x = np.arange(len(session_labels))
    if trial_performance_by_file:
        fig, axes = plt.subplots(
            2,
            1,
            figsize=(10, 7.2),
            gridspec_kw={"height_ratios": [1.0, 1.25]},
        )
        ax = axes[0]
        ax_trials = axes[1]
    else:
        fig, ax = plt.subplots(figsize=(9.5, 4.6))
        ax_trials = None
    ax.plot(x, go_values, marker="o", color="b", lw=1.8, label="Go")
    ax.plot(x, nogo_values, marker="o", color="r", lw=1.8, label="NoGo")
    ax.plot(x, total_values, marker="o", color="k", lw=1.8, label="Total")
    ax.set_title("Performance across sessions", fontsize=13, fontweight="bold", loc="left")
    ax.set_xlabel("Session")
    ax.set_ylabel("Performance (%)")
    ax.set_ylim(-10, 110)
    ax.set_yticks([0, 50, 100])
    ax.set_xticks(x)
    ax.set_xticklabels(session_labels, rotation=45, ha="right")
    ax.grid(True, axis="y", color="#E1E1E1", linewidth=0.7)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.legend(frameon=False)

    if ax_trials is not None:
        all_x = []
        go_trial_perf = []
        nogo_trial_perf = []
        session_centers = []
        session_boundaries = []
        trial_session_labels = []
        x_offset = 0

        for session_key, perf_data in sorted_sessions:
            if not isinstance(perf_data, dict) or "error" in perf_data:
                continue
            trial_data = trial_performance_by_file.get(session_key, {})
            trial_types = np.asarray(trial_data.get("trial_type", []), dtype=float)
            correct = np.asarray(trial_data.get("correct", []), dtype=float)
            if trial_types.size == 0 or correct.size == 0:
                continue

            n_trials = min(len(trial_types), len(correct))
            trial_types = trial_types[:n_trials]
            correct = correct[:n_trials]
            x_trials = np.arange(x_offset, x_offset + n_trials)

            go_values = np.full(n_trials, np.nan)
            nogo_values = np.full(n_trials, np.nan)
            go_values[trial_types == 1] = correct[trial_types == 1]
            nogo_values[trial_types == 2] = correct[trial_types == 2]

            if trial_session_labels:
                session_boundaries.append(x_offset - 0.5)
            all_x.extend(x_trials.tolist())
            go_trial_perf.extend(go_values.tolist())
            nogo_trial_perf.extend(nogo_values.tolist())
            session_centers.append(x_offset + ((n_trials - 1) / 2))
            trial_session_labels.append(Path(session_key).stem or str(session_key))
            x_offset += n_trials

        if all_x:
            ax_trials.plot(
                all_x,
                go_trial_perf,
                marker="o",
                linestyle="None",
                color="b",
                markersize=3,
                alpha=0.75,
                label="Go",
            )
            ax_trials.plot(
                all_x,
                nogo_trial_perf,
                marker="o",
                linestyle="None",
                color="r",
                markersize=3,
                alpha=0.75,
                label="NoGo",
            )
            for boundary in session_boundaries:
                ax_trials.axvline(boundary, color="gray", ls="--", lw=1, alpha=0.55)
            ax_trials.set_xticks(session_centers)
            ax_trials.set_xticklabels(trial_session_labels, rotation=45, ha="right")
            ax_trials.set_xlim(-1, max(all_x) + 1)
        else:
            ax_trials.text(
                0.5,
                0.5,
                "No trial-level performance data",
                ha="center",
                va="center",
                transform=ax_trials.transAxes,
            )

        ax_trials.set_title("Trial-by-trial performance", fontsize=12, fontweight="bold", loc="left")
        ax_trials.set_xlabel("Trials across sessions")
        ax_trials.set_ylabel("Correct")
        ax_trials.set_ylim(-0.15, 1.15)
        ax_trials.set_yticks([0, 1])
        ax_trials.set_yticklabels(["Incorrect", "Correct"])
        ax_trials.grid(True, axis="y", color="#E1E1E1", linewidth=0.7)
        ax_trials.spines["top"].set_visible(False)
        ax_trials.spines["right"].set_visible(False)
        ax_trials.legend(frameon=False)

    fig.tight_layout()
    if show:
        plt.show(block=block)
    return fig


# -----------------------------------------------------------------------------
# Single-session signal and occupancy plots
# -----------------------------------------------------------------------------

def plot_ir_events(data_session_dict, ir_events, show=True, block=False):
    fig = plt.figure()
    ax_ir = fig.add_subplot(2, 1, 1)
    ax_diff = fig.add_subplot(2, 1, 2, sharex=ax_ir)

    data_ir = data_session_dict["dataIR"]["full"]
    mean_ir_val = data_session_dict["dataIR"]["mean"]
    y_diff = ir_events["Y"]
    n_events = len(ir_events["debut_fork"])

    ax_ir.plot(data_ir, color="k")
    ax_ir.plot([0, len(data_ir)], [mean_ir_val, mean_ir_val], lw=2, color="r")
    ax_ir.set_ylabel("IR")

    ax_diff.plot(y_diff, color="red")
    ax_diff.set_ylabel("d(IR)")
    ax_diff.set_xlabel("Sample")

    for d_fork in ir_events["debut_fork"]:
        if d_fork < len(y_diff):
            ax_diff.plot(d_fork, y_diff[d_fork], "*", color="green")
    for d_not_fork in ir_events["debut_nontaken"]:
        if d_not_fork < len(y_diff):
            ax_diff.plot(d_not_fork, y_diff[d_not_fork], "*", color="orange")
    for end_fork in ir_events["end_fork"]:
        if end_fork < len(y_diff):
            ax_diff.plot(end_fork, y_diff[end_fork], "*", color="blue")

    ax_ir.set_title(f"Session IR events - {n_events} events")
    fig.tight_layout()
    if show:
        plt.show(block=block)
    return fig

def plot_trial_ir_and_sound(
    data_session_dict,
    trial_ir_analysis=None,
    ir_events=None,
    trial_index=0,
    pre_s=2.0,
    post_s=None,
    fe=1000,
    trial_bin_s=0.1,
    show_result_table=True,
    result_fields=None,
    show=True,
    block=False,
):
    data_trial_id = np.asarray(data_session_dict["trialID"]["full"])
    data_ir = np.asarray(data_session_dict["dataIR"]["full"])
    sound_signal = np.asarray(data_session_dict["sound_signal"])

    trial_markers = np.where(data_trial_id == 99)[0]
    if len(trial_markers) == 0:
        raise ValueError("No trial markers found in trialID signal.")
    if trial_index < 0 or trial_index >= len(trial_markers):
        raise IndexError(
            f"trial_index={trial_index} is outside available trials 0-{len(trial_markers) - 1}."
        )

    trial_marker_s = float(trial_markers[trial_index] * trial_bin_s)
    if post_s is None:
        if trial_index + 1 < len(trial_markers):
            post_s = float((trial_markers[trial_index + 1] - trial_markers[trial_index]) * trial_bin_s)
        else:
            post_s = 5.0

    start_s = max(0.0, trial_marker_s - float(pre_s))
    end_s = trial_marker_s + float(post_s)
    start_sample = max(0, int(start_s * fe))
    end_sample = min(max(len(data_ir), len(sound_signal)), int(end_s * fe))

    ir_end = min(end_sample, len(data_ir))
    sound_end = min(end_sample, len(sound_signal))
    ir_samples = np.arange(start_sample, ir_end)
    sound_samples = np.arange(start_sample, sound_end)
    ir_time = (ir_samples / fe) - trial_marker_s
    sound_time = (sound_samples / fe) - trial_marker_s

    fig, axes = plt.subplots(3, 1, figsize=(5, 8.2), sharex=True, dpi=140)
    fig.patch.set_facecolor("white")
    ax_ir, ax_sound, ax_trial = axes

    ax_ir.plot(ir_time, data_ir[start_sample:ir_end], color="k", linewidth=1.2)
    ax_ir.axvline(0, color="#C44E52", linewidth=1.6, linestyle="--", label="Trial marker")
    if ir_events is not None:
        debut_fork = np.asarray(ir_events["debut_fork"], dtype=int)
        end_fork = np.asarray(ir_events["end_fork"], dtype=int)

        debut_in_trial = debut_fork[
            (debut_fork >= start_sample)
            & (debut_fork < ir_end)
        ]
        end_in_trial = end_fork[
            (end_fork >= start_sample)
            & (end_fork < ir_end)
        ]

        if len(debut_in_trial) > 0:
            ax_ir.plot(
                (debut_in_trial / fe) - trial_marker_s,
                data_ir[debut_in_trial],
                "*",
                color="green",
                markersize=8,
                label="debut_fork",
            )
        if len(end_in_trial) > 0:
            ax_ir.plot(
                (end_in_trial / fe) - trial_marker_s,
                data_ir[end_in_trial],
                "*",
                color="blue",
                markersize=8,
                label="end_fork",
            )
    ax_ir.set_ylabel("IR", fontsize=11)
    ax_ir.set_title(f"Trial {trial_index + 1}: IR and sound signal", fontsize=15, fontweight="bold", loc="left")
    ax_ir.legend(frameon=False, loc="upper right", fontsize=9)
    if show_result_table:
        trial_lines = [
            _format_results_table_row(
            data_session_dict.get("ResultsTable"),
            trial_index,
            result_fields=result_fields,
            )
        ]
        trial_lines.extend(_format_trial_ir_times(trial_ir_analysis, trial_index))
        trial_text = "\n".join(trial_lines)
        ax_ir.text(
            0.02,
            0.96,
            trial_text,
            transform=ax_ir.transAxes,
            ha="left",
            va="top",
            fontsize=8.5,
            color="#222222",
            bbox={
                "boxstyle": "round,pad=0.35",
                "facecolor": "white",
                "edgecolor": "#BDBDBD",
                "alpha": 0.88,
            },
        )

    ax_sound.plot(sound_time, sound_signal[start_sample:sound_end], color="#2F6F9F", linewidth=1.2)
    ax_sound.axvline(0, color="#C44E52", linewidth=1.6, linestyle="--")
    ax_sound.set_ylabel("Sound", fontsize=11)

    trial_samples = np.arange(
        max(0, int(start_s / trial_bin_s)),
        min(len(data_trial_id), int(end_s / trial_bin_s)),
    )
    trial_time = (trial_samples * trial_bin_s) - trial_marker_s
    ax_trial.step(
        trial_time,
        data_trial_id[trial_samples],
        where="post",
        color="#6A4C93",
        linewidth=1.2,
    )
    ax_trial.axvline(0, color="#C44E52", linewidth=1.6, linestyle="--")
    ax_trial.set_ylabel("TrialID", fontsize=11)
    ax_trial.set_xlabel("Time from trial marker (s)", fontsize=11)

    for ax in axes:
        ax.set_facecolor("#FBFBFB")
        ax.grid(True, axis="both", color="#E1E1E1", linewidth=0.7)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color("#777777")
        ax.spines["bottom"].set_color("#777777")
        ax.tick_params(axis="both", labelsize=9, colors="#333333")

    fig.tight_layout()
    if show:
        plt.show(block=block)
    return fig

def plot_ir_occupancy_by_sound(data_session_dict, trial_ir_analysis, show=True, block=False):
    viz_visits = trial_ir_analysis["viz_visits"]
    if viz_visits.size == 0:
        return None
    x_label = trial_ir_analysis.get("occupancy_x_label", "Time (samples; 1000 = RW start)")
    plot_title = trial_ir_analysis.get("occupancy_title", "IR occupancy aligned to reward window")

    def _add_trial_lines(ax, viz_data):
        if viz_data.size == 0:
            return
        ax.hlines(
            np.arange(viz_data.shape[0] + 1) - 0.5,
            -0.5,
            viz_data.shape[1] - 0.5,
            colors="#8AACC4",
            linewidths=0.35,
            alpha=0.65,
        )

    def _mean_occupancy(viz_data):
        if viz_data.size == 0:
            return np.array([])
        valid = np.isfinite(viz_data)
        counts = valid.sum(axis=0)
        summed = np.nansum(viz_data, axis=0)
        mean_values = np.full(viz_data.shape[1], np.nan, dtype=float)
        has_data = counts > 0
        mean_values[has_data] = summed[has_data] / counts[has_data]
        return mean_values

    results_table = data_session_dict["ResultsTable"]
    trial_types = _to_ttypes_ids(results_table)
    analyzed_rows = np.array(
        sorted(trial_ir_analysis["dict_data_IRxTrial"].keys()),
        dtype=int,
    )

    if len(trial_types) == viz_visits.shape[0]:
        rows_sound1 = analyzed_rows[trial_types[analyzed_rows] == 1]
        rows_sound2 = analyzed_rows[trial_types[analyzed_rows] == 2]
        viz_sound1 = viz_visits[rows_sound1, :]
        viz_sound2 = viz_visits[rows_sound2, :]

        fig, axes = plt.subplots(
            2,
            2,
            figsize=(12, 8),
            gridspec_kw={"height_ratios": [3, 1]},
        )

        ax_hm_1 = axes[0, 0]
        ax_hm_2 = axes[0, 1]
        ax_plot_1 = axes[1, 0]
        ax_plot_2 = axes[1, 1]

        if viz_sound1.size > 0:
            ax_hm_1.imshow(
                viz_sound1,
                aspect="auto",
                interpolation="nearest",
                cmap="Greys",
                vmin=0,
                vmax=1,
            )
        else:
            ax_hm_1.text(
                0.5,
                0.5,
                "No SoundId=1 trials",
                ha="center",
                va="center",
                transform=ax_hm_1.transAxes,
            )

        if viz_sound2.size > 0:
            ax_hm_2.imshow(
                viz_sound2,
                aspect="auto",
                interpolation="nearest",
                cmap="Greys",
                vmin=0,
                vmax=1,
            )
        else:
            ax_hm_2.text(
                0.5,
                0.5,
                "No SoundId=2 trials",
                ha="center",
                va="center",
                transform=ax_hm_2.transAxes,
            )

        _add_trial_lines(ax_hm_1, viz_sound1)
        _add_trial_lines(ax_hm_2, viz_sound2)
        ax_hm_1.set_title(f"SoundId = 1 (n={viz_sound1.shape[0]})")
        ax_hm_2.set_title(f"SoundId = 2 (n={viz_sound2.shape[0]})")
        ax_hm_1.set_ylabel("Trial index")
        ax_hm_1.set_xlabel(x_label)
        ax_hm_2.set_xlabel(x_label)

        occ_sound1 = _mean_occupancy(viz_sound1)
        occ_sound2 = _mean_occupancy(viz_sound2)

        if occ_sound1.size > 0:
            ax_plot_1.plot(
                occ_sound1 ,
                linestyle="-",
                lw=2,
                color="black",
                alpha=0.75,
            )
        else:
            ax_plot_1.text(
                0.5,
                0.5,
                "No data",
                ha="center",
                va="center",
                transform=ax_plot_1.transAxes,
            )

        if occ_sound2.size > 0:
            ax_plot_2.plot(
                occ_sound2 ,
                linestyle="-",
                lw=2,
                color="black",
                alpha=0.75,
            )
        else:
            ax_plot_2.text(
                0.5,
                0.5,
                "No data",
                ha="center",
                va="center",
                transform=ax_plot_2.transAxes,
            )

        ax_plot_1.set_xlabel(x_label)
        ax_plot_2.set_xlabel(x_label)
        ax_plot_1.set_ylabel("Mean over trials")
        ax_plot_2.set_ylabel("")
        ax_plot_1.set_ylim(0.1,1.1)
        ax_plot_2.set_ylim(0.1,1.1)
        fig.suptitle(plot_title)
        fig.tight_layout()
        if show:
            plt.show(block=block)
        return fig

    fig = plt.figure()
    ax_hm = fig.add_subplot(1, 1, 1)
    ax_hm.imshow(viz_visits, aspect="auto", interpolation="nearest", cmap="Greys")
    _add_trial_lines(ax_hm, viz_visits)
    ax_hm.set_title(plot_title)
    ax_hm.set_xlabel(x_label)
    ax_hm.set_ylabel("Trial index")
    fig.tight_layout()
    if show:
        plt.show(block=block)
    return fig


# -----------------------------------------------------------------------------
# Sound response plots
# -----------------------------------------------------------------------------

def plot_hit_by_sound(
    hit_by_sound,
    show=True,
    block=False,
    title: str | None = None,
    save_path: Path | str | None = None,
    sound_x=None,
):
    if not hit_by_sound:
        return None

    batch_metadata = {}
    if isinstance(hit_by_sound, dict) and "hit_by_sound" in hit_by_sound:
        batch_metadata = hit_by_sound
        hit_by_sound = hit_by_sound.get("hit_by_sound", {})
        if not hit_by_sound:
            return None

    normalized_hit_by_sound = {
        int(sid): stats for sid, stats in hit_by_sound.items()
    }
    sound_ids = sorted(normalized_hit_by_sound.keys())
    fa_pct = [normalized_hit_by_sound[sid]["FAs_pct"] for sid in sound_ids]
    n_trials = [normalized_hit_by_sound[sid].get("n_trials", np.nan) for sid in sound_ids]
    if sound_x is None:
        sound_x = np.asarray(sound_ids, dtype=float)
        x_label = "SoundId"
    else:
        sound_x = np.asarray(sound_x, dtype=float)
        if len(sound_x) != len(sound_ids):
            raise ValueError("sound_x must have the same length as hit_by_sound.")
        x_label = "Sound"

    fig, ax = plt.subplots(figsize=(8.5, 5.2), dpi=140)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("#FBFBFB")

    ax.plot(
        sound_x,
        fa_pct,
        color="k",
        linewidth=2,
        marker="o",
        markersize=7,
        markerfacecolor="#FFFFFF",
        markeredgecolor="#2F6F9F",
        markeredgewidth=2,
    )

    for x_value, pct, n_trial in zip(sound_x, fa_pct, n_trials):
        if not np.isfinite(n_trial):
            continue
        ax.annotate(
            f"n={int(n_trial)}",
            xy=(x_value, pct),
            xytext=(0, 12),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=8.5,
            color="#333333",
        )

    animal_name = batch_metadata.get("animal_name", "")
    hit_source = batch_metadata.get("hit_source", "")
    if title is None:
        title = "%GO by sound" if batch_metadata else "FA percentage by sound"
        if animal_name:
            title += f" - {animal_name}"

    ax.set_title(title, fontsize=16, fontweight="bold", loc="left", pad=14)
    if batch_metadata:
        subtitle = "Batch analysis across sessions"
        if hit_source:
            subtitle += f" | Source: {hit_source}"
        ax.text(
            0,
            1.02,
            subtitle,
            transform=ax.transAxes,
            fontsize=10,
            color="#555555",
            va="bottom",
        )

    ax.set_xlabel(x_label, fontsize=12, labelpad=10)
    ax.set_ylabel("GO trials (%)", fontsize=12, labelpad=10)
    ax.set_xticks(sound_x)
    ax.set_ylim(0, max(100, max(fa_pct) * 1.18 if fa_pct else 100))
    ax.grid(True, axis="y", color="#D9D9D9", linewidth=0.8)
    ax.grid(True, axis="x", color="#EFEFEF", linewidth=0.6)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#777777")
    ax.spines["bottom"].set_color("#777777")
    ax.tick_params(axis="both", labelsize=10, colors="#333333")
    fig.tight_layout()
    if save_path is not None:
        save_path = Path(save_path)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=300, bbox_inches="tight", facecolor="white")
    if show:
        plt.show(block=block)
    return fig


# -----------------------------------------------------------------------------
# Batch learning and threshold plots
# -----------------------------------------------------------------------------

def plot_batch_go_performance_by_window(
    batch_hit_by_sound,
    alldays_datekeys=None,
    n_size_window: int = 10,
    ax=None,
    labels=None,
):
    """
    Plot GO/correct performance in fixed trial windows across session days.

    batch_hit_by_sound can be one animal dict, a list/tuple of animal dicts, or
    the dict returned by load_batch_ir_go_by_sound_files(). For one animal,
    returns all_perf as an array. For multiple animals, returns all_perf as a
    dict keyed by label.
    """
    if (
        isinstance(batch_hit_by_sound, (list, tuple))
        and len(batch_hit_by_sound) == 1
        and isinstance(batch_hit_by_sound[0], dict)
        and not any(
            isinstance(value, dict) and "alldataGO" in value
            for value in batch_hit_by_sound[0].values()
        )
    ):
        batch_hit_by_sound = batch_hit_by_sound[0]

    is_loaded_batches = (
        isinstance(batch_hit_by_sound, dict)
        and len(batch_hit_by_sound) > 0
        and not any(
            isinstance(value, dict) and "alldataGO" in value
            for value in batch_hit_by_sound.values()
        )
        and all(isinstance(value, dict) for value in batch_hit_by_sound.values())
    )

    if is_loaded_batches:
        batch_dicts = list(batch_hit_by_sound.values())
        loaded_labels = list(batch_hit_by_sound.keys())
        is_multi_animal = True
    elif isinstance(batch_hit_by_sound, (list, tuple)):
        batch_dicts = list(batch_hit_by_sound)
        loaded_labels = None
        is_multi_animal = True
    else:
        batch_dicts = [batch_hit_by_sound]
        loaded_labels = None
        is_multi_animal = False

    if labels is None:
        labels = loaded_labels or [f"animal_{idx + 1}" for idx in range(len(batch_dicts))]
    elif isinstance(labels, str):
        labels = [labels]
    else:
        labels = list(labels)

    if len(labels) != len(batch_dicts):
        raise ValueError("labels must have the same length as batch_hit_by_sound.")

    if alldays_datekeys is None:
        all_key_lists = [sorted(batch_dict.keys()) for batch_dict in batch_dicts]
    elif (
        is_multi_animal
        and isinstance(alldays_datekeys, (list, tuple))
        and len(alldays_datekeys) == len(batch_dicts)
        and all(isinstance(item, (list, tuple)) for item in alldays_datekeys)
    ):
        all_key_lists = [list(keys) for keys in alldays_datekeys]
    else:
        all_key_lists = [list(alldays_datekeys) for _ in batch_dicts]

    if ax is None:
        fig, ax = plt.subplots(figsize=(8, 4))
    else:
        fig = ax.figure

    all_perf_by_label = {}
    color_cycle = plt.rcParams["axes.prop_cycle"].by_key().get("color", [])
    colors_by_label = {
        label: color_cycle[idx % len(color_cycle)] if color_cycle else None
        for idx, label in enumerate(labels)
    }

    for batch_dict, datekeys, label in zip(batch_dicts, all_key_lists, labels):
        all_perf = []
        x_offset = 0
        animal_color = colors_by_label[label]

        for datekey in datekeys:
            alldata_go = np.asarray(batch_dict[datekey]["alldataGO"], dtype=float)
            n = len(alldata_go) // n_size_window * n_size_window
            if n == 0:
                continue

            a_reshaped = alldata_go[:n].reshape(-1, n_size_window)
            n_trials_x_arr = np.sum(~np.isnan(a_reshaped), axis=1)
            perf_across_session = np.divide(
                np.nansum(a_reshaped, axis=1),
                n_trials_x_arr,
                out=np.full(a_reshaped.shape[0], np.nan),
                where=n_trials_x_arr > 0,
            )
            all_perf.extend(perf_across_session)

            n_points = a_reshaped.shape[0]
            x = np.arange(x_offset, x_offset + n_points)
            line_label = label if x_offset == 0 else None
            ax.plot(x, perf_across_session, color=animal_color, label=line_label)
            ax.axvline(x_offset - 0.5, color="gray", ls="--", alpha=0.25)
            x_offset += n_points

        all_perf_by_label[label] = np.asarray(all_perf)

    ax.set_xlabel(f"Trial window ({n_size_window} trials/bin)")
    ax.set_ylabel("Performance")
    ax.set_ylim(-0.05, 1.05)
    if len(batch_dicts) > 1:
        ax.legend(frameon=False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()

    if is_multi_animal:
        return fig, ax, all_perf_by_label
    return fig, ax, next(iter(all_perf_by_label.values()))

def plot_batch_go_mean_curve(
    loaded_batches,
    labels=None,
    alldays_datekeys=None,
    n_size_window: int = 10,
    ax=None,
    error: str = "std",
    xlim: int | None = 750,
    fit_sigmoid: bool = True,
    threshold: float | None = 0.8,
):
    """
    Plot the mean performance curve across animals with STD or SEM shading.

    When threshold is not None, a horizontal threshold line is drawn and
    matrix_data["trials_to_threshold"] is filled from the sigmoid fit when it
    crosses the threshold, otherwise from the first mean bin above threshold.
    """
    from behavior_functions import batch_go_performance_matrix

    matrix_data = batch_go_performance_matrix(
        loaded_batches,
        labels=labels,
        alldays_datekeys=alldays_datekeys,
        n_size_window=n_size_window,
    )

    if ax is None:
        fig, ax = plt.subplots(figsize=(8, 4))
    else:
        fig = ax.figure

    x = matrix_data["x"]
    mean_curve = matrix_data["mean_curve"]
    err_curve = matrix_data["sem_curve"] if error == "sem" else matrix_data["std_curve"]

    ax.errorbar(
        x,
        mean_curve,
        yerr=err_curve,
        color="k",
        marker="o",
        linestyle="-",
        lw=2,
        markersize=5,
        capsize=3,
        elinewidth=1.2,
        label=error.upper(),
    )
    if fit_sigmoid:
        try:
            

            valid = np.isfinite(x) & np.isfinite(mean_curve)
            if xlim is not None:
                valid = valid & (x <= xlim)
            x_fit_data = x[valid]
            y_fit_data = mean_curve[valid]
            if len(y_fit_data) >= 4:
                y_min = float(np.nanmin(y_fit_data))
                y_max = float(np.nanmax(y_fit_data))
                x_mid_guess = float(
                    x_fit_data[np.argmin(np.abs(y_fit_data - ((y_min + y_max) / 2.0)))]
                )
                p0 = [
                    max(0.0, y_min),
                    min(1.0, y_max),
                    x_mid_guess,
                    max(float(n_size_window), 1.0),
                ]
                bounds = (
                    [0.0, 0.0, float(np.min(x_fit_data)), 0.01],
                    [1.0, 1.0, float(np.max(x_fit_data)), float(np.max(x_fit_data) * 10.0)],
                )
                popt, _pcov = curve_fit(
                    _learning_sigmoid,
                    x_fit_data,
                    y_fit_data,
                    p0=p0,
                    bounds=bounds,
                    maxfev=20000,
                )
                fit_x_max = xlim if xlim is not None else float(np.max(x_fit_data))
                fit_x = np.linspace(float(np.min(x_fit_data)), fit_x_max, 300)
                fit_y = _learning_sigmoid(fit_x, *popt)
                ax.plot(
                    fit_x,
                    fit_y,
                    color="#C44E52",
                    lw=2,
                    ls="-",
                    label="Sigmoid fit",
                )
                trials_to_threshold = np.nan
                if threshold is not None:
                    bottom, top, x_mid, slope = popt
                    if bottom < threshold < top:
                        ratio = (top - bottom) / (threshold - bottom) - 1.0
                        if ratio > 0:
                            trials_to_threshold = float(x_mid - slope * np.log(ratio))
                matrix_data["sigmoid_fit"] = {
                    "params": {
                        "bottom": float(popt[0]),
                        "top": float(popt[1]),
                        "x_mid": float(popt[2]),
                        "slope": float(popt[3]),
                    },
                    "fit_x": fit_x,
                    "fit_y": fit_y,
                    "trials_to_threshold": trials_to_threshold,
                }
        except Exception as exc:
            matrix_data["sigmoid_fit_error"] = str(exc)

    if threshold is not None:
        ax.axhline(
            threshold,
            color="#C44E52",
            ls="--",
            lw=1.0,
            alpha=0.8,
        )
        trials_to_threshold = matrix_data.get("sigmoid_fit", {}).get(
            "trials_to_threshold",
            np.nan,
        )
        threshold_method = "sigmoid"
        if not np.isfinite(trials_to_threshold):
            reached = np.where(mean_curve >= threshold)[0]
            if len(reached) > 0:
                trials_to_threshold = float(x[reached[0]])
                threshold_method = "first_bin"
            else:
                threshold_method = "not_reached"
        matrix_data["threshold"] = threshold
        matrix_data["trials_to_threshold"] = trials_to_threshold
        matrix_data["trials_to_threshold_method"] = threshold_method
        if np.isfinite(trials_to_threshold):
            ax.axvline(
                trials_to_threshold,
                color="#C44E52",
                ls=":",
                lw=1.0,
                alpha=0.8,
            )

    ax.set_xlabel(f"Trials ({n_size_window} trials/bin)")
    ax.set_ylabel("Performance")
    ax.set_ylim(-0.05, 1.05)
    if xlim is not None:
        ax.set_xlim(0, xlim)
    ax.legend(frameon=False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    return fig, ax, matrix_data

def plot_trials_to_threshold_summary(
    trials_to_threshold_by_group: dict,
    ax=None,
    ylabel: str = "Trials to 80% performance",
    title: str = "Learning speed by protocol",
    show_points: bool = True,
    annotate: bool = False,
):
    """
    Plot group mean +/- SEM for trials-to-threshold dictionaries.

    Expected input:
    {
        "protocol_a": {"animal_1": value, "animal_2": value},
        "protocol_b": {"animal_3": value},
    }
    """
    if ax is None:
        fig, ax = plt.subplots(figsize=(8.5, 4.8))
    else:
        fig = ax.figure

    group_names = list(trials_to_threshold_by_group.keys())
    x = np.arange(len(group_names))
    color_cycle = plt.rcParams["axes.prop_cycle"].by_key().get("color", [])

    means = []
    sems = []
    clean_labels = []
    all_values_by_group = {}

    for group_name in group_names:
        animal_values = trials_to_threshold_by_group[group_name]
        values = np.asarray(list(animal_values.values()), dtype=float)
        values = values[np.isfinite(values)]
        all_values_by_group[group_name] = values
        means.append(float(np.nanmean(values)) if len(values) else np.nan)
        if len(values) > 1:
            sems.append(float(np.nanstd(values, ddof=1) / np.sqrt(len(values))))
        else:
            sems.append(0.0)
        clean_labels.append(group_name.replace("_trials_to_80", "").replace("_", "\n"))

    bar_x = x - 0.16
    dist_x = x + 0.18

    ax.errorbar(
        bar_x,
        means,
        yerr=sems,
        color="k",
        marker="o",
        linestyle="None",
        markersize=8,
        markerfacecolor="white",
        markeredgecolor="k",
        markeredgewidth=1.8,
        capsize=5,
        elinewidth=1.5,
        label="Mean +/- SEM",
    )

    if show_points:
        rng = np.random.default_rng(4)
        for group_idx, group_name in enumerate(group_names):
            color = color_cycle[group_idx % len(color_cycle)] if color_cycle else "#333333"
            animal_values = trials_to_threshold_by_group[group_name]
            for animal_name, value in animal_values.items():
                if not np.isfinite(value):
                    continue
                jitter = rng.uniform(-0.055, 0.055)
                ax.plot(
                    dist_x[group_idx] + jitter,
                    value,
                    marker="o",
                    markersize=6,
                    markerfacecolor="white",
                    markeredgecolor=color,
                    markeredgewidth=1.6,
                    linestyle="None",
                )
            values = all_values_by_group[group_name]
            if len(values) > 1:
                ax.plot(
                    [dist_x[group_idx], dist_x[group_idx]],
                    [np.nanmin(values), np.nanmax(values)],
                    color=color,
                    lw=1,
                    alpha=0.45,
                )

    if annotate:
        for group_idx, (mean_value, sem_value, group_name) in enumerate(zip(means, sems, group_names)):
            n_animals = len(all_values_by_group[group_name])
            ax.text(
                group_idx,
                mean_value + sem_value + 45,
                f"mean={mean_value:.0f}\nSEM={sem_value:.0f}\nn={n_animals}",
                ha="center",
                va="bottom",
                fontsize=8.5,
                color="#222222",
            )

    ax.set_xticks(x)
    ax.set_xticklabels(clean_labels)
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontsize=14, fontweight="bold", loc="left")
    ax.grid(True, axis="y", color="#E1E1E1", linewidth=0.7)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    finite_means = np.asarray(means, dtype=float)
    finite_sems = np.asarray(sems, dtype=float)
    mean_tops = finite_means + finite_sems
    raw_values = [
        value
        for values in all_values_by_group.values()
        for value in np.asarray(values, dtype=float)
        if np.isfinite(value)
    ]
    y_candidates = [value for value in mean_tops if np.isfinite(value)] + raw_values
    if y_candidates:
        y_max = max(y_candidates)
        y_padding = max(y_max * 0.12, 80)
        if annotate:
            y_padding += 80
        ax.set_ylim(0, y_max + y_padding)
    else:
        ax.set_ylim(0, 100)
    fig.tight_layout()

    summary = {
        group_name: {
            "mean": mean,
            "sem": sem,
            "n": len(all_values_by_group[group_name]),
            "values": all_values_by_group[group_name],
        }
        for group_name, mean, sem in zip(group_names, means, sems)
    }
    return fig, ax, summary


def plot_trials_to_threshold_boxplot_summary(
    trials_to_threshold_by_group: dict,
    ax=None,
    ylabel: str = "Trials to 80% performance",
    title: str = "Learning speed by protocol",
    show_points: bool = True,
    annotate: bool = False,
    showfliers: bool = False,
    box_width: float = 0.45,
):
    """
    Plot group boxplots for trials-to-threshold dictionaries.

    Expected input:
    {
        "protocol_a": {"animal_1": value, "animal_2": value},
        "protocol_b": {"animal_3": value},
    }
    """
    if ax is None:
        fig, ax = plt.subplots(figsize=(8.5, 4.8))
    else:
        fig = ax.figure

    group_names = list(trials_to_threshold_by_group.keys())
    x = np.arange(len(group_names))
    color_cycle = plt.rcParams["axes.prop_cycle"].by_key().get("color", [])

    clean_labels = []
    all_values_by_group = {}
    box_values = []
    box_positions = []
    box_colors = []

    for group_idx, group_name in enumerate(group_names):
        animal_values = trials_to_threshold_by_group[group_name]
        values = np.asarray(list(animal_values.values()), dtype=float)
        values = values[np.isfinite(values)]
        all_values_by_group[group_name] = values
        clean_labels.append(group_name.replace("_trials_to_80", "").replace("_", "\n"))
        if len(values):
            box_values.append(values)
            box_positions.append(x[group_idx])
            color = color_cycle[group_idx % len(color_cycle)] if color_cycle else "#666666"
            box_colors.append(color)

    if box_values:
        boxplot = ax.boxplot(
            box_values,
            positions=box_positions,
            widths=box_width,
            patch_artist=True,
            showfliers=showfliers,
            medianprops={"color": "k", "linewidth": 1.6},
            whiskerprops={"color": "#555555", "linewidth": 1.2},
            capprops={"color": "#555555", "linewidth": 1.2},
            boxprops={"edgecolor": "#333333", "linewidth": 1.2},
        )
        for patch, color in zip(boxplot["boxes"], box_colors):
            patch.set_facecolor(color)
            patch.set_alpha(0.28)

    if show_points:
        rng = np.random.default_rng(4)
        for group_idx, group_name in enumerate(group_names):
            color = color_cycle[group_idx % len(color_cycle)] if color_cycle else "#333333"
            animal_values = trials_to_threshold_by_group[group_name]
            for _animal_name, value in animal_values.items():
                if not np.isfinite(value):
                    continue
                jitter = rng.uniform(-0.08, 0.08)
                ax.plot(
                    x[group_idx] + jitter,
                    value,
                    marker="o",
                    markersize=6,
                    markerfacecolor="white",
                    markeredgecolor=color,
                    markeredgewidth=1.5,
                    linestyle="None",
                    alpha=0.95,
                )

    summary = {}
    for group_name in group_names:
        values = all_values_by_group[group_name]
        if len(values):
            mean = float(np.nanmean(values))
            median = float(np.nanmedian(values))
            q1 = float(np.nanpercentile(values, 25))
            q3 = float(np.nanpercentile(values, 75))
            sem = float(np.nanstd(values, ddof=1) / np.sqrt(len(values))) if len(values) > 1 else 0.0
        else:
            mean = np.nan
            median = np.nan
            q1 = np.nan
            q3 = np.nan
            sem = np.nan
        summary[group_name] = {
            "mean": mean,
            "median": median,
            "q1": q1,
            "q3": q3,
            "iqr": q3 - q1 if np.isfinite(q1) and np.isfinite(q3) else np.nan,
            "sem": sem,
            "n": len(values),
            "values": values,
        }

    if annotate:
        for group_idx, group_name in enumerate(group_names):
            stats = summary[group_name]
            if not np.isfinite(stats["median"]):
                continue
            ax.text(
                group_idx,
                stats["q3"] + max(stats["q3"] * 0.06, 45),
                f"median={stats['median']:.0f}\nIQR={stats['iqr']:.0f}\nn={stats['n']}",
                ha="center",
                va="bottom",
                fontsize=8.5,
                color="#222222",
            )

    ax.set_xticks(x)
    ax.set_xticklabels(clean_labels)
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontsize=14, fontweight="bold", loc="left")
    ax.grid(True, axis="y", color="#E1E1E1", linewidth=0.7)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    raw_values = [
        value
        for values in all_values_by_group.values()
        for value in np.asarray(values, dtype=float)
        if np.isfinite(value)
    ]
    if raw_values:
        y_max = max(raw_values)
        y_padding = max(y_max * 0.12, 80)
        if annotate:
            y_padding += 80
        ax.set_ylim(0, y_max + y_padding)
    else:
        ax.set_ylim(0, 100)
    fig.tight_layout()

    return fig, ax, summary


def _pvalue_to_stars(pvalue):
    if not np.isfinite(pvalue):
        return "n/a"
    if pvalue < 0.001:
        return "***"
    if pvalue < 0.01:
        return "**"
    if pvalue < 0.05:
        return "*"
    return "ns"


def _permutation_difference_test(
    values_a,
    values_b,
    alternative="two-sided",
    statistic="mean",
    n_resamples=10000,
    random_state=0,
    max_exact=100000,
):
    import itertools
    import math

    values_a = np.asarray(values_a, dtype=float)
    values_b = np.asarray(values_b, dtype=float)
    combined = np.concatenate([values_a, values_b])
    n_a = len(values_a)
    n_total = len(combined)

    def calc_stat(a_values, b_values):
        if statistic == "mean":
            return float(np.nanmean(b_values) - np.nanmean(a_values))
        if statistic == "median":
            return float(np.nanmedian(b_values) - np.nanmedian(a_values))
        raise ValueError("statistic must be 'mean' or 'median'.")

    observed = calc_stat(values_a, values_b)

    def is_extreme(value):
        if alternative == "two-sided":
            return abs(value) >= abs(observed)
        if alternative == "greater":
            return value >= observed
        if alternative == "less":
            return value <= observed
        raise ValueError("alternative must be 'two-sided', 'greater', or 'less'.")

    n_combinations = math.comb(n_total, n_a)
    if n_combinations <= max_exact:
        extreme = 0
        total = 0
        all_indices = np.arange(n_total)
        for indices_a in itertools.combinations(all_indices, n_a):
            mask_a = np.zeros(n_total, dtype=bool)
            mask_a[list(indices_a)] = True
            perm_stat = calc_stat(combined[mask_a], combined[~mask_a])
            extreme += int(is_extreme(perm_stat))
            total += 1
        pvalue = extreme / total if total else np.nan
        mode = "exact"
    else:
        rng = np.random.default_rng(random_state)
        extreme = 0
        for _ in range(int(n_resamples)):
            shuffled = rng.permutation(combined)
            perm_stat = calc_stat(shuffled[:n_a], shuffled[n_a:])
            extreme += int(is_extreme(perm_stat))
        pvalue = (extreme + 1) / (int(n_resamples) + 1)
        mode = "random"

    return observed, float(pvalue), mode


def compare_trials_to_threshold_groups(
    trials_to_threshold_by_group: dict,
    group_a: str | None = None,
    group_b: str | None = None,
    test: str = "permutation",
    alternative: str = "two-sided",
    alpha: float = 0.05,
    permutation_statistic: str = "mean",
    n_resamples: int = 10000,
    random_state: int = 0,
    paired_by_position: bool = False,
):
    """
    Compare two trials-to-threshold groups and return a statistical summary.

    Expected input:
    {
        "protocol_a": {"animal_1": value, "animal_2": value},
        "protocol_b": {"animal_3": value},
    }

    Supported tests:
    - "nonparametric": Wilcoxon for paired data, Mann-Whitney for unpaired data
    - "permutation": dependency-free permutation test of mean or median difference
    - "mannwhitney": unpaired Mann-Whitney U test
    - "welch": unpaired Welch t-test
    - "ttest": unpaired Student t-test
    - "paired_ttest": paired t-test using animal names present in both groups
    - "wilcoxon": paired Wilcoxon signed-rank test using animal names present in both groups

    Set paired_by_position=True for paired tests when both groups are already
    in matching order but do not share the same animal labels.
    """
    group_names = list(trials_to_threshold_by_group.keys())
    if group_a is None or group_b is None:
        if len(group_names) != 2:
            raise ValueError(
                "Specify group_a and group_b when trials_to_threshold_by_group "
                "does not contain exactly two groups."
            )
        group_a, group_b = group_names

    if group_a not in trials_to_threshold_by_group:
        raise KeyError(f"group_a={group_a!r} was not found.")
    if group_b not in trials_to_threshold_by_group:
        raise KeyError(f"group_b={group_b!r} was not found.")

    values_a_by_animal = trials_to_threshold_by_group[group_a]
    values_b_by_animal = trials_to_threshold_by_group[group_b]
    test = test.lower()
    requested_test = test

    common_finite_animals = [
        animal
        for animal in values_a_by_animal
        if animal in values_b_by_animal
        and np.isfinite(values_a_by_animal[animal])
        and np.isfinite(values_b_by_animal[animal])
    ]
    if test == "nonparametric":
        if paired_by_position or len(common_finite_animals) >= 2:
            test = "wilcoxon"
        else:
            test = "mannwhitney"

    paired_tests = {"paired_ttest", "wilcoxon"}
    if test in paired_tests:
        if paired_by_position:
            raw_values_a = np.asarray(list(values_a_by_animal.values()), dtype=float)
            raw_values_b = np.asarray(list(values_b_by_animal.values()), dtype=float)
            n_pairs = min(len(raw_values_a), len(raw_values_b))
            finite_pairs = np.isfinite(raw_values_a[:n_pairs]) & np.isfinite(raw_values_b[:n_pairs])
            values_a = raw_values_a[:n_pairs][finite_pairs]
            values_b = raw_values_b[:n_pairs][finite_pairs]
            common_animals = None
            paired_labels = None
            pairing = "position"
        else:
            common_animals = common_finite_animals
            values_a = np.asarray([values_a_by_animal[animal] for animal in common_animals], dtype=float)
            values_b = np.asarray([values_b_by_animal[animal] for animal in common_animals], dtype=float)
            paired_labels = common_animals
            pairing = "animal_name"
    else:
        common_animals = None
        paired_labels = None
        pairing = None
        values_a = np.asarray(list(values_a_by_animal.values()), dtype=float)
        values_b = np.asarray(list(values_b_by_animal.values()), dtype=float)
        values_a = values_a[np.isfinite(values_a)]
        values_b = values_b[np.isfinite(values_b)]

    if test in paired_tests:
        if len(values_a) < 2:
            if paired_by_position:
                raise ValueError(
                    f"{test} needs at least two finite paired values, but only "
                    f"{len(values_a)} usable pair(s) were found by position."
                )
            raise ValueError(
                f"{test} needs at least two finite paired values, but only "
                f"{len(values_a)} usable pair(s) had matching animal names. "
                "Use paired_by_position=True if the groups are paired by order, "
                "or use test='mannwhitney' / test='permutation' for unpaired groups."
            )
    elif len(values_a) < 2 or len(values_b) < 2:
        raise ValueError(
            "Each group needs at least two finite values for an unpaired comparison."
        )

    if test == "permutation":
        statistic, pvalue, permutation_mode = _permutation_difference_test(
            values_a,
            values_b,
            alternative=alternative,
            statistic=permutation_statistic,
            n_resamples=n_resamples,
            random_state=random_state,
        )
        test_label = f"Permutation test ({permutation_statistic} difference)"
    else:
        try:
            from scipy import stats
        except ImportError as exc:
            raise ImportError(
                f"The '{test}' test requires scipy. Use test='permutation' "
                "for a dependency-free comparison."
            ) from exc

    if test == "permutation":
        pass
    elif test == "mannwhitney":
        result = stats.mannwhitneyu(values_a, values_b, alternative=alternative)
        test_label = "Mann-Whitney U"
        statistic = float(result.statistic)
        pvalue = float(result.pvalue)
    elif test == "welch":
        result = stats.ttest_ind(values_a, values_b, equal_var=False, alternative=alternative)
        test_label = "Welch t-test"
        statistic = float(result.statistic)
        pvalue = float(result.pvalue)
    elif test == "ttest":
        result = stats.ttest_ind(values_a, values_b, equal_var=True, alternative=alternative)
        test_label = "Student t-test"
        statistic = float(result.statistic)
        pvalue = float(result.pvalue)
    elif test == "paired_ttest":
        result = stats.ttest_rel(values_a, values_b, alternative=alternative)
        test_label = "Paired t-test"
        statistic = float(result.statistic)
        pvalue = float(result.pvalue)
    elif test == "wilcoxon":
        result = stats.wilcoxon(values_a, values_b, alternative=alternative)
        test_label = "Wilcoxon signed-rank"
        statistic = float(result.statistic)
        pvalue = float(result.pvalue)
    else:
        raise ValueError(
            "test must be 'nonparametric', 'permutation', 'mannwhitney', "
            "'welch', 'ttest', 'paired_ttest', or 'wilcoxon'."
        )

    summary = {
        "test": test_label,
        "requested_test": requested_test,
        "group_a": group_a,
        "group_b": group_b,
        "n_a": int(len(values_a)),
        "n_b": int(len(values_b)),
        "mean_a": float(np.nanmean(values_a)),
        "mean_b": float(np.nanmean(values_b)),
        "median_a": float(np.nanmedian(values_a)),
        "median_b": float(np.nanmedian(values_b)),
        "difference_mean_b_minus_a": float(np.nanmean(values_b) - np.nanmean(values_a)),
        "difference_median_b_minus_a": float(np.nanmedian(values_b) - np.nanmedian(values_a)),
        "statistic": statistic,
        "pvalue": pvalue,
        "alpha": float(alpha),
        "significant": bool(pvalue < alpha),
        "significance": _pvalue_to_stars(pvalue),
        "alternative": alternative,
        "values_a": values_a,
        "values_b": values_b,
    }
    if test == "permutation":
        summary["permutation_mode"] = permutation_mode
        summary["permutation_statistic"] = permutation_statistic
    if common_animals is not None:
        summary["paired_animals"] = common_animals
    if pairing is not None:
        summary["pairing"] = pairing
    if paired_labels is not None:
        summary["paired_labels"] = paired_labels
    return summary


# -----------------------------------------------------------------------------
# Learning-curve fitting helpers
# -----------------------------------------------------------------------------

def _learning_sigmoid(x, bottom, top, x_mid, slope):
    return bottom + (top - bottom) / (1.0 + np.exp(-(x - x_mid) / slope))


def _fit_learning_sigmoid_threshold(
    perf_values,
    n_size_window,
    threshold,
    fit_max_bin=None,
):
    try:
        from scipy.optimize import curve_fit
    except ImportError as exc:
        raise ImportError(
            "Sigmoid threshold fitting requires scipy in the current Python environment."
        ) from exc

    perf_values = np.asarray(perf_values, dtype=float)
    x_data = (np.arange(len(perf_values)) + 1) * n_size_window
    valid = np.isfinite(perf_values)
    if fit_max_bin is not None:
        valid = valid & (np.arange(len(perf_values)) <= int(fit_max_bin))
    x_data = x_data[valid]
    y_data = perf_values[valid]

    if len(y_data) < 4:
        return np.nan, None

    y_min = float(np.nanmin(y_data))
    y_max = float(np.nanmax(y_data))
    x_mid_guess = float(x_data[np.argmin(np.abs(y_data - ((y_min + y_max) / 2.0)))])
    bottom_guess = min(max(0.0, y_min), threshold - 1e-3)
    top_guess = max(min(1.0, y_max), threshold + 1e-3)
    p0 = [bottom_guess, top_guess, x_mid_guess, max(float(n_size_window), 1.0)]
    bounds = (
        [0.0, threshold + 1e-6, float(np.min(x_data)), 0.01],
        [threshold - 1e-6, 1.0, float(np.max(x_data)), float(np.max(x_data) * 10.0)],
    )

    try:
        popt, _pcov = curve_fit(
            _learning_sigmoid,
            x_data,
            y_data,
            p0=p0,
            bounds=bounds,
            maxfev=20000,
        )
    except Exception:
        return np.nan, None

    bottom, top, x_mid, slope = popt
    if not (bottom < threshold < top):
        return np.nan, {
            "params": popt,
            "x_data": x_data,
            "y_data": y_data,
            "fit_x": np.linspace(float(np.min(x_data)), float(np.max(x_data)), 300),
        }

    ratio = (top - bottom) / (threshold - bottom) - 1.0
    if ratio <= 0:
        threshold_x = np.nan
    else:
        threshold_x = float(x_mid - slope * np.log(ratio))

    fit_x = np.linspace(float(np.min(x_data)), float(np.max(x_data)), 300)
    fit_y = _learning_sigmoid(fit_x, *popt)
    return threshold_x, {
        "params": popt,
        "x_data": x_data,
        "y_data": y_data,
        "fit_x": fit_x,
        "fit_y": fit_y,
    }


# -----------------------------------------------------------------------------
# Batch learning plots with fitted thresholds
# -----------------------------------------------------------------------------

def plot_batch_go_performance_with_threshold_subplot(
    batch_hit_by_sound,
    alldays_datekeys=None,
    n_size_window: int = 10,
    threshold: float = 0.8,
    labels=None,
    max_trials_to_threshold: int | None = None,
    threshold_method: str = "sigmoid",
    crop_after_threshold: bool = True,
    extra_bins_after_threshold: int = 2,
    sigmoid_fit_max_bin: int | None = None,
    return_sigmoid_fits: bool = False,
):
    """
    Plot learning curves and trials needed to reach a performance threshold.

    The top subplot shows all animal learning curves together. The bottom
    subplot shows the trial count where each animal reaches `threshold`.
    Values above max_trials_to_threshold are treated as not reached.
    threshold_method can be "sigmoid" or "first_bin".
    When crop_after_threshold is True, the plotted curve stops at the threshold
    crossing plus extra_bins_after_threshold bins. Threshold fitting still uses
    the full curve.
    sigmoid_fit_max_bin optionally restricts sigmoid fitting to the early curve
    segment up to that bin index.
    """
    tmp_fig, tmp_ax, all_perf = plot_batch_go_performance_by_window(
        batch_hit_by_sound,
        alldays_datekeys=alldays_datekeys,
        n_size_window=n_size_window,
        labels=labels,
    )
    plt.close(tmp_fig)

    if isinstance(all_perf, dict):
        perf_by_label = all_perf
    else:
        label = labels[0] if isinstance(labels, (list, tuple)) else (labels or "animal_1")
        perf_by_label = {label: all_perf}

    animal_labels = list(perf_by_label.keys())
    n_animals = len(animal_labels)
    if n_animals == 0:
        raise ValueError("No animal performance data found to plot.")
    fig, axes = plt.subplots(
        2,
        1,
        figsize=(9, 6.5),
        sharex=False,
        gridspec_kw={"height_ratios": [2.4, 1.3]},
    )
    axes = np.asarray(axes)
    ax_curve = axes[0]
    ax_threshold = axes[-1]

    color_cycle = plt.rcParams["axes.prop_cycle"].by_key().get("color", [])
    colors_by_label = {
        label: color_cycle[idx % len(color_cycle)] if color_cycle else None
        for idx, label in enumerate(animal_labels)
    }
    trials_to_threshold = []
    sigmoid_fits = {}
    for label in animal_labels:
        perf_values = np.asarray(perf_by_label[label], dtype=float)
        x_curve = np.arange(len(perf_values))
        n_trials = np.nan
        fit_result = None

        if threshold_method == "sigmoid":
            n_trials, fit_result = _fit_learning_sigmoid_threshold(
                perf_values,
                n_size_window,
                threshold,
                fit_max_bin=sigmoid_fit_max_bin,
            )
            sigmoid_fits[label] = fit_result
            if max_trials_to_threshold is not None and n_trials > max_trials_to_threshold:
                trials_to_threshold.append(np.nan)
            else:
                trials_to_threshold.append(n_trials)
        elif threshold_method == "first_bin":
            reached = np.where(perf_values >= threshold)[0]
            if len(reached) == 0:
                trials_to_threshold.append(np.nan)
            else:
                n_trials = int((reached[0] + 1) * n_size_window)
                if max_trials_to_threshold is not None and n_trials > max_trials_to_threshold:
                    trials_to_threshold.append(np.nan)
                else:
                    trials_to_threshold.append(n_trials)
        else:
            raise ValueError("threshold_method must be 'sigmoid' or 'first_bin'.")

        plot_stop = len(perf_values)
        if crop_after_threshold and np.isfinite(n_trials):
            threshold_bin = int(np.ceil(float(n_trials) / float(n_size_window))) - 1
            plot_stop = threshold_bin + int(extra_bins_after_threshold) + 1
            plot_stop = min(max(plot_stop, 1), len(perf_values))

        ax_curve.plot(
            x_curve[:plot_stop],
            perf_values[:plot_stop],
            color=colors_by_label[label],
            marker="o",
            linestyle="-",
            markersize=4,
            lw=1.4,
            label=label,
        )

        if fit_result is not None and "fit_y" in fit_result:
            fit_x_bins = fit_result["fit_x"] / n_size_window - 1
            fit_mask = fit_x_bins <= (plot_stop - 1)
            if sigmoid_fit_max_bin is not None:
                fit_mask = fit_mask & (fit_x_bins <= int(sigmoid_fit_max_bin))
            ax_curve.plot(
                fit_x_bins[fit_mask],
                fit_result["fit_y"][fit_mask],
                ls=":",
                lw=1.8,
                alpha=0.9,
                color=colors_by_label[label],
            )

    ax_curve.axhline(
        threshold,
        color="#C44E52",
        ls="--",
        lw=1.0,
        alpha=0.8,
    )
    ax_curve.set_xlabel(f"Trial window ({n_size_window} trials/bin)")
    ax_curve.set_ylabel("Performance")
    ax_curve.set_ylim(-0.05, 1.05)
    ax_curve.grid(True, axis="y", color="#E1E1E1", linewidth=0.7)
    ax_curve.spines["top"].set_visible(False)
    ax_curve.spines["right"].set_visible(False)
    ax_curve.legend(frameon=False, ncols=min(4, n_animals))
    ax_curve.set_title(
        f"Learning curves and trials to reach {int(threshold * 100)}%",
        fontsize=12,
        loc="left",
    )

    x = np.arange(len(animal_labels))
    ax_threshold.bar(
        x,
        np.nan_to_num(trials_to_threshold, nan=0.0),
        color=[colors_by_label[label] for label in animal_labels],
        edgecolor="white",
        linewidth=1.0,
    )
    for xpos, value in zip(x, trials_to_threshold):
        label_text = "not reached" if np.isnan(value) else str(int(value))
        ypos = 0.5 if np.isnan(value) else value
        ax_threshold.text(
            xpos,
            ypos,
            label_text,
            ha="center",
            va="bottom",
            fontsize=9,
            color="#333333",
        )

    ax_threshold.set_xticks(x)
    ax_threshold.set_xticklabels(animal_labels, rotation=30, ha="right")
    ax_threshold.set_ylabel("Trials")
    ax_threshold.set_title(
        f"Trials to reach {int(threshold * 100)}% performance",
        fontsize=11,
        loc="left",
    )
    if max_trials_to_threshold is not None:
        ax_threshold.axhline(
            max_trials_to_threshold,
            color="#C44E52",
            ls=":",
            lw=1.0,
            alpha=0.7,
        )
    ax_threshold.spines["top"].set_visible(False)
    ax_threshold.spines["right"].set_visible(False)
    ax_threshold.grid(True, axis="y", color="#E1E1E1", linewidth=0.7)

    fig.tight_layout()
    trials_to_threshold_by_label = {
        label: value for label, value in zip(animal_labels, trials_to_threshold)
    }
    if return_sigmoid_fits:
        return fig, axes, trials_to_threshold_by_label, sigmoid_fits
    return fig, axes, trials_to_threshold_by_label


def plot_batch_go_performance_with_threshold_protocol_columns(
    protocol_batches,
    protocol_labels=None,
    alldays_datekeys=None,
    n_size_window: int = 10,
    threshold: float = 0.8,
    labels=None,
    max_trials_to_threshold: int | None = None,
    threshold_method: str = "sigmoid",
    return_sigmoid_fits: bool = False,
):
    """
    Plot one protocol per column, with learning curves above threshold bars.

    protocol_batches can be a dict mapping protocol names to loaded batch dicts
    or a list/tuple of loaded batch dicts.
    """
    if isinstance(protocol_batches, dict):
        protocol_items = list(protocol_batches.items())
    else:
        protocol_batches = list(protocol_batches)
        if protocol_labels is None:
            protocol_labels = [
                f"protocol_{idx + 1}" for idx in range(len(protocol_batches))
            ]
        protocol_items = list(zip(protocol_labels, protocol_batches))

    n_protocols = len(protocol_items)
    if n_protocols == 0:
        raise ValueError("No protocol data found to plot.")

    if alldays_datekeys is None:
        alldays_by_protocol = [None] * n_protocols
    elif (
        isinstance(alldays_datekeys, (list, tuple))
        and len(alldays_datekeys) == n_protocols
    ):
        alldays_by_protocol = list(alldays_datekeys)
    else:
        alldays_by_protocol = [alldays_datekeys] * n_protocols

    fig, axes = plt.subplots(
        2,
        n_protocols,
        figsize=(max(5.0 * n_protocols, 6.5), 6.5),
        sharey="row",
        squeeze=False,
        gridspec_kw={"height_ratios": [2.4, 1.3]},
    )

    trials_to_threshold_by_protocol = {}
    sigmoid_fits_by_protocol = {}

    for protocol_idx, ((protocol_label, batch_hit_by_sound), protocol_datekeys) in enumerate(
        zip(protocol_items, alldays_by_protocol)
    ):
        tmp_fig, _tmp_ax, all_perf = plot_batch_go_performance_by_window(
            batch_hit_by_sound,
            alldays_datekeys=protocol_datekeys,
            n_size_window=n_size_window,
            labels=labels,
        )
        plt.close(tmp_fig)

        if isinstance(all_perf, dict):
            perf_by_label = all_perf
        else:
            label = labels[0] if isinstance(labels, (list, tuple)) else (labels or "animal_1")
            perf_by_label = {label: all_perf}

        animal_labels = list(perf_by_label.keys())
        n_animals = len(animal_labels)
        if n_animals == 0:
            raise ValueError(f"No animal performance data found for {protocol_label}.")

        ax_curve = axes[0, protocol_idx]
        ax_threshold = axes[1, protocol_idx]

        color_cycle = plt.rcParams["axes.prop_cycle"].by_key().get("color", [])
        colors_by_label = {
            label: color_cycle[idx % len(color_cycle)] if color_cycle else None
            for idx, label in enumerate(animal_labels)
        }

        trials_to_threshold = []
        sigmoid_fits = {}
        for label in animal_labels:
            perf_values = np.asarray(perf_by_label[label], dtype=float)
            x_curve = np.arange(len(perf_values))
            ax_curve.plot(
                x_curve,
                perf_values,
                color=colors_by_label[label],
                marker="o",
                linestyle="-",
                markersize=4,
                lw=1.4,
                label=label,
            )

            if threshold_method == "sigmoid":
                n_trials, fit_result = _fit_learning_sigmoid_threshold(
                    perf_values,
                    n_size_window,
                    threshold,
                )
                sigmoid_fits[label] = fit_result
                if fit_result is not None and "fit_y" in fit_result:
                    ax_curve.plot(
                        fit_result["fit_x"] / n_size_window - 1,
                        fit_result["fit_y"],
                        ls=":",
                        lw=1.8,
                        alpha=0.9,
                        color=colors_by_label[label],
                    )
                if max_trials_to_threshold is not None and n_trials > max_trials_to_threshold:
                    trials_to_threshold.append(np.nan)
                else:
                    trials_to_threshold.append(n_trials)
            elif threshold_method == "first_bin":
                reached = np.where(perf_values >= threshold)[0]
                if len(reached) == 0:
                    trials_to_threshold.append(np.nan)
                else:
                    n_trials = int((reached[0] + 1) * n_size_window)
                    if max_trials_to_threshold is not None and n_trials > max_trials_to_threshold:
                        trials_to_threshold.append(np.nan)
                    else:
                        trials_to_threshold.append(n_trials)
            else:
                raise ValueError("threshold_method must be 'sigmoid' or 'first_bin'.")

        ax_curve.axhline(threshold, color="#C44E52", ls="--", lw=1.0, alpha=0.8)
        ax_curve.set_xlabel(f"Trial window ({n_size_window} trials/bin)")
        if protocol_idx == 0:
            ax_curve.set_ylabel("Performance")
        ax_curve.set_ylim(-0.05, 1.05)
        ax_curve.grid(True, axis="y", color="#E1E1E1", linewidth=0.7)
        ax_curve.spines["top"].set_visible(False)
        ax_curve.spines["right"].set_visible(False)
        ax_curve.set_title(str(protocol_label), fontsize=12, loc="left")
        ax_curve.legend(frameon=False, ncols=min(2, n_animals))

        x = np.arange(len(animal_labels))
        ax_threshold.bar(
            x,
            np.nan_to_num(trials_to_threshold, nan=0.0),
            color=[colors_by_label[label] for label in animal_labels],
            edgecolor="white",
            linewidth=1.0,
        )
        for xpos, value in zip(x, trials_to_threshold):
            label_text = "not reached" if np.isnan(value) else str(int(value))
            ypos = 0.5 if np.isnan(value) else value
            ax_threshold.text(
                xpos,
                ypos,
                label_text,
                ha="center",
                va="bottom",
                fontsize=9,
                color="#333333",
            )

        ax_threshold.set_xticks(x)
        ax_threshold.set_xticklabels(animal_labels, rotation=30, ha="right")
        if protocol_idx == 0:
            ax_threshold.set_ylabel("Trials")
        ax_threshold.set_title(
            f"Trials to {int(threshold * 100)}%",
            fontsize=11,
            loc="left",
        )
        if max_trials_to_threshold is not None:
            ax_threshold.axhline(
                max_trials_to_threshold,
                color="#C44E52",
                ls=":",
                lw=1.0,
                alpha=0.7,
            )
        ax_threshold.spines["top"].set_visible(False)
        ax_threshold.spines["right"].set_visible(False)
        ax_threshold.grid(True, axis="y", color="#E1E1E1", linewidth=0.7)

        trials_to_threshold_by_protocol[protocol_label] = {
            label: value for label, value in zip(animal_labels, trials_to_threshold)
        }
        sigmoid_fits_by_protocol[protocol_label] = sigmoid_fits

    fig.suptitle(
        f"Learning curves and trials to reach {int(threshold * 100)}%",
        x=0.01,
        ha="left",
        fontsize=13,
    )
    fig.tight_layout()

    if return_sigmoid_fits:
        return fig, axes, trials_to_threshold_by_protocol, sigmoid_fits_by_protocol
    return fig, axes, trials_to_threshold_by_protocol


def plot_mean_go_by_sound(
    group_go: dict,
    title: str = "Mean GO by sound across mice",
    save_path: Path | None = None,
):
    sound_x = np.asarray(group_go["sound_in_khz"], dtype=float)
    sound_in_khz_str = [str(np.round(sound, 2)) for sound in sound_x]
    go_matrix = np.asarray(group_go["go_matrix"], dtype=float)
    mean_go = np.asarray(group_go["mean_go_pct"], dtype=float)
    sem_go = np.asarray(group_go["sem_go_pct"], dtype=float)

    fig, axes = plt.subplots(2, 1, figsize=(8.5, 8.2), dpi=140, sharex=True)
    fig.patch.set_facecolor("white")
    ax_raw, ax_mean = axes
    ax_raw.set_facecolor("#FBFBFB")
    ax_mean.set_facecolor("#FBFBFB")

    rng = np.random.default_rng(4)
    mouse_names = group_go.get(
        "mouse_names",
        [f"mouse_{idx + 1}" for idx in range(go_matrix.shape[0])],
    )
    color_cycle = plt.rcParams["axes.prop_cycle"].by_key().get("color", [])
    if len(sound_x) > 1:
        jitter_width = float(np.nanmin(np.diff(np.sort(sound_x)))) * 0.08
    else:
        jitter_width = 0.05

    for mouse_idx, mouse_name in enumerate(mouse_names):
        mouse_values = go_matrix[mouse_idx, :]
        valid = np.isfinite(mouse_values)
        if not np.any(valid):
            continue
        mouse_color = color_cycle[mouse_idx % len(color_cycle)] if color_cycle else "#4C78A8"
        x_jitter = sound_x[valid] + rng.uniform(-jitter_width, jitter_width, np.sum(valid))
        ax_raw.scatter(
            x_jitter,
            mouse_values[valid],
            s=28,
            facecolors="white",
            edgecolors=mouse_color,
            linewidths=1.3,
            alpha=0.9,
            label=str(mouse_name),
        )

    ax_mean.errorbar(
        sound_x,
        mean_go,
        yerr=sem_go,
        color="k",
        linewidth=1,
        marker="o",
        markersize=5,
        capsize=0,
        elinewidth=1,
        ecolor="#555555",
    )

    ax_raw.set_title(title, fontsize=16, fontweight="bold", loc="left", pad=14)
    ax_raw.text(
        0,
        1.02,
        "Individual mice",
        transform=ax_raw.transAxes,
        fontsize=8,
        color="#555555",
        va="bottom",
    )
    ax_raw.legend(frameon=False, fontsize=7, ncols=2)
    ax_mean.set_title("Mean +/- SEM across mice", fontsize=12, fontweight="bold", loc="left")
    ax_mean.set_xlabel("Sound", fontsize=12, labelpad=10)
    ax_raw.set_ylabel("GO trials (%)", fontsize=12, labelpad=10)
    ax_mean.set_ylabel("GO trials (%)", fontsize=12, labelpad=10)
    ax_mean.set_xticks(sound_x)
    ax_mean.set_xticklabels(sound_in_khz_str, rotation=90)

    y_max_candidates = np.r_[go_matrix[np.isfinite(go_matrix)], mean_go + sem_go]
    if y_max_candidates.size:
        y_max = max(100, float(np.nanmax(y_max_candidates)) * 1.12)
    else:
        y_max = 100
    for ax in axes:
        ax.set_ylim(0, y_max)
        ax.grid(True, axis="y", color="#D9D9D9", linewidth=0.8)
        ax.grid(True, axis="x", color="#EFEFEF", linewidth=0.6)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color("#777777")
        ax.spines["bottom"].set_color("#777777")
        ax.tick_params(axis="both", labelsize=10, colors="#333333")

    fig.tight_layout()
    if save_path is not None:
        save_path = Path(save_path)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=300, bbox_inches="tight", facecolor="white")
    return fig, axes

def _sigmoid(x, bottom, top, x_mid, slope):
    return bottom + (top - bottom) / (1.0 + np.exp(-(x - x_mid) / slope))


def fit_sigmoid_to_group_go(
    group_go: dict,
    n_fit_points: int = 300,
    exclude_indices=None,
    exclude_x=None,
) -> dict:
    """
    Fit the mean GO-by-sound curve with an optional point exclusion mask.

    exclude_indices uses zero-based positions in group_go["sound_in_khz"].
    exclude_x uses x-axis values, for example sound frequencies in kHz.
    """
    try:
        from scipy.optimize import curve_fit
    except ImportError as exc:
        raise ImportError(
            "fit_sigmoid_to_group_go requires scipy. Install scipy in the Spyder "
            "environment to fit the curve."
        ) from exc

    x_data = np.asarray(group_go["sound_in_khz"], dtype=float)
    y_data = np.asarray(group_go["mean_go_pct"], dtype=float)
    sem_data = np.asarray(group_go.get("sem_go_pct", np.zeros_like(y_data)), dtype=float)

    valid = ~np.isnan(x_data) & ~np.isnan(y_data)
    excluded = np.zeros(len(x_data), dtype=bool)
    if exclude_indices is not None:
        for idx in np.atleast_1d(exclude_indices):
            idx = int(idx)
            if idx < 0:
                idx += len(x_data)
            if 0 <= idx < len(x_data):
                excluded[idx] = True
    if exclude_x is not None:
        for x_value in np.atleast_1d(exclude_x).astype(float):
            excluded = excluded | np.isclose(x_data, x_value)

    fit_mask = valid & ~excluded
    x_fit_data = x_data[fit_mask]
    y_fit_data = y_data[fit_mask]
    sem_fit_data = sem_data[fit_mask]
    if len(x_fit_data) < 4:
        raise ValueError("At least 4 valid sound points are needed to fit a sigmoid.")

    y_min = float(np.nanmin(y_fit_data))
    y_max = float(np.nanmax(y_fit_data))
    x_mid_guess = float(
        x_fit_data[np.argmin(np.abs(y_fit_data - ((y_min + y_max) / 2.0)))]
    )
    p0 = [max(0.0, y_min), min(100.0, y_max), x_mid_guess, 1.0]
    bounds = (
        [0.0, 0.0, float(np.min(x_fit_data)), 0.01],
        [100.0, 100.0, float(np.max(x_fit_data)), 100.0],
    )

    sigma = sem_fit_data.copy()
    sigma[~np.isfinite(sigma) | (sigma <= 0)] = 1.0
    popt, pcov = curve_fit(
        _sigmoid,
        x_fit_data,
        y_fit_data,
        p0=p0,
        bounds=bounds,
        sigma=sigma,
        absolute_sigma=False,
        maxfev=20000,
    )

    fit_x = np.linspace(float(np.min(x_fit_data)), float(np.max(x_fit_data)), n_fit_points)
    fit_y = _sigmoid(fit_x, *popt)
    pred_y = _sigmoid(x_fit_data, *popt)
    ss_res = float(np.sum((y_fit_data - pred_y) ** 2))
    ss_tot = float(np.sum((y_fit_data - np.mean(y_fit_data)) ** 2))
    r_squared = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else np.nan

    fit_result = {
        "params": {
            "bottom": float(popt[0]),
            "top": float(popt[1]),
            "x_mid": float(popt[2]),
            "slope": float(popt[3]),
        },
        "covariance": pcov,
        "fit_x": fit_x,
        "fit_y": fit_y,
        "x_fit_data": x_fit_data,
        "y_fit_data": y_fit_data,
        "fit_mask": fit_mask,
        "excluded_indices": np.where(excluded & valid)[0].astype(int).tolist(),
        "excluded_x": x_data[excluded & valid].astype(float).tolist(),
        "r_squared": r_squared,
    }
    group_go["sigmoid_fit"] = fit_result
    return fit_result


def plot_mean_go_by_sound_with_sigmoid(
    group_go: dict,
    title: str = "Mean GO by sound across mice",
    save_path: Path | None = None,
    exclude_indices=None,
    exclude_x=None,
):
    use_custom_exclusion = exclude_indices is not None or exclude_x is not None
    fit_result = None if use_custom_exclusion else group_go.get("sigmoid_fit")
    if fit_result is None:
        fit_result = fit_sigmoid_to_group_go(
            group_go,
            exclude_indices=exclude_indices,
            exclude_x=exclude_x,
        )

    fig, axes = plot_mean_go_by_sound(group_go, title=title, save_path=None)
    ax_mean = axes[1]
    if fit_result.get("excluded_indices"):
        sound_x = np.asarray(group_go["sound_in_khz"], dtype=float)
        mean_go = np.asarray(group_go["mean_go_pct"], dtype=float)
        excluded_indices = np.asarray(fit_result["excluded_indices"], dtype=int)
        ax_mean.scatter(
            sound_x[excluded_indices],
            mean_go[excluded_indices],
            s=80,
            facecolors="none",
            edgecolors="#C44E52",
            linewidths=1.8,
            label="Excluded from fit",
            zorder=5,
        )
    ax_mean.plot(
        fit_result["fit_x"],
        fit_result["fit_y"],
        color="#C44E52",
        linewidth=2.6,
        label=(
            f"Sigmoid fit, midpoint={fit_result['params']['x_mid']:.2f}, "
            f"R2={fit_result['r_squared']:.2f}"
        ),
    )
    #ax.set_xscale('log')
    ax_mean.legend(frameon=False, loc="best", fontsize=9)
    fig.tight_layout()

    if save_path is not None:
        save_path = Path(save_path)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=300, bbox_inches="tight", facecolor="white")
    return fig, axes, fit_result

# -----------------------------------------------------------------------------
# Combined plot runners
# -----------------------------------------------------------------------------

def plot_session_visualizations(
    data_session_dict,
    performance,
    ir_events,
    trial_ir_analysis,
    hit_by_sound=None,
    show=True,
    block=False,
):
    figures = []
    figures.append(
        plot_performance(
            performance,
            data_session_dict,
            trial_ir_analysis=trial_ir_analysis,
            show=show,
            block=block,
        )
    )
    figures.append(plot_ir_events(data_session_dict, ir_events, show=show, block=block))
    fig_occ = plot_ir_occupancy_by_sound(
        data_session_dict,
        trial_ir_analysis,
        show=show,
        block=block,
    )
    if fig_occ is not None:
        figures.append(fig_occ)
    fig_hit = plot_hit_by_sound(hit_by_sound, show=show, block=block)
    if fig_hit is not None:
        figures.append(fig_hit)
    return figures
