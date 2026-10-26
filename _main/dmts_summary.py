"""Chronological session summaries using recorded outcomes only."""
import numpy as np
import pandas as pd
from matplotlib.figure import Figure


def plot_modality_performance(session, title="DMTS session"):
    """Compare saved-outcome accuracy by recorded trial modality."""
    table = session['ResultsTable']
    required = {'StimulusSource', 'SampleSoundId', 'TestSoundId', 'SavedOutcome'}
    if not required.issubset(table.columns):
        raise ValueError('Reload the NWB file to read per-trial light/sound identities.')
    aliases = {'hit': 'HIT', 'miss': 'MISS', 'correct': 'CR', 'correctrejection': 'CR',
               'cr': 'CR', 'falsealarm': 'FA', 'fa': 'FA'}
    records = []
    for _, row in table.iterrows():
        if row.SampleSoundId == row.TestSoundId == 0:
            continue
        source = str(row.StimulusSource).strip().lower()
        if source not in ('led', 'sound'):
            continue
        raw = row.SavedOutcome
        raw = raw.decode('utf-8') if isinstance(raw, bytes) else str(raw)
        outcome = aliases.get(raw.strip().lower().replace(' ', '').replace('_', ''))
        records.append((source, row.SampleSoundId == row.TestSoundId, outcome))
    if not records:
        raise ValueError('No light or sound trials with known modality were found.')
    fig = Figure(figsize=(10, 6))
    ax = fig.subplots()
    stats = {}
    for i, (source, label, color) in enumerate((('led', 'Light', '#59A14F'), ('sound', 'Sound', '#4C78A8'))):
        values = [r for r in records if r[0] == source]
        stats[label] = {}
        for j, metric in enumerate(('Overall accuracy', 'Match hit rate', 'Non-match CR rate')):
            eligible = [r for r in values if r[2] is not None and (j == 0 or r[1] == (j == 1))]
            correct = sum(r[2] == ('HIT' if r[1] else 'CR') for r in eligible)
            count = len(eligible)
            rate = 100 * correct / count if count else np.nan
            stats[label][metric] = dict(correct=correct, n=count, percent=rate)
            x = j + (i - .5) * .34
            ax.bar(x, rate if count else 0, width=.32, color=color, label=label if j == 0 else None)
            ax.text(x, (rate if count else 0) + 2, f'{rate:.1f}%\n{correct}/{count}' if count else 'N/A\nn=0',
                    ha='center', va='bottom', fontsize=9)
    ax.set(xticks=range(3), xticklabels=['Overall accuracy', 'Match hit rate', 'Non-match CR rate'],
           ylabel='Performance (%)', ylim=(0, 117), title='Light vs Sound')
    ax.set_yticks(range(0, 101, 20))
    ax.legend()
    ax.grid(axis='y', alpha=.2)
    ax.set_axisbelow(True)
    fig.suptitle(title, fontsize=11)
    excluded = sum(r[2] is None for r in records)
    fig.text(.5, .025, f'Saved outcomes; blanks and {excluded} unknown outcome(s) excluded. Labels: correct / eligible trials.\n'
             'Overall: HIT on match trials and CR on non-match trials.', ha='center', fontsize=9)
    fig.tight_layout(rect=(0, .09, 1, .94))
    fig.modality_stats = stats
    return fig


def performance_by_stim_data(session):
    """Shared saved-outcome data for the StimID figure and spatial heatmap."""
    table = session["ResultsTable"]
    if not {"SavedOutcome", "SampleSoundId", "TestSoundId"}.issubset(table.columns) or table.empty:
        raise ValueError("This plot requires saved outcomes and sample/test IDs for DMTS trials.")
    aliases = {"hit": "HIT", "miss": "MISS", "falsealarm": "FA", "fa": "FA",
               "correct": "CR", "correctrejection": "CR", "cr": "CR"}
    pairs = {}
    for _, row in table.iterrows():
        sample, test = int(row.SampleSoundId), int(row.TestSoundId)
        if sample == test == 0:
            continue
        values = pairs.setdefault((sample, test), [])
        value = row.SavedOutcome
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        outcome = aliases.get(str(value).strip().lower().replace(" ", "").replace("_", ""))
        if outcome is not None:
            values.append(int(outcome == ("HIT" if sample == test else "CR")))
    if not pairs:
        raise ValueError("No non-blank DMTS sounds found in this session.")
    return pairs


def plot_performance_by_sound(session, title="DMTS session"):
    """Separate match hit rates from non-match sound-pair rejection rates."""
    from matplotlib import colormaps
    pairs = performance_by_stim_data(session)
    sounds = sorted({sid for pair in pairs for sid in pair})
    size = len(sounds)
    fig = Figure(figsize=(max(12, 6 + size * .55), max(6, 2.5 + size * .55)))
    match_ax, pair_ax = fig.subplots(1, 2, gridspec_kw={"width_ratios": [1, 1.4]})
    match_values = [pairs.get((sid, sid), []) for sid in sounds]
    rates = [100 * np.mean(values) if values else np.nan for values in match_values]
    x = np.arange(size)
    match_ax.plot(x, rates, color="#2F6F9F", marker="o", markerfacecolor="white", linewidth=2)
    for pos, rate, values in zip(x, rates, match_values):
        if values:
            match_ax.annotate(f"n={len(values)}", (pos, rate), xytext=(0, -15 if rate > 90 else 10),
                              textcoords="offset points", ha="center", fontsize=9)
        else:
            match_ax.text(pos, 3, "N/A\nn=0", ha="center", fontsize=9)
    match_ax.set_xticks(x, sounds, rotation=90 if size > 12 else 0)
    match_ax.set(xlabel="Sound ID (sample = test)", ylabel="Hit rate (%)", ylim=(0, 100),
                 title="Match trials", xlim=(-.5, size - .5))
    match_ax.grid(axis="y", alpha=.25)
    matrix = np.full((size, size), np.nan)
    for row, sample in enumerate(sounds):
        for col, test in enumerate(sounds):
            values = pairs.get((sample, test), [])
            if sample != test and values:
                matrix[row, col] = 100 * np.mean(values)
    cmap = colormaps["viridis"].with_extremes(bad="#EEEEEE")
    image = pair_ax.imshow(np.ma.masked_invalid(matrix), vmin=0, vmax=100, cmap=cmap)
    pair_ax.set_xticks(x, sounds, rotation=90 if size > 12 else 0)
    pair_ax.set_yticks(x, sounds)
    pair_ax.set(xlabel="Test sound ID", ylabel="Sample sound ID", title="Non-match trials")
    font_size = max(5, min(10, 100 / size))
    for row, sample in enumerate(sounds):
        for col, test in enumerate(sounds):
            if sample == test:
                continue
            values = pairs.get((sample, test))
            rate = matrix[row, col]
            if np.isfinite(rate):
                pair_ax.text(col, row, f"{rate:.0f}%\nn={len(values)}", ha="center", va="center",
                             fontsize=font_size, color="white" if rate < 55 else "black")
            elif values is not None:
                pair_ax.text(col, row, "N/A\nn=0", ha="center", va="center", fontsize=font_size)
    fig.colorbar(image, ax=pair_ax, shrink=.8, label="Correct rejection (%)")
    fig.suptitle(f"DMTS Performance by StimID - {title}", fontsize=12)
    fig.text(.5, .02, "Saved pyBEHAVIOR outcomes; blank and unknown outcomes excluded. n = eligible trials.\n"
             "Heatmap: diagonal = match trials; empty grey cells = untested pairs; N/A = no eligible outcomes.",
             ha="center", fontsize=9)
    fig.tight_layout(rect=(0, .09, 1, .95))
    return fig


def plot_performance_position_heatmap(pairs, trials, title="Performance by position", cmap='viridis'):
    from dmts_voltage_viewer import plot_voltage_position_heatmap
    patterns = {}
    for trial in trials:
        for phase in ('sample', 'test'):
            presentation = trial.get(phase)
            if not presentation:
                continue
            name = presentation['stimulus'].strip()
            # CSV library STIM1 corresponds to NWB light ID 1.
            import re
            match = re.fullmatch(r'(?:STIM\s*)?(\d+)', name, re.IGNORECASE)
            if not match or not presentation['pattern']:
                continue
            sid = int(match.group(1))
            pattern = frozenset(presentation['pattern'])
            if sid in patterns and patterns[sid] != pattern:
                raise ValueError(f'StimID {sid} has inconsistent LED patterns in the CSV.')
            patterns[sid] = pattern
    means = {}
    for (sample, test), values in pairs.items():
        if sample == test and sample > 0 and values and sample in patterns:
            rate = float(100 * np.mean(values))
            means[str(sample)] = {position: rate for position in patterns[sample]}
    if not means:
        raise ValueError('No match-trial performance could be mapped to CSV LED patterns (STIM1, STIM2, …).')
    fig = plot_voltage_position_heatmap(means, title=title, cmin=0, cmax=100, cmap=cmap)
    fig.axes[0].set_title('Match-trial hit rate by LED position')
    fig.heatmap_kind = 'performance_percent'
    for text in fig.axes[0].texts:
        text.set_text(f'{float(text.get_text()):.1f}%')
    for ax in fig.axes:
        if ax.get_ylabel() == 'Mean voltage (V)':
            ax.set_ylabel('Match hit rate (%)')
    fig.texts[-1].set_text('Saved outcomes; match trials only. Each cell: mean of overlapping StimID hit rates (%).\n'
                          'Gray: no mapped eligible match trials. P increases right; N increases up.')
    return fig


def plot_session_summary(session, window=25, title="DMTS session"):
    if isinstance(window, bool) or int(window) != window or window < 1:
        raise ValueError("Rolling window must be a positive integer.")
    table = session["ResultsTable"]
    required = {"SavedOutcome", "SampleSoundId", "TestSoundId"}
    if not required.issubset(table.columns) or table.empty:
        raise ValueError("This summary requires saved outcomes and sample/test IDs for DMTS trials.")
    sample = np.asarray(table.SampleSoundId)
    test = np.asarray(table.TestSoundId)
    blank = (sample == 0) & (test == 0)
    match = (sample == test) & ~blank
    nonmatch = (sample != test) & ~blank
    aliases = {"hit": "HIT", "miss": "MISS", "falsealarm": "FA", "fa": "FA",
               "correct": "CR", "correctrejection": "CR", "cr": "CR"}
    def normalize(value):
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        return aliases.get(str(value).strip().lower().replace(" ", "").replace("_", ""), "Unknown")
    outcomes = np.array([normalize(value) for value in table.SavedOutcome], dtype=object)
    outcomes[blank] = "Blank"
    eligible = ~blank & np.isin(outcomes, ["HIT", "MISS", "FA", "CR"])
    correct = np.isin(outcomes, ["HIT", "CR"])
    trials = np.arange(1, len(table) + 1)
    fig = Figure(figsize=(13, 7))
    top, bottom = fig.subplots(2, 1, sharex=True, gridspec_kw={"height_ratios": [1, 1.4]})
    labels = ["HIT", "MISS", "FA", "CR"]
    if blank.any():
        labels.append("Blank")
    if (outcomes == "Unknown").any():
        labels.append("Unknown")
    colors = {"HIT": "#339966", "MISS": "#E69F00", "FA": "#CC4444", "CR": "#2878B5",
              "Blank": "#999999", "Unknown": "#555555"}
    for row, label in enumerate(labels):
        selected = outcomes == label
        top.scatter(trials[selected], np.full(selected.sum(), row), color=colors[label], s=22)
    top.set_yticks(range(len(labels)), labels)
    top.set_ylim(len(labels) - .5, -.5)
    top.set_ylabel("Saved outcome")
    top.grid(axis="x", alpha=.2)
    def curve(mask, success, label, color):
        x = trials[mask]
        if len(x):
            y = pd.Series(success[mask].astype(float)).rolling(int(window), min_periods=1).mean() * 100
            bottom.plot(x, y, label=label, color=color, marker="." if len(x) == 1 else None)
    curve(eligible, correct, "Overall accuracy", "#222222")
    curve(eligible & match, outcomes == "HIT", "Match hit rate", "#339966")
    curve(eligible & nonmatch, outcomes == "CR", "Non-match correct rejection", "#2878B5")
    if eligible.any():
        bottom.legend(loc="best")
    else:
        bottom.text(.5, .5, "No eligible saved outcomes", transform=bottom.transAxes, ha="center")
    bottom.set(xlabel="Session trial number", ylabel="Performance (%)", ylim=(-2, 102),
               xlim=(.5, len(table) + .5))
    bottom.grid(alpha=.2)
    bottom.set_title(f"Trailing {window} eligible trials per curve (available trials at session start)", fontsize=10)
    accuracy = f"{100 * correct[eligible].mean():.1f}%" if eligible.any() else "N/A"
    counts = " | ".join(f"{label}: {(outcomes == label).sum()}" for label in labels)
    fig.suptitle(f"{title}\n{len(table)} trials | Accuracy: {accuracy} | {counts}", fontsize=11)
    fig.text(.5, .015, "Source: saved pyBEHAVIOR outcomes. Blank and unknown outcomes excluded from performance.",
             ha="center", fontsize=9)
    fig.tight_layout(rect=(0, .04, 1, .92))
    return fig
