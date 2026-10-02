# Behavior GUI Function Maps

Status as of 2026-10-02:

- `behavior_gui_v8.py` is the frozen baseline.
- `behavior_gui_v9.py` is the active working copy created from v8.
- The live GUI learning curve is currently the clickable "Batch performance" plot.
- The older/offline GO-window learning-curve helpers exist in `behavior_plots.py`, but are not currently called by the live GUI.

## Version Handoff

```text
behavior_gui_v8.py
└─ frozen baseline

behavior_gui_v9.py
└─ copied from v8
   ├─ window title changed to "BEHAVIOR v9"
   └─ layout comment changed from v8 to v9
```

## GUI Startup Map

```text
main()
├─ parses CLI arguments
├─ handles --nogui modes
├─ clears stale Tk / Matplotlib state from previous reruns
├─ creates root = tk.Tk()
├─ creates ScanMediaFoldersApp(root, ...)
├─ opens startup workflow map
└─ enters root.mainloop()
```

```text
ScanMediaFoldersApp.__init__()
├─ stores root
├─ sets window title
├─ creates input state
│  ├─ folder_var
│  ├─ file_var
│  ├─ animal_var
│  └─ hit_source_var
├─ creates batch state
│  ├─ found_nwb_files
│  ├─ found_session_folders
│  ├─ batch_performance_by_file
│  ├─ batch_trial_performance_by_file
│  ├─ batch_trials_by_sound_id
│  └─ batch_hit_by_sound
├─ calls _build_ui()
├─ connects folder/file variable traces
└─ draws initial selected-input box
```

## Animal / NWB Discovery Map

```text
Animal tab controls
└─ _build_ui()
   ├─ "Animal name" entry -> self.animal_var
   ├─ "Find NWB files" button -> _find_nwb_files_for_animal()
   ├─ "Run All NWB" button -> _run_all_found_nwb_files()
   ├─ "Find folders" button -> _find_session_folders_for_animal()
   └─ "Run All Folders" button -> _run_all_found_session_folders()
```

```text
Find NWB files
└─ _find_nwb_files_for_animal()
   ├─ reads self.animal_var
   ├─ asks user to select NWB root folder
   ├─ if animal name is empty:
   │  ├─ scans selected root for *.nwb
   │  ├─ _infer_animal_name_from_nwb_files()
   │  │  └─ _infer_animal_name_from_nwb_filename()
   │  │     ├─ supports sub_2914 / sub-2914-style names
   │  │     └─ supports M588-style names
   │  └─ writes inferred name back to self.animal_var
   ├─ find_nwb_files_for_animal()
   ├─ fills self.found_nwb_files
   ├─ clears self.found_session_folders
   ├─ selects first found NWB file as current input
   └─ calls _draw_selected_input_box()
```

```text
find_nwb_files_for_animal(nwb_root, animal_name)
├─ recursively scans for *.nwb
└─ returns files where animal_name appears in:
   ├─ file name
   └─ parent path
```

## Single Session Map

```text
Run button
└─ _start_scan()
   └─ starts worker thread
      └─ _scan_worker()
         ├─ load_session_data_fromFolder()
         │  OR load_session_data_fromFile()
         ├─ extract_performance()
         ├─ detect_ir_events()
         ├─ analyze_ir_by_trial()
         ├─ _get_hit_by_sound_func()
         ├─ extract_hit_by_sound_IR()
         │  OR extract_hit_by_sound_licks()
         └─ schedules GUI update
            └─ _handle_scan_success()
               ├─ stores single-session outputs
               ├─ enables trial viewer
               └─ calls _draw_selected_input_box()
```

## Batch Learning Curve Map

This is the path used by the live GUI to build the visible clickable learning curve.

```text
Run All NWB
└─ _run_all_found_nwb_files()
   ├─ clears previous batch dictionaries
   ├─ chooses hit-by-sound function via _get_hit_by_sound_func()
   └─ for each file in self.found_nwb_files:
      ├─ load_session_data_fromFile()
      ├─ extract_performance()
      │  └─ computes:
      │     ├─ go
      │     ├─ nogo
      │     ├─ total
      │     ├─ n_go
      │     └─ n_nogo
      ├─ detect_ir_events()
      ├─ analyze_ir_by_trial()
      ├─ extract_hit_by_sound_IR()
      │  OR extract_hit_by_sound_licks()
      ├─ stores session performance in self.batch_performance_by_file
      ├─ derives trial-by-trial correctness from ResultsTable
      ├─ stores trial data in self.batch_trial_performance_by_file
      ├─ _append_trials_by_sound_id()
      └─ _merge_hit_by_sound()
```

```text
Run All Folders
└─ _run_all_found_session_folders()
   ├─ same batch dictionary reset
   └─ for each folder in self.found_session_folders:
      ├─ load_session_data_fromFolder()
      ├─ extract_performance()
      ├─ detect_ir_events()
      ├─ analyze_ir_by_trial()
      ├─ extract_hit_by_sound_IR()
      │  OR extract_hit_by_sound_licks()
      ├─ stores session performance in self.batch_performance_by_file
      ├─ derives trial-by-trial correctness from ResultsTable
      ├─ stores trial data in self.batch_trial_performance_by_file
      ├─ _append_trials_by_sound_id()
      └─ _merge_hit_by_sound()
```

```text
Clickable plot entry
└─ _draw_selected_input_box()
   └─ if self.batch_performance_by_file exists:
      ├─ draws "Batch performance" rectangle
      ├─ draws clickable marker
      └─ sets gid="plot_batch_session_performance"
```

```text
Click handling
└─ _handle_main_canvas_pick(event)
   └─ if event.artist.get_gid() == "plot_batch_session_performance":
      └─ _open_batch_session_performance_plot()
```

```text
Final batch learning curve plot
└─ _open_batch_session_performance_plot()
   └─ plot_batch_session_performance(
        self.batch_performance_by_file,
        trial_performance_by_file=self.batch_trial_performance_by_file,
        show=True,
        block=False,
      )
      ├─ sorts sessions by natural session key
      ├─ extracts per-session go values
      ├─ extracts per-session nogo values
      ├─ extracts per-session total values
      ├─ plots Go / NoGo / Total across sessions
      └─ if trial data exists:
         └─ plots trial-by-trial correctness underneath
```

## Performance Computation Map

```text
extract_performance(session_datadict)
├─ reads session_datadict["ResultsTable"]
├─ reads SoundId
├─ reads TrialType when available
├─ if TrialType is missing:
│  └─ rebuilds trial_type from SoundId / user-specific fallback
├─ writes normalized TrialType back into ResultsTable
├─ reads Hit and CR
├─ Go trials:
│  └─ trial_type == SOUND_ID_GO
├─ NoGo trials:
│  └─ trial_type == SOUND_ID_NOGO
├─ perf_go = hits on Go / number of Go trials
├─ perf_nogo = CR on NoGo / number of NoGo trials
└─ perf_total = mean(perf_go, perf_nogo)
```

## Offline GO-Window Learning Helpers

These functions are available, but the current live GUI batch plot does not call them.

```text
plot_batch_go_performance_by_window(batch_hit_by_sound, ...)
├─ normalizes one-animal or multi-animal input
├─ loops over session/date keys
├─ reads alldataGO arrays
├─ bins trials by n_size_window
├─ computes correct fraction per bin
├─ plots each animal/session sequence
└─ returns all_perf
```

```text
plot_batch_go_mean_curve(loaded_batches, ...)
├─ batch_go_performance_matrix()
│  ├─ normalizes batch input
│  ├─ bins alldataGO per animal
│  ├─ aligns animals into a padded matrix
│  ├─ computes mean_curve
│  ├─ computes std_curve
│  └─ computes sem_curve
├─ plots mean curve with error bars
├─ optionally fits _learning_sigmoid()
└─ optionally estimates trials_to_threshold
```

```text
plot_batch_go_performance_with_threshold_subplot(batch_hit_by_sound, ...)
├─ plot_batch_go_performance_by_window()
├─ for each animal:
│  ├─ computes performance curve
│  ├─ threshold_method == "sigmoid":
│  │  └─ _fit_learning_sigmoid_threshold()
│  │     ├─ fits _learning_sigmoid()
│  │     └─ estimates trial count at threshold
│  └─ threshold_method == "first_bin":
│     └─ uses first bin above threshold
├─ plots animal learning curves
└─ plots trials-to-threshold summary bars
```

## Main Files

- `behavior_gui_v8.py`: frozen GUI baseline.
- `behavior_gui_v9.py`: active GUI working copy.
- `behavior_functions.py`: loading, extraction, per-session performance, batch helpers.
- `behavior_plots.py`: single-session plots, batch performance plot, offline learning-curve helpers.

