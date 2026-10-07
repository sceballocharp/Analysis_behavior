"""Compact DMTS batch results based on recorded trial outcomes."""
import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from dmts_analysis import parameters, analyze_dmts
from datetime import datetime, timezone


def session_sort_key(result):
    """Order valid, timezone-aware NWB start times first; unknown times last."""
    try:
        value = datetime.fromisoformat(result.get("session_start_time") or "")
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Missing timezone")
        return (0, value.astimezone(timezone.utc).timestamp(), result.get("file", ""))
    except (TypeError, ValueError, OverflowError):
        return (1, 0, result.get("file", ""))


def mark_engagement(trials, silent_match_threshold=5):
    """Allow N silent matches; disengagement begins at N+1, without backdating."""
    if isinstance(silent_match_threshold, bool) or int(silent_match_threshold) != silent_match_threshold or silent_match_threshold < 1:
        raise ValueError("Silent-match threshold must be a positive integer.")
    streak = 0
    state = "engaged"
    periods = []
    current = None
    for trial in trials:
        if trial["kind"] == "match":
            counts = (trial.get("left_lick_count"), trial.get("right_lick_count"))
            if any(count is not None and count > 0 for count in counts):
                streak, state = 0, "engaged"
            elif any(count is None for count in counts):
                streak, state = 0, "unknown"
            else:
                streak += 1
                if streak > silent_match_threshold:
                    state = "disengaged"
        trial["engagement"] = state
        trial["disengaged"] = None if state == "unknown" else state == "disengaged"
        trial["silent_match_streak"] = streak
        if state == "disengaged":
            if current is None:
                current = {"start_trial": trial["trial"], "end_trial": trial["trial"]}
                periods.append(current)
            current["end_trial"] = trial["trial"]
        else:
            current = None
    eligible = [t for t in trials if t["correct"] is not None]
    engaged = [t for t in eligible if t["engagement"] == "engaged"]
    return dict(silent_match_threshold=int(silent_match_threshold), periods=periods, n_periods=len(periods),
                eligible_trials=len(eligible), engaged_eligible_trials=len(engaged),
                unknown_eligible_trials=sum(t["engagement"] == "unknown" for t in eligible),
                engaged_pct=100 * len(engaged) / len(eligible) if eligible else float("nan"),
                engaged_accuracy=100 * np.mean([t["correct"] for t in engaged]) if engaged else float("nan"))


def summarize_session(session, path, silent_match_threshold=5):
    if parameters(session).get("TaskType", parameters(session).get("task_type", "")).upper() != "DMTS":
        raise ValueError("Not a DMTS session")
    table = session["ResultsTable"]
    if not {"SavedOutcome", "SampleSoundId", "TestSoundId"}.issubset(table.columns) or table.empty:
        raise ValueError("Missing saved DMTS trial results")
    trials = []
    for index, (_, row) in enumerate(table.iterrows(), 1):
        sample, test = int(row.SampleSoundId), int(row.TestSoundId)
        kind = "blank" if sample == test == 0 else "match" if sample == test else "nonmatch"
        outcome = str(row.SavedOutcome).strip()
        valid = kind != "blank" and outcome in ("Hit", "Miss", "FalseAlarm", "Correct")
        trials.append(dict(trial=index, kind=kind, outcome=outcome,
                           correct=int(outcome in ("Hit", "Correct")) if valid else None,
                           sample_id=sample, test_id=test))
    warning = None
    try:
        analysis = analyze_dmts(session)
        if len(analysis["trials"]) != len(trials):
            raise ValueError("Lick trial count does not match saved results")
        for trial, detected in zip(trials, analysis["trials"]):
            # Only complete response windows can establish that there were zero licks.
            complete = detected["outcome"] is not None
            for side in ("Left", "Right"):
                events = detected["events"].get(side)
                trial[side.lower() + "_lick_count"] = len(events) if events is not None and (complete or len(events)) else None
        thresholds = analysis.get("thresholds", {})
    except (ValueError, KeyError, TypeError, IndexError) as exc:
        warning = f"Engagement unavailable: {exc}"
        thresholds = {}
        for trial in trials:
            trial.update(left_lick_count=None, right_lick_count=None)
    engagement = mark_engagement(trials, silent_match_threshold)
    if warning:
        for trial in trials:
            trial.update(engagement="unknown", disengaged=None)
        engagement.update(periods=[], n_periods=0, engaged_eligible_trials=0,
                          unknown_eligible_trials=engagement["eligible_trials"], engaged_pct=float("nan"),
                          engaged_accuracy=float("nan"))
    engagement.update(warning=warning, lick_thresholds=thresholds, window="response window", smoothing_ms=0)
    def rate(kind=None):
        selected = [t for t in trials if t["correct"] is not None and (kind is None or t["kind"] == kind)]
        return 100 * np.mean([t["correct"] for t in selected]) if selected else float("nan")
    return dict(file=str(path), session_start_time=session.get("session_start_time"),
                trials=trials, total=rate(), match=rate("match"), nonmatch=rate("nonmatch"), engagement=engagement)


def plot_batch(results, show_engaged_only=False):
    if not results:
        raise ValueError("Run batch performance first.")
    results = sorted(results, key=session_sort_key)
    fig = Figure(figsize=(13, 8))
    top, bottom = fig.subplots(2, 1)
    x = np.arange(1, len(results) + 1)
    for key, label, color in (("total", "Overall", "#222222"), ("match", "Match", "#339966"),
                              ("nonmatch", "Non-match", "#2878B5")):
        y = [r[key] for r in results]
        if np.isfinite(y).any():
            top.plot(x, y, "o-", label=label, color=color)
    top.set(xlabel="Session start date/time (chronological; unknown times last)", ylabel="Accuracy (%)", ylim=(-2, 102))
    top.set_xticks(x)
    top.set_xticklabels([str(r.get("session_start_time") or "Unknown start time").replace("T", "\n")
                        for r in results], rotation=30, ha="right", fontsize=8)
    if show_engaged_only:
        top.plot(x, [r.get("engagement", {}).get("engaged_accuracy", np.nan) for r in results],
                 "o--", color="#D55E00", label="Engaged-only overall")
    if top.lines:
        top.legend()
    offset = 0
    all_trials = []
    for i, result in enumerate(results):
        for period in result.get("engagement", {}).get("periods", []):
            bottom.axvspan(offset + period["start_trial"] - .5, offset + period["end_trial"] + .5,
                           color="grey", alpha=.22, zorder=0)
        if i:
            bottom.axvline(offset + .5, color=".7", lw=.7)
        all_trials.extend(result["trials"])
        offset += len(result["trials"])
    trial_numbers = np.arange(1, len(all_trials) + 1)
    for kind, label, color in ((None, "Overall", "#222222"), ("match", "Match", "#339966"),
                               ("nonmatch", "Non-match", "#2878B5")):
        mask = np.array([t["correct"] is not None and (kind is None or t["kind"] == kind) for t in all_trials])
        values = [t["correct"] for t, use in zip(all_trials, mask) if use]
        if values:
            y = pd.Series(values).rolling(25, min_periods=1).mean() * 100
            bottom.plot(trial_numbers[mask], y, label=label, color=color)
    bottom.set(xlabel="Cumulative session trial number", ylabel="Performance (%)", ylim=(-2, 102),
               title="Trailing 25 eligible trials per curve; vertical lines separate sessions")
    if show_engaged_only:
        mask = np.array([t["correct"] is not None and t.get("engagement") == "engaged" for t in all_trials])
        values = [t["correct"] for t, use in zip(all_trials, mask) if use]
        if values:
            rolling = pd.Series(values).rolling(25, min_periods=1).mean() * 100
            bottom.plot(trial_numbers[mask], rolling, "--", color="#D55E00", label="Engaged-only overall")
    if bottom.lines:
        handles, labels = bottom.get_legend_handles_labels()
        if handles:
            bottom.legend()
    for ax in (top, bottom):
        ax.grid(alpha=.2)
    periods = sum(r.get("engagement", {}).get("n_periods", 0) for r in results)
    eligible = sum(r.get("engagement", {}).get("eligible_trials", 0) for r in results)
    engaged = sum(r.get("engagement", {}).get("engaged_eligible_trials", 0) for r in results)
    pct = f"{100 * engaged / eligible:.1f}%" if eligible else "N/A"
    fig.suptitle(f"DMTS batch performance — {len(results)} sessions | {periods} disengaged periods | Engaged eligible trials: {pct}\n"
                 "Engagement estimated from match responses; grey = disengaged; original saved outcomes retained", fontsize=10)
    fig.tight_layout(rect=(0, 0, 1, .93))
    return fig
