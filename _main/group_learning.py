"""Adapt Go/noGo GUI exports to learning-threshold plots."""
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
from session_order import session_sort_key
from behavior_plots import plot_batch_go_performance_with_threshold_subplot


def grouped_trial_batches(exports, assignments):
    """Combine each animal's sessions, deduplicating repeated exported sessions."""
    groups, identities = {}, {}
    for key, payload in exports.items():
        group = assignments.get(key)
        if not group:
            continue
        animal = str(payload.get("animal_name", "")).strip()
        if not animal:
            raise ValueError(f"Missing animal name: {Path(key).name}")
        identity = animal.casefold()
        if identity in identities and identities[identity][0] != group:
            raise ValueError(f"Animal {animal} is assigned to more than one group.")
        identities.setdefault(identity, (group, animal))
        display = identities[identity][1]
        sessions = groups.setdefault(group, {}).setdefault(display, {})
        trial_data = payload.get("trial_performance_by_file", {})
        for session_key, performance in payload.get("performance_by_file", {}).items():
            if not isinstance(performance, dict) or "error" in performance:
                continue
            data = trial_data.get(session_key, {})
            correct = np.asarray(data.get("correct", []), dtype=float)
            if correct.ndim != 1:
                raise ValueError(f"Invalid per-trial correctness: {session_key}")
            if not len(correct):
                continue
            if np.any(np.isfinite(correct) & ~np.isin(correct, [0., 1.])) or np.any(np.isinf(correct)):
                raise ValueError(f"Expected correctness values 0, 1 or NaN: {session_key}")
            normalized = str(Path(session_key)).casefold()
            if normalized in sessions:
                previous = sessions[normalized][1]
                if not np.array_equal(previous, correct, equal_nan=True):
                    raise ValueError(f"Conflicting duplicate session for {animal}: {session_key}")
                continue
            sessions[normalized] = (performance, correct)
    batches = {}
    for group, animals in groups.items():
        batches[group] = {}
        for animal, sessions in animals.items():
            ordered = sorted(sessions.items(), key=lambda item: session_sort_key((item[0], item[1][0])))
            if ordered:
                batches[group][animal] = {
                    index: {"alldataGO": value[1]}
                    for index, (_, value) in enumerate(ordered, 1)}
    return batches


def plot_group_learning_thresholds(exports, assignments):
    """User-requested 25-trial, 80%, cropped sigmoid plots and group summary."""
    batches = grouped_trial_batches(exports, assignments)
    if not any(batches.values()):
        raise ValueError("Assign PKLs containing per-trial correctness to groups first.")
    results, stats, figures = {}, {}, []
    rng = np.random.default_rng(42)
    colors = ["#4477AA", "#CC6677"]
    try:
        for group, batch in batches.items():
            if batch:
                fig, axes, estimates, fits = plot_batch_go_performance_with_threshold_subplot(
                    batch, n_size_window=25, threshold=0.8, threshold_method="sigmoid",
                    return_sigmoid_fits=True, crop_after_threshold=True, extra_bins_after_threshold=0)
                fig.suptitle(str(group))
                fig.tight_layout(rect=(0, 0, 1, .95))
                figures.append(fig)
            else:
                estimates, fits = {}, {}
            results[group] = dict(data=batch, trials_to_threshold=estimates, sigmoid_fits=fits)
            valid = {animal: float(value) for animal, value in estimates.items()
                     if value is not None and np.isfinite(value)}
            values = np.array(list(valid.values()), dtype=float)
            n = len(values)
            stats[group] = dict(n=n, mean=float(values.mean()) if n else np.nan,
                                sem=float(values.std(ddof=1)/np.sqrt(n)) if n>1 else np.nan,
                                individual_trials=valid)

        fig, ax = plt.subplots(figsize=(6, 4.5), layout="constrained")
        figures.append(fig)
        for x, (group, stat) in enumerate(stats.items()):
            n = stat["n"]
            if not n:
                ax.text(x, .05, "No valid estimate", ha="center", transform=ax.get_xaxis_transform(), fontsize=9)
                continue
            color = colors[x % len(colors)]
            ax.bar(x-.14, stat["mean"], width=.34, yerr=stat["sem"] if n>1 else None,
                   capsize=5, color=color, alpha=.65)
            values = np.array(list(stat["individual_trials"].values()))
            ax.scatter(x+.19+rng.uniform(-.06,.06,size=n), values, s=25,
                       color=color, edgecolor="white", linewidth=.6, zorder=3)
        ax.set_xticks(range(len(stats)), [f"{group}\n(n={stat['n']})" for group,stat in stats.items()])
        ax.set_ylabel("Estimated trials to reach 80%")
        ax.set_title("Go/NoGo learning by group")
        ax.set_axisbelow(True)
        ax.grid(axis="y", alpha=.2)
        return figures, results, stats
    except Exception:
        for figure in figures:
            plt.close(figure)
        raise
