# NWB Data Contract for the Behavior GUI

This document describes the NWB/HDF5 layout expected by the current behavior GUI and analysis code. A writer that follows this contract should produce NWB files that can be loaded by `load_session_data_fromFile()` without changing `behavior_gui_v6.py`, `behavior_gui_v7.py`, `behavior_functions.py`, or `behavior_plots.py`.

## Loader Entry Point

The GUI loads NWB files through:

```python
from behavior_functions import load_session_data_fromFile
```

Internally this creates:

```python
nwb_obj.session_data_nwb(nwbfile=path)
```

and calls:

```python
read_paths()
extract_continuous_signal()
generate_results_table()
get_parameters()
```

The NWB reader uses `h5py` and expects exact dataset paths.

## Required NWB Dataset Paths

The following datasets are required by the current reader.

### Continuous Signals

```text
/stimulus/presentation/SoundCopy/data
/stimulus/presentation/WhichSound/data
/acquisition/Reward/data
/acquisition/TrialType/data
/acquisition/IRFork/data
```

These are loaded as NumPy arrays:

```python
sound_signal = np.array(h5f["stimulus"]["presentation"]["SoundCopy"]["data"])
whichSound = np.array(h5f["stimulus"]["presentation"]["WhichSound"]["data"])
reward = np.array(h5f["acquisition"]["Reward"]["data"])
trialtype = np.array(h5f["acquisition"]["TrialType"]["data"])
IRdata = np.array(h5f["acquisition"]["IRFork"]["data"])
```

Only `sound_signal`, `trialtype`, and `IRdata` are returned to the GUI, but `WhichSound` and `Reward` are still read and therefore must exist unless the reader is changed.

Expected meaning:

```text
SoundCopy/data       Continuous sound TTL/signal trace.
WhichSound/data      Continuous/encoded sound identity trace, read for compatibility.
Reward/data          Continuous reward trace, read for compatibility.
TrialType/data       Continuous trial marker trace. Values equal to 99 mark trial/reward-window anchors.
IRFork/data          Continuous IR fork/lick signal used for event detection.
```

The analysis assumes `IRFork/data` and `SoundCopy/data` are sampled at approximately 1000 Hz. The trial marker signal is interpreted with:

```python
trial_bin_s = 0.1
```

so each sample in `TrialType/data` corresponds to 100 ms.

### Trial Table Datasets

```text
/intervals/trials/id
/intervals/trials/sound_ids
/intervals/trials/HMCF
/intervals/trials/trial_type
```

These are converted into the GUI `ResultsTable` DataFrame:

```python
ResultsTable = pd.DataFrame({
    "TrialsId":  /intervals/trials/id,
    "SoundId":   /intervals/trials/sound_ids,
    "TrialType": encoded from /intervals/trials/trial_type,
    "Hit":       HMCF == "Hit",
    "Miss":      HMCF == "Miss",
    "CR":        HMCF == "Correct",
    "FA":        HMCF == "FalseAlarm",
})
```

Required string values:

```text
/intervals/trials/trial_type:
    "Go"   -> TrialType = 1
    "NoGo" -> TrialType = 2

/intervals/trials/HMCF:
    "Hit"        -> Hit = 1
    "Miss"       -> Miss = 1
    "Correct"    -> CR = 1
    "FalseAlarm" -> FA = 1
```

All other rows are encoded as zero for those binary columns.

### Parameters

```text
/file_create_date
/acquisition/Parameters/key
/acquisition/Parameters/value
```

`/file_create_date` is expected to contain at least one UTF-8 string in ISO datetime format, for example:

```text
2025-05-26T11:28:10+00:00
```

The date portion is stored as:

```python
parameters["date"] = "YYYY-MM-DD"
```

`Parameters/key` and `Parameters/value` should be same-length arrays of UTF-8 byte strings. They are converted into:

```python
parameters[key] = value
```

## Normalized Python Object Returned to the GUI

`load_session_data_fromFile()` returns this dictionary:

```python
{
    "parameters": dict,
    "dataIR": {
        "full": np.ndarray,
        "mean": float,
    },
    "trialID": {
        "full": np.ndarray,
        "types": list,
    },
    "sound_signal": np.ndarray,
    "ResultsTable": pd.DataFrame,
    "nTotalTrials": int,
}
```

### `parameters`

Dictionary from `/file_create_date` and `/acquisition/Parameters`.

Must include:

```python
parameters["date"]
```

Other parameter keys are preserved and used by batch exports.

### `dataIR`

```python
dataIR["full"] = IRFork/data
dataIR["mean"] = mean(IRFork/data)
```

Used by:

```python
detect_ir_events(data_session_dict["dataIR"]["full"])
analyze_ir_by_trial(data_session_dict, ir_events)
plot_ir_events(...)
plot_trial_ir_and_sound(...)
```

### `trialID`

```python
trialID["full"] = acquisition/TrialType/data
trialID["types"] = sorted unique values from TrialType/data
```

Important: `analyze_ir_by_trial()` finds trial anchors with:

```python
np.where(data_session_dict["trialID"]["full"] == 99)
```

Therefore the writer must place `99` values in `TrialType/data` at the trial/reward-window anchor samples.

### `sound_signal`

```python
sound_signal = stimulus/presentation/SoundCopy/data
```

Used by `plot_trial_ir_and_sound()` to plot the sound trace for a selected trial.

### `ResultsTable`

Must contain exactly these analysis columns:

```text
TrialsId
SoundId
TrialType
Hit
Miss
CR
FA
```

`extract_performance()` requires:

```text
SoundId
TrialType
Hit
CR
```

The current performance constants are:

```python
SOUND_ID_GO = 1
SOUND_ID_NOGO = 2
```

So Go trials are `TrialType == 1`, and NoGo trials are `TrialType == 2`.

### `nTotalTrials`

```python
nTotalTrials = len(ResultsTable)
```

This should match the number of trial rows in `/intervals/trials`.

## IR Event Analysis Expectations

The GUI computes IR events from `IRFork/data` using:

```python
detect_ir_events(data_ir, rise_threshold=0.5, fall_threshold=-1.0)
```

This detects:

```python
ir_events["debut_fork"]
ir_events["end_fork"]
ir_events["timespent_each_fork_event"]
```

Then `analyze_ir_by_trial()` aligns IR entries to trial anchors from `trialID["full"] == 99`.

Current alignment defaults:

```python
rw_fix = 1.0
trial_bin_s = 0.1
fe = 1000
timereward_ms = 1000
pre_rw_entry_tolerance_ms = 250
```

For each trial, valid entries are those with:

```python
t_start_rw - 250 ms <= debut_fork <= t_start_rw + 1000 ms
```

where:

```python
t_start_rw = marker_sample_in_TrialType_data * trial_bin_s * fe
```

## Minimal Compatibility Checklist for a Writer

To create NWB files that the current GUI can analyze without code changes:

1. Save all required HDF5 paths listed above.
2. Use UTF-8 byte/string arrays for `HMCF`, `trial_type`, parameter keys, parameter values, and `file_create_date`.
3. Use `trial_type` strings exactly `"Go"` and `"NoGo"`.
4. Use `HMCF` strings exactly `"Hit"`, `"Miss"`, `"Correct"`, and `"FalseAlarm"`.
5. Save continuous IR data at `/acquisition/IRFork/data`.
6. Save continuous sound data at `/stimulus/presentation/SoundCopy/data`.
7. Save trial anchor markers as value `99` in `/acquisition/TrialType/data`.
8. Keep `/intervals/trials/id`, `/intervals/trials/sound_ids`, `/intervals/trials/HMCF`, and `/intervals/trials/trial_type` aligned row-by-row.
9. Ensure `len(/intervals/trials/id)` equals the number of behavioral trials.
10. Use Go/NoGo trial coding that maps to `TrialType == 1` and `TrialType == 2` after loading.

## Notes for Future Robustness

The current reader does not use defensive path lookup for NWB files. Missing paths such as `/acquisition/Reward/data` or `/stimulus/presentation/WhichSound/data` will raise an error even if the GUI does not later use those arrays.

If a future writer cannot provide one of these paths, the reader should be updated first. Otherwise, the safest option is to write placeholder arrays with the correct path and compatible shape.
