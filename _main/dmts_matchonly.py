"""Grouped DMTS lick traces with full-resolution onset detection."""
from pathlib import Path
import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from matplotlib.collections import LineCollection
from dmts_analysis import analyze_dmts, signal_times, is_dmts_lick


def plot_matchonly(session, threshold_v=1.0, smooth_ms=0.0, bin_width_s=0.1,
                   pre_s=0.5, post_s=0.5, trace_height=0.7, max_plot_points=800,
                   file_path="DMTS session"):
    """Return the grouped figure, events, histogram and original trial mapping."""
    file_path = Path(file_path)
    if not np.all(np.isfinite([threshold_v, smooth_ms, bin_width_s, pre_s,
                              post_s, trace_height, max_plot_points])):
        raise ValueError("All settings must be finite numbers.")
    if trace_height <= 0 or int(max_plot_points) != max_plot_points:
        raise ValueError("Use positive trace height and an integer drawing point limit.")
    max_plot_points = int(max_plot_points)
    if (
        bin_width_s <= 0 or smooth_ms < 0
        or pre_s < 0 or post_s < 0 or max_plot_points < 4
    ):
        raise ValueError("Check the plotting and detection settings.")

    print("Loading file...")

    if session is None or not is_dmts_lick(session):
        raise ValueError("Select a DMTS lick-task NWB file.")

    analysis = analyze_dmts(session)

    original_trials = [
        {**trial, "original_trial": i}
        for i, trial in enumerate(analysis["trials"], start=1)
    ]
    if not original_trials:
        raise ValueError("No trials found.")

    # Group trials while preserving chronological order within each group.
    group_order = ("blank", "match", "nonmatch")
    group_labels = {
        "blank": "Blank",
        "match": "Match",
        "nonmatch": "Non-match",
    }
    group_colors = {
        "blank": "#888888",
        "match": "#339966",
        "nonmatch": "#AA66BB",
    }

    trials = []
    trial_groups = []

    for kind in group_order:
        selected = [t for t in original_trials if t["kind"] == kind]
        if selected:
            first = len(trials) + 1
            trials.extend(selected)
            last = len(trials)
            trial_groups.append((kind, first, last))
            print(f"{group_labels[kind]}: rows {first}–{last}")

    if len(trials) != len(original_trials):
        raise ValueError("Unexpected trial type.")

    # Common time window relative to sample / blank onset.
    t_min = -pre_s
    requested_end = max(
        trial["response_end"] - trial["start"] for trial in trials
    ) + post_s

    n_bins = int(np.ceil((requested_end - t_min) / bin_width_s))
    bins = t_min + np.arange(n_bins + 1) * bin_width_s
    t_max = bins[-1]


    def trailing_average(values, n):
        """Causal moving average using available samples at recording start."""
        cumulative = np.r_[0.0, np.cumsum(values, dtype=float)]
        result = cumulative[1:].copy()

        if n < len(values):
            result[n:] -= cumulative[1:len(values) - n + 1]

        result /= np.minimum(np.arange(1, len(values) + 1), n)
        return result


    def display_indices(values, limit):
        """Reduce drawing points while preserving block minima and maxima."""
        size = len(values)
        if size <= limit:
            return np.arange(size)

        block_size = int(np.ceil(size / max(1, (limit - 2) // 2)))
        n_blocks = size // block_size

        blocks = values[:n_blocks * block_size].reshape(n_blocks, block_size)
        offsets = np.arange(n_blocks) * block_size

        indices = [
            offsets + blocks.argmin(axis=1),
            offsets + blocks.argmax(axis=1),
        ]

        tail_start = n_blocks * block_size
        if tail_start < size:
            tail = values[tail_start:]
            indices.append(np.array([
                tail_start + tail.argmin(),
                tail_start + tail.argmax(),
            ]))

        return np.unique(np.concatenate(indices))


    print("Detecting licks at full resolution...")
    channels = {}

    for side in ("Left", "Right"):
        name = side + "Lick"
        if name not in session["signals"]:
            raise ValueError(f"{name} was not recorded.")

        signal = session["signals"][name]
        times = np.asarray(signal_times(signal), dtype=float)
        raw = np.asarray(signal["data"], dtype=float).reshape(-1)

        if len(times) != len(raw) or len(raw) < 2:
            raise ValueError(f"{side}: invalid signal length.")

        dt = np.diff(times)
        if (
            not np.all(np.isfinite(times))
            or np.any(dt <= 0)
            or not np.all(np.isfinite(raw))
        ):
            raise ValueError(f"{side}: invalid timestamps or signal values.")

        sample_interval = np.median(dt)
        rate = 1.0 / sample_interval

        if smooth_ms > 0 and not np.allclose(
            dt, sample_interval, rtol=0.01, atol=1e-8
        ):
            raise ValueError(
                f"{side}: smoothing requires approximately uniform sampling."
            )

        n = max(1, int(round(smooth_ms * rate / 1000)))
        filtered = trailing_average(raw, n) if n > 1 else raw

        # Same rising-crossing rule as pyBEHAVIOR_v7.
        high = filtered >= threshold_v
        indices = np.flatnonzero(high & ~np.r_[False, high[:-1]])

        channels[side] = {
            "time": times,
            "raw": raw,
            "event_times": times[indices],
            "event_values": filtered[indices],
        }

    # Estimate a common visual voltage scale from a subset of samples.
    voltage_scale = max(
        1.0,
        *[
            np.percentile(
                np.abs(ch["raw"][::max(1, len(ch["raw"]) // 100000)]),
                99.5
            )
            for ch in channels.values()
        ]
    )
    gain = trace_height / voltage_scale

    print("Building grouped plots...")
    fig = Figure(figsize=(15, 10))
    axes = fig.subplots(
        2, 2,
        sharex=True,
        sharey="row",
        gridspec_kw={"height_ratios": [3, 1], "hspace": 0.08}
    )

    event_tables = []
    histogram_tables = []

    for column, (side, trace_color) in enumerate(
        zip(("Left", "Right"), ("tab:blue", "tab:orange"))
    ):
        top_ax = axes[0, column]
        hist_ax = axes[1, column]
        channel = channels[side]

        times = channel["time"]
        event_times = channel["event_times"]

        segments = []
        marker_x = []
        marker_y = []
        counts_by_kind = {
            kind: np.zeros(n_bins, dtype=np.int64)
            for kind in group_order
        }

        for plot_row, trial in enumerate(trials, start=1):
            start = trial["start"]

            i0 = np.searchsorted(times, start + t_min, side="left")
            i1 = np.searchsorted(times, start + t_max, side="left")

            # Reduce only the raw data sent to Matplotlib.
            raw_window = channel["raw"][i0:i1]
            if raw_window.size:
                selected = i0 + display_indices(
                    raw_window, max_plot_points
                )
                segments.append(np.column_stack((
                    times[selected] - start,
                    plot_row + gain * channel["raw"][selected]
                )))

            # Select full-resolution events in this aligned window.
            e0 = np.searchsorted(event_times, start + t_min, side="left")
            e1 = np.searchsorted(event_times, start + t_max, side="left")

            absolute_events = event_times[e0:e1]
            relative_events = absolute_events - start

            marker_x.append(relative_events)
            marker_y.append(
                plot_row + gain * channel["event_values"][e0:e1]
            )

            counts_by_kind[trial["kind"]] += np.histogram(
                relative_events, bins=bins
            )[0]

            if len(relative_events):
                event_tables.append(pd.DataFrame({
                    "trial": trial["original_trial"],
                    "plot_row": plot_row,
                    "side": side,
                    "trial_kind": trial["kind"],
                    "sample_id": trial["sample_id"],
                    "test_id": trial["test_id"],
                    "time_session_s": absolute_events,
                    "time_from_sample_s": relative_events,
                    "in_response_window": (
                        (absolute_events >= trial["response_start"])
                        & (absolute_events < trial["response_end"])
                    ),
                }))

        # One collection for all raw trial traces.
        top_ax.add_collection(LineCollection(
            segments,
            colors=trace_color,
            linewidths=0.55,
            alpha=0.75
        ))

        # One artist for all detected lick markers.
        top_ax.plot(
            np.concatenate(marker_x),
            np.concatenate(marker_y),
            linestyle="none",
            marker="|",
            color="black",
            markersize=4,
            markeredgewidth=0.8,
            zorder=4
        )

        total_events = 0

        for kind, first, last in trial_groups:
            n_group = last - first + 1

            top_ax.axhspan(
                first - 0.5, last + 0.5,
                color=group_colors[kind], alpha=0.09, zorder=-2
            )

            if first > 1:
                top_ax.axhline(
                    first - 0.5, color="0.4",
                    linestyle="--", linewidth=0.8
                )

            top_ax.text(
                0.99, (first + last) / 2,
                f"{group_labels[kind]} (n={n_group})",
                transform=top_ax.get_yaxis_transform(),
                ha="right", va="center", fontsize=9,
                bbox=dict(
                    facecolor="white", alpha=0.85, edgecolor="none"
                ),
                zorder=5
            )

            counts = counts_by_kind[kind]
            total_events += int(counts.sum())

            hist_ax.stairs(
                counts, bins,
                color=group_colors[kind],
                linewidth=1.4,
                label=f"{group_labels[kind]} (n={n_group})"
            )

            histogram_tables.append(pd.DataFrame({
                "side": side,
                "trial_kind": kind,
                "n_trials": n_group,
                "bin_start_s": bins[:-1],
                "bin_end_s": bins[1:],
                "bin_center_s": (bins[:-1] + bins[1:]) / 2,
                "lick_count": counts,
            }))

        top_ax.set_title(f"{side} licks — {total_events} aligned events")
        hist_ax.set_xlabel("Time from sample / blank onset (s)")
        hist_ax.legend(fontsize=8, loc="upper right")
        hist_ax.grid(axis="y", alpha=0.2)

        for ax in (top_ax, hist_ax):
            ax.axvline(0, color="black", linestyle="--", linewidth=0.8)
            ax.set_xlim(t_min, t_max)

    tick_step = max(1, int(np.ceil(len(trials) / 25)))
    axes[0, 0].set_yticks(np.arange(1, len(trials) + 1, tick_step))
    axes[0, 0].set_ylim(0.5, len(trials) + 1)
    axes[0, 0].set_ylabel("Grouped trial row + scaled lick voltage")
    axes[1, 0].set_ylabel(f"Lick count\nper {bin_width_s:g} s bin")
    axes[1, 0].set_ylim(bottom=0)

    fig.suptitle(
        f"{file_path.name}\n"
        f"Threshold: {threshold_v:g} V | Smoothing: {smooth_ms:g} ms | "
        "Black ticks: detected lick onsets"
    )
    fig.subplots_adjust(
        top=0.91, bottom=0.08, left=0.08, right=0.98, wspace=0.08
    )

    # Tables remain available in Spyder.
    event_columns = [
        "trial", "plot_row", "side", "trial_kind",
        "sample_id", "test_id", "time_session_s",
        "time_from_sample_s", "in_response_window"
    ]

    lick_events = (
        pd.concat(event_tables, ignore_index=True)
        if event_tables
        else pd.DataFrame(columns=event_columns)
    )
    lick_histogram = pd.concat(histogram_tables, ignore_index=True)

    trial_order = pd.DataFrame([
        {
            "plot_row": row,
            "trial": trial["original_trial"],
            "trial_kind": trial["kind"],
            "sample_id": trial["sample_id"],
            "test_id": trial["test_id"],
        }
        for row, trial in enumerate(trials, start=1)
    ])

    return fig, lick_events, lick_histogram, trial_order
