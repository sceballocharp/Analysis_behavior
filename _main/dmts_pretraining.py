"""Plot DMTS pretraining lick threshold crossings and reward signals."""

import h5py
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.figure import Figure


def trailing_average(values, n):
    """Causal moving average; use available samples at recording start."""
    cs = np.concatenate(([0.0], np.cumsum(values, dtype=float)))
    ends = np.arange(1, len(values) + 1)
    starts = np.maximum(0, ends - n)
    return (cs[ends] - cs[starts]) / (ends - starts)


def _read_signal(acquisition, name):
    group = acquisition[name]
    dataset = group["data"]
    raw = np.asarray(dataset[:], dtype=float).squeeze()
    if raw.ndim != 1 or raw.size < 2:
        raise ValueError(f"{name}: expected a one-dimensional signal with at least two samples.")
    raw = raw * float(dataset.attrs.get("conversion", 1.0)) + float(dataset.attrs.get("offset", 0.0))
    if not np.all(np.isfinite(raw)):
        raise ValueError(f"{name}: signal contains NaN or infinite values.")
    if "timestamps" in group:
        time = np.asarray(group["timestamps"][:], dtype=float)
        if time.ndim != 1 or len(time) != len(raw) or not np.all(np.isfinite(time)):
            raise ValueError(f"{name}: invalid timestamps.")
        dt = np.diff(time)
        if np.any(dt <= 0):
            raise ValueError(f"{name}: timestamps must be strictly increasing.")
        rate = 1.0 / np.median(dt)
    else:
        start = float(group["starting_time"][()])
        rate = float(group["starting_time"].attrs["rate"])
        if not np.isfinite(start) or not np.isfinite(rate) or rate <= 0:
            raise ValueError(f"{name}: invalid starting time or sampling rate.")
        time = start + np.arange(len(raw)) / rate
    return raw, time, rate


def plot_pretraining(file_path, t_start=295, t_end=300, threshold_v=1.0, smooth_ms=0):
    """Return a figure and lick onset arrays, without showing a window."""
    if not np.all(np.isfinite([t_start, t_end, threshold_v, smooth_ms])):
        raise ValueError("Time bounds, threshold, and smoothing must be finite numbers.")
    if t_end <= t_start:
        raise ValueError("t_end must be greater than t_start.")
    if smooth_ms < 0:
        raise ValueError("smooth_ms must be >= 0.")

    # Read reward using its own timing metadata, independently of the lick channels.
    with h5py.File(file_path, "r") as handle:
        acquisition = handle["acquisition"]
        reward, reward_time, _ = _read_signal(acquisition, "Reward")
        signals = {name: _read_signal(acquisition, name) for name in ("LeftLick", "RightLick")}

    prepared = {}
    lick_times = {}
    for name, (raw, time, rate) in signals.items():
        n = max(1, int(round(smooth_ms * rate / 1000.0)))
        smoothed = trailing_average(raw, n)
        high = smoothed >= threshold_v
        # Detect before cropping to preserve state at the window boundary.
        crossings = high & ~np.r_[False, high[:-1]]
        in_window = (time >= t_start) & (time <= t_end)
        if not np.any(in_window):
            raise ValueError(f"{name}: no samples between {t_start:g} and {t_end:g} s "
                             f"(recording: {time[0]:g} to {time[-1]:g} s).")
        events = crossings & in_window
        lick_times[name] = time[events]
        prepared[name] = (raw, time, smoothed, in_window, events)

    # Create an unmanaged figure for embedding: no second window or toolbar
    # should share this figure's mouse callbacks with the GUI canvas.
    fig = Figure(figsize=(13, 6))
    axes = fig.subplots(2, 1, sharex=True)
    try:
        for ax, name, color in zip(axes, ("LeftLick", "RightLick"), ("red", "blue")):
            raw, time, smoothed, in_window, events = prepared[name]
            ax.plot(time[in_window], raw[in_window], color=color, lw=0.7, alpha=0.25, label="Raw")
            ax.plot(time[in_window], smoothed[in_window], color=color, lw=1.2,
                    label=f"Smoothed ({smooth_ms:g} ms)")
            ax.axhline(threshold_v, color="red", ls="--", lw=1, label=f"Threshold: {threshold_v:g} V")
            ax.scatter(time[events], np.repeat(2.5, events.sum()), color="black", marker="o", s=5,
                       zorder=5, label="Lick onset")
            mask = (reward_time >= t_start) & (reward_time <= t_end)
            ax.step(reward_time[mask], reward[mask], where="post", color="tab:green", linewidth=1,
                    label="Reward")
            ax.set_ylabel(f"{name} (V)")
            ax.set_title(f"{name}: {events.sum()} licks")
            ax.grid(alpha=0.2)
            ax.legend(loc="upper right", fontsize=8)
        axes[-1].set_xlabel("Time (s)")
        axes[-1].set_xlim(t_start, t_end)
        fig.tight_layout()
    except Exception:
        plt.close(fig)
        raise
    return fig, lick_times
