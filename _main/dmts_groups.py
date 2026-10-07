"""Overlay DMTS batch exports and average curves without extending recordings."""
import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from dmts_batch import session_sort_key


def export_curves(payload, engaged_only=False):
    if not isinstance(payload, dict) or payload.get("format") not in ("dmts_batch_v1", "dmts_batch_v2"):
        raise ValueError("Not a DMTS batch export")
    sessions = payload["sessions"]
    # Older exports have no timestamps; preserve their stored order.
    if any(session.get("session_start_time") for session in sessions):
        sessions = sorted(sessions, key=session_sort_key)
    trials = [trial for session in sessions for trial in session["trials"]]
    if not trials:
        raise ValueError("Export contains no trials")
    if engaged_only and not all("engagement" in trial for trial in trials):
        raise ValueError("Export has no engagement flags; rerun batch analysis to use engaged-only curves")
    curves = {}
    for kind in ("overall", "match", "nonmatch"):
        indices, values = [], []
        for i, trial in enumerate(trials):
            if trial.get("correct") is None or (kind != "overall" and trial["kind"] != kind):
                continue
            if engaged_only and trial.get("engagement") != "engaged":
                continue
            value = float(trial["correct"])
            if value not in (0., 1.):
                raise ValueError("Invalid trial correctness value")
            indices.append(i)
            values.append(value)
        curve = np.full(len(trials), np.nan)
        if values:
            rolling = pd.Series(values, index=indices).rolling(25, min_periods=1).mean() * 100
            curve = rolling.reindex(range(len(trials))).ffill().to_numpy()
        curves[kind] = curve
    return curves


def mean_curves(curves):
    matrix = np.full((len(curves), max(map(len, curves))), np.nan)
    for i, curve in enumerate(curves):
        matrix[i, :len(curve)] = curve
    counts = np.isfinite(matrix).sum(axis=0)
    return np.divide(np.nansum(matrix, axis=0), counts,
                     out=np.full(matrix.shape[1], np.nan), where=counts > 0), counts


def plot_groups(exports, assignments, engaged_only=False, plot_layout=None):
    if not exports:
        raise ValueError("Load DMTS batch PKL files first")
    prepared = {key: export_curves(value, engaged_only) for key, value in exports.items()}
    layout = plot_layout or {}
    def positive(key, default):
        try:
            value = float(layout.get(key, default))
            return value if np.isfinite(value) and value > 0 else default
        except (TypeError, ValueError):
            return default
    dpi = positive("dpi", 100)
    fig = Figure(figsize=(positive("subplot_width_px", 500)/dpi,
                          3*positive("subplot_height_px", 300)/dpi), dpi=dpi)
    axes = fig.subplots(3, 1, sharex=True)
    groups = sorted({assignments.get(key, "All files") for key in exports})
    colors = ["#2878B5", "#339966", "#AA66BB", "#D55E00", "#CC4444"]
    averages = {}
    for ax, metric in zip(axes, ("overall", "match", "nonmatch")):
        for g, group in enumerate(groups):
            keys = [key for key in exports if assignments.get(key, "All files") == group]
            curves = [prepared[key][metric] for key in keys]
            for curve in curves:
                ax.plot(np.arange(1, len(curve)+1), curve, color=colors[g % len(colors)], alpha=.25, lw=.8)
            mean, counts = mean_curves(curves)
            averages[(group, metric)] = dict(mean=mean, contributing_files=counts)
            if np.isfinite(mean).any():
                ax.plot(np.arange(1, len(mean)+1), mean, color=colors[g % len(colors)], lw=2.3,
                        label=f"{group} mean ({len(keys)} files)")
        ax.set(title=metric.capitalize(), ylabel="Performance (%)", ylim=(-2, 102))
        ax.grid(alpha=.2)
        if ax.get_legend_handles_labels()[0]:
            ax.legend(fontsize=8)
    axes[-1].set_xlabel("Cumulative session trial number")
    fig.suptitle("DMTS groups — " + ("engaged-only" if engaged_only else "all eligible trials") +
                 "\nThin: individual PKLs; bold: equal-file mean; rolling 25 eligible trials", fontsize=9)
    fig.tight_layout(rect=(0, 0, 1, .94))
    return fig, averages
