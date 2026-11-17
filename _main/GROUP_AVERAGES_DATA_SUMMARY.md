# Group averages: data summary

Verified against `behavior_plots.py:305–418` and `behavior_gui_v10.py:1439–1450` on 2026-11-13. Scope: Plot Group Averages in Go/NoGo → Groups.

## What data is used?

| Input | Contents used |
| --- | --- |
| `group_exports` | Loaded animal batch PKL payloads, keyed by resolved file path |
| `group_assignments` | File path → group name; unassigned exports are ignored |
| `animal_name` | Animal identity, compared case-insensitively |
| `rolling_trial_data.window_trials` | Must equal 25 |
| `rolling_trial_data.trial_index` | Cumulative trial indices, required to be 0 through N−1 |
| `rolling_trial_data.go_pct` | Saved 25-trial rolling Go performance |
| `rolling_trial_data.nogo_pct` | Saved 25-trial rolling NoGo performance |
| `rolling_trial_data.total_pct` | Saved 25-trial rolling total performance |

The full PKL remains loaded, but this plot does not use raw signals, per-sound response counts, or the session performance dictionary to calculate its group mean. It reads the saved rolling percentages.

## Function workflow

```text
_open_group_average_plot()
└─ plot_group_average_performance(group_exports, group_assignments)
   ├─ group_animal_curves()
   │  ├─ validate assigned exports and animal identity
   │  ├─ reject an animal assigned to different groups
   │  ├─ validate rolling window, indices and metric lengths
   │  └─ _mean_aligned_curves(): average multiple exports for each animal
   ├─ draw each animal's Go / NoGo / Total curve in grey
   ├─ _mean_aligned_curves(): average animals within each group
   ├─ draw group means in color
   └─ return Matplotlib figure
```

## Intermediate animal data

`group_animal_curves()` builds this local structure:

```python
groups = {
    "Control": {
        "animal_a": {
            "go_pct": [...],
            "nogo_pct": [...],
            "total_pct": [...],
        },
        "animal_b": {
            "go_pct": [...],
            "nogo_pct": [...],
            "total_pct": [...],
        },
    },
}
```

Each array contains a percentage for each cumulative trial index. If an animal has multiple exports, their values are averaged at matching indices; exports are not concatenated.

## Group mean calculation

For each group, metric, and trial index:

`group_mean[i] = mean(finite animal values at index i)`

Animals are equally weighted at each index. Nonfinite values and animals whose curves have already ended are excluded. If no finite values are available, the mean is NaN. For example, 80% and 60% produce a group mean of 70%.

The x-axis is cumulative trial index, not session/date. Curves can have different lengths. The legend's `n` is the number of animal curves in the group; the number contributing at a particular trial can be smaller. Total is averaged from the animals' saved `total_pct` arrays, independently of the group Go/NoGo arrays.

## What is retained or saved?

| Data/result | Where it remains |
| --- | --- |
| Original loaded PKL payloads | `self.group_exports` in app memory |
| Group membership | `self.group_assignments` in app memory; separately saved as JSON if requested |
| Animal-level combined curves | Local `groups` variable while plotting; not assigned to an app attribute |
| Group mean arrays | Local `mean` variable while plotting; x/y values are retained in the figure's plotted lines |
| Go, NoGo and Total plots | Returned Matplotlib figure, displayed by the GUI |

Clicking Plot Group Averages does not create a new PKL/CSV, modify the original animal exports, or store a dedicated group-average dictionary on the app. It does not calculate SEM, confidence intervals, or statistical comparisons. Those would require a separate export/statistics feature.

Generate group files and Plot Curves Single Animals are separate actions with different outputs; their saved dictionaries are not the output of Plot Group Averages.
