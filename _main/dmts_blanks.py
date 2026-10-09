"""Blank responses remain separate from task accuracy and engagement."""
import numpy as np
import pandas as pd

BLANK_SIDES = ("any", "left", "right")


def add_blank_responses(trial, detected):
    for side in BLANK_SIDES:
        trial[f"blank_{side}_response"] = None
    if trial["kind"] != "blank" or detected is None:
        return
    coverage = detected.get("response_coverage", {})
    for side in ("Left", "Right"):
        if coverage.get(side, False):
            trial[f"blank_{side.lower()}_response"] = bool(len(detected["events"][side]))
    left, right = trial["blank_left_response"], trial["blank_right_response"]
    # Either-side rate requires both channels to cover the full window.
    if left is not None and right is not None:
        trial["blank_any_response"] = left or right


def blank_summary(trials):
    result = {"window_trials": 25, "n_blank_trials": sum(t["kind"] == "blank" for t in trials),
              "timing": "trial start + 2*SoundDuration_s + Delay_s; duration ResponseWindow_s"}
    for side in BLANK_SIDES:
        values = [t[f"blank_{side}_response"] for t in trials
                  if t["kind"] == "blank" and t.get(f"blank_{side}_response") is not None]
        result[side] = dict(valid_trials=len(values), responding_trials=sum(values),
                            rate_pct=100*np.mean(values) if values else float("nan"))
    return result


def blank_rolling(trials, side, window=25):
    indices = [i for i, trial in enumerate(trials) if trial["kind"] == "blank"
               and trial.get(f"blank_{side}_response") is not None]
    values = [float(trials[i][f"blank_{side}_response"]) for i in indices]
    rates = pd.Series(values, dtype=float).rolling(window, min_periods=1).mean().to_numpy()*100
    return np.asarray(indices, dtype=int)+1, rates
