"""Chronological session summaries using recorded outcomes only."""
import numpy as np
import pandas as pd
from matplotlib.figure import Figure


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
