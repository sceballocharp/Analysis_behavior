# Behavior GUI Function Maps

Verified against the current local source on **2026-10-06**, including the DMTS Animal/batch additions in the v9 source saved at 12:48 local time.

Scope: `behavior_gui_v9.py` and its analysis/plotting modules in this directory. This is a source-level map, not a record of an interactive GUI test. Function names below are actual source entry points; indented descriptions summarize their behavior.

## Version and Main Files

- `behavior_gui_v8.py`: retained baseline; this map describes v9.
- `behavior_gui_v9.py`: active GUI, input discovery, batch processing, Groups, DMTS controls, session console, and terminal runners.
- `behavior_functions.py`: session loading, performance extraction, response analysis, and batch helpers.
- `behavior_plots.py`: session/trial plots, batch rolling curves, group averages, and offline learning/threshold helpers.
- `dmts_analysis.py`: dual-channel lick detection, DMTS scoring, and DMTS trial plots.
- `dmts_pretraining.py`: pretraining signal/lick plots.
- `dmts_matchonly.py`: MatchOnly plots and lick-event/histogram/trial-order tables.
- `dmts_summary.py`: session summary with adjustable rolling window.
- `dmts_batch.py`: saved-outcome DMTS session summaries and batch learning curves.
- `nwb_obj.py`: NWB session reader (`session_data_nwb`).
- `gui_preferences.json`: saved guide preference and configuration, including default NWB folder and plot layout.
- `NWB_BEHAVIOR_GUI_DATA_CONTRACT.md`: companion NWB data-contract document.

V9 now includes substantial functionality beyond the original v8 copy: automatic animal grouping, rolling batch performance, PKL export, Groups, DMTS, session inspection, and reset/result-generation handling.

## Startup and UI Layout

```text
main()
├─ parses CLI arguments
├─ --nogui -> terminal runners (see Terminal Map)
└─ GUI mode
   ├─ checks GUI dependencies
   ├─ destroys stale default Tk root / closes plots on reruns
   ├─ creates tk.Tk()
   ├─ ScanMediaFoldersApp(root, initial_folder, initial_file)
   │  ├─ sets title "BEHAVIOR v9" and window dimensions
   │  ├─ initializes input, animal-discovery, batch, Groups, and viewer state
   │  ├─ initializes scan_generation and session-console state
   │  ├─ reads gui_preferences.json
   │  ├─ _build_ui()
   │  └─ connects input traces -> _sync_current_input_label()
   ├─ if show_guide_at_startup: schedules _show_getting_started()
   └─ root.mainloop()
```

```text
_build_ui()
├─ Help -> Getting started -> _show_getting_started()
├─ Go/noGo main tab
│  ├─ Folder or File subtab: session input and hit source
│  ├─ Animal subtab: NWB discovery / detected animal / raw-folder discovery
│  ├─ Groups subtab: PKL files and group assignments
│  └─ input controls, Plot canvas, and Output panels
└─ DMTS main tab
   ├─ File subtab: NWB selection, trial viewer, pretraining / MatchOnly / summary
   └─ Animal subtab: mouse-folder scan, batch performance, Plot results, Save data

_select_gonogo_layout()
├─ switches input-control panels with the selected subtab
└─ shows the full-width Groups table only for Groups
   └─ _restore_groups_table_height() restores its splitter position
```

The Getting Started window is also available through Help. `_save_guide_preference()` persists its startup preference. The previous startup workflow-map description no longer applies.

## Input Selection and Reset

```text
_browse_folder() / _browse_nwb()
└─ select input and update active-input state

_reset_session()
├─ closes session console and trial viewer
├─ increments scan_generation (invalidates prior worker callbacks)
├─ clears single-session and batch results / selected inputs
├─ disables trial viewer
└─ clears main canvas
```

Reset invalidates old results; it does not terminate an already running worker thread.

## Animal / NWB Discovery

```text
Find NWB files -> _find_nwb_files_for_animal()
├─ asks for root folder (using configured default_nwb_folder)
├─ resets session and previous discovery state
├─ recursively collects files with .nwb suffix, case-insensitively
├─ _group_nwb_files(paths)
│  └─ _infer_animal_name_from_nwb_filename()
├─ stores nwb_scanned_files, nwb_search_root, and nwb_groups
├─ populates Detected animal selector
└─ logs unidentified files; waits for animal selection

Detected animal selection -> _select_nwb_group()
├─ resets session results
├─ sets animal_var and found_nwb_files for that animal
└─ logs files and redraws Animal canvas

Manual animal search -> _search_nwb_animal_override()
├─ requires an already scanned root and an animal name
├─ case-insensitive substring search over every scanned full path
│  └─ includes paths excluded from automatic animal grouping
└─ sets sorted found_nwb_files and redraws Animal canvas

Find folders -> _find_session_folders_for_animal()
└─ uses _find_session_folders_for_animal(folder_root, animal_name)
   └─ _is_session_folder() identifies raw session folders
```

The GUI discovery flow groups all detected animals first. It no longer infers one animal and immediately selects the first NWB as the current single-session input. The standalone `find_nwb_files_for_animal()` helper remains available to batch code.

## Single Session Processing

```text
Run canvas action -> _start_scan()
├─ validates folder/file and resolves active_input
├─ sets running state and captures hit source / scan_generation
└─ starts daemon worker -> _run_scan_worker(path, hit_source, generation)
   ├─ load_session_data_fromFolder() OR load_session_data_fromFile()
   ├─ extract_performance(session)
   ├─ analyze_session_responses(session, hit_source)
   └─ root.after() -> _deliver_scan_result(generation, callback, ...)
      ├─ ignores callbacks from an obsolete generation
      ├─ success -> _handle_scan_success()
      │  ├─ stores session data, performance, hit-by-sound and response outputs
      │  ├─ logs analysis results and enables trial viewer
      │  └─ redraws selected-input canvas
      └─ failure -> _handle_scan_error()
```

```text
analyze_session_responses(session, hit_source)
├─ is_dmts_lick(session)?
│  └─ analyze_dmts(session) -> (None, None, DMTS hit_by_sound)
└─ otherwise detect_ir_events(session["dataIR"]["full"])
   ├─ hit_source == "Licks"
   │  ├─ analyze_lick_events_by_trial()
   │  └─ extract_hit_by_sound_licks() -> (None, None, hit_by_sound)
   └─ IR mode
      ├─ analyze_ir_by_trial()
      └─ extract_hit_by_sound_IR() -> (events, trial_analysis, hit_by_sound)
```

Licks mode counts signal events; it does not return IR occupancy outputs. Dual-lick DMTS recognition takes precedence over the selected hit source.

## Performance Computation

```text
extract_performance(session)
├─ dual-lick DMTS -> analyze_dmts(session)["performance"]
└─ standard Go/NoGo
   ├─ requires a nonempty ResultsTable
   ├─ reads numeric TrialType; if absent/invalid, rebuilds from SoundId
   │  ├─ Eya fallback: SoundId 1 -> Go, 16 -> NoGo
   │  └─ generic fallback: SoundId values become TrialType
   ├─ persists normalized TrialType in ResultsTable
   ├─ Go mask: TrialType == SOUND_ID_GO
   ├─ NoGo mask: TrialType == SOUND_ID_NOGO
   ├─ no Go trials -> raises ValueError
   ├─ go = 100 * Go hits / n_go, rounded to 2 decimals
   ├─ no NoGo trials -> nogo = NaN; total = go
   └─ otherwise nogo = 100 * NoGo CR / n_nogo;
      total = mean(go, nogo), rounded to 2 decimals
```

Returned standard keys are `go`, `nogo`, `total`, `n_go`, and `n_nogo`. Performance values are percentages, not fractions. Total is a balanced Go/NoGo mean, not an overall trial-weighted accuracy.

## GUI Batch Processing and Learning Curve

```text
_run_all_found_nwb_files() / _run_all_found_session_folders()
├─ reset batch dictionaries
└─ for each selected NWB file / session folder
   ├─ load_session_data_fromFile() / load_session_data_fromFolder()
   ├─ extract_performance()
   ├─ analyze_session_responses()
   ├─ store batch_performance_by_file
   ├─ derive correctness from ResultsTable
   │  ├─ standard: Go uses Hit; NoGo uses CR
   │  └─ DMTSOutcome override: Hit/Correct -> 1;
   │     Miss/FalseAlarm -> 0; other outcomes -> NaN
   ├─ store trial_type and correct in batch_trial_performance_by_file
   ├─ _append_trials_by_sound_id() -> batch_trials_by_sound_id
   ├─ _merge_hit_by_sound() -> batch_hit_by_sound
   └─ log success or per-session error
```

These Go/NoGo GUI batch loops run in their handlers; the single-session worker-thread map does not describe them. DMTS Animal batch processing uses a separate background worker (see below).

```text
_draw_selected_input_box()
├─ Groups selected -> _draw_groups_canvas()
├─ Animal selected -> _draw_animal_canvas()
└─ otherwise draws single-session input / available analysis actions

Batch performance canvas action
└─ _handle_main_canvas_pick()
   └─ _open_batch_session_performance_plot()
      └─ plot_batch_session_performance(
           batch_performance_by_file,
           trial_performance_by_file=batch_trial_performance_by_file,
           plot_layout=preferences["plot_layout"], show=True, block=False)
         ├─ naturally sorts session names; skips error entries
         ├─ panel 1: Go / NoGo / Total per session
         └─ when trial data is supplied
            ├─ panel 2: trial correctness with session boundaries
            └─ panel 3: trailing 25-trial Go / NoGo / Total percentages
               └─ batch_rolling_trial_data()
```

`batch_rolling_trial_data()` concatenates trials in plot order. Its trailing window includes the current trial, crosses session boundaries, and uses available trials for initial windows. Go and NoGo percentages use valid outcomes of each type within that window of 25 total trials. Rolling total is the mean of the available Go and NoGo percentages. Trial indices are zero-based.

Batch and group figures accept `plot_layout` settings `dpi`, `subplot_width_px`, and `subplot_height_px`; invalid/nonpositive values fall back to defaults.

## Batch PKL Export and Groups

```text
Export batch data (.pkl) -> _export_batch_data()
├─ asks for output filename
├─ computes batch_rolling_trial_data(..., window=25)
└─ pickles schema_version=1 payload
   ├─ animal_name
   ├─ performance_by_file
   ├─ trial_performance_by_file
   ├─ trials_by_sound_id
   ├─ hit_by_sound
   └─ rolling_trial_data
```

Rolling data includes trial/session indices, trial types, correctness, Go/NoGo/Total percentages, and metadata describing the window and alignment.

```text
Groups: Select PKL folder -> _load_group_folder()
├─ clears loaded exports and assignments
├─ _read_group_export(path) validates expected schema / rolling data
├─ populates animal / file / session count / trial count / group table
└─ reports loaded and skipped files

_assign_selected_group() / _remove_selected_group()
└─ update assignments -> _refresh_group_assignments()

_save_group_assignments() / _load_group_assignments()
└─ separate JSON mapping using paths relative to the selected PKL folder
   (does not rewrite PKL analysis files)

Plot group averages -> _open_group_average_plot()
└─ plot_group_average_performance(exports, assignments, plot_layout=...)
   └─ group_animal_curves()
      ├─ ignores unassigned files
      ├─ validates 25-trial rolling data and zero-based sequential indices
      ├─ rejects an animal assigned to more than one group
      ├─ averages multiple exports of the same animal first
      └─ _mean_aligned_curves() averages available finite values by trial index
```

Group plots show grey individual-animal curves and colored group means for Go, NoGo, and Total. Alignment is by cumulative trial index; shorter curves contribute only where data exist. The Groups loader expects the Go/NoGo GUI schema_version=1 export, not arbitrary PKL dictionaries, terminal batch JSON, or the separate DMTS dmts_batch_v1 export.

## Session Plots, Trial Viewer, and Console

| GUI handler | Plot / action |
| --- | --- |
| `_open_performance_plot()` | `plot_performance()` |
| `_open_ir_occupancy_plot()` | `plot_ir_occupancy_by_sound()` |
| `_open_hit_by_sound_plot()` | `plot_hit_by_sound()` |
| `_open_trial_viewer()` | Builds trial navigation window |
| `_change_trial()` / `_render_trial_viewer_plot()` | `plot_trial_ir_and_sound()` for selected zero-based trial |
| `_open_session_console()` | Opens Python session-inspection console |
| `_execute_session_command()` | Executes commands and displays final expression/output/errors in Output |

The console exposes NumPy as `np` and the five `single_session_*` data/analysis objects. Commands can modify data and files. Its namespace persists for the loaded session and is reset when the session changes.

`_update_plots()` also wraps `plot_session_visualizations()` for the combined plot set. Figure saving is available through plot toolbars where installed; GUI batch PKL and DMTS MatchOnly CSV exports are separate actions.

## DMTS Analysis and GUI

```text
is_dmts_lick(session)
└─ recognizes TaskType/task_type == DMTS and TriggerType == lick

analyze_dmts(session)
├─ returns cached session["dmts_analysis"] when present
├─ reads/validates task timing, minimum lick count, and channel thresholds
├─ uses LeftLick / RightLick signals and their timing provenance
├─ crossings() detects threshold events
├─ score_trial() classifies responses
└─ stores DMTS analysis used by performance, hit-by-sound, and trial plotting
```

```text
DMTS Browse NWB -> _browse_dmts_nwb()
└─ updates DMTS file selection and closes an existing DMTS trial viewer

_handle_dmts_canvas_pick()
├─ dmts_pretraining -> _run_dmts_pretraining()
│  ├─ dmts_pretraining.plot_pretraining(file, settings)
│  ├─ stores left_lick_times / right_lick_times
│  └─ _show_dmts_figure()
├─ dmts_matchonly -> _run_dmts_matchonly()
│  ├─ load_session_data_fromFile()
│  ├─ dmts_matchonly.plot_matchonly(session, settings)
│  ├─ stores lick_events, lick_histogram, trial_order
│  ├─ _show_dmts_figure()
│  └─ if Save results enabled: writes three CSV tables into
│     <NWB stem>_lick_analysis beside the source file
└─ dmts_summary -> _open_dmts_summary()
   ├─ loads browsed file (or MatchOnly file fallback)
   ├─ dmts_summary.plot_session_summary(session, window=25)
   └─ Update / Enter redraws using selected eligible-trial rolling window

_open_dmts_trial_viewer()
├─ loads selected DMTS file and analyzes responses with "Licks"
├─ creates zero-based Go / Previous / Next navigation
└─ plot_trial_ir_and_sound()
   └─ DMTS sessions use dmts_analysis.plot_dmts_trial()
```

DMTS pretraining and MatchOnly settings are read from their GUI controls. Their signal-analysis plots are separate entry points from the general single-session Go/NoGo processing flow.

## DMTS Animal Discovery, Batch Analysis, and Export

```text
DMTS Animal -> Select mouse folder -> _browse_dmts_mouse_folder()
└─ _start_dmts_folder_scan(folder)
   ├─ increments _dmts_batch_generation and clears prior batch results/errors
   ├─ cancels previous folder scan via Event and its scheduled poll
   ├─ starts daemon worker using os.walk(..., followlinks=False)
   │  ├─ sorts directories/files case-insensitively
   │  ├─ finds .nwb files recursively, case-insensitively
   │  └─ queues progress, paths, warnings, and completion
   └─ Tk poll every 100 ms drains up to 100 messages
      ├─ fills dmts_animal_nwb_files and the Animal Output panel
      ├─ displays folder/file counts and scan warnings
      └─ _draw_dmts_canvas() updates available actions
```

Folder discovery lists NWB files without first checking their task type. Non-DMTS or incomplete sessions are skipped during analysis. The canvas shows Animal batch actions only after scanning finishes and more than one NWB file is found. `_write_dmts_animal_output()` appends batch messages to this tab's dedicated output panel.

```text
_handle_dmts_canvas_pick() (Animal actions)
├─ dmts_batch -> _run_dmts_batch()
│  ├─ requires >=2 discovered files, no active scan, and no running batch
│  ├─ clears results/errors and captures _dmts_batch_generation
│  ├─ sorts full file paths case-insensitively
│  ├─ daemon worker, for each path
│  │  ├─ load_session_data_fromFile()
│  │  ├─ dmts_batch.summarize_session(session, path)
│  │  └─ queues result or per-file error, then progress/completion
│  └─ Tk poll every 100 ms drains up to 100 messages
│     ├─ fills dmts_batch_results / dmts_batch_errors
│     ├─ reports progress, session accuracy, and skipped files
│     └─ enables Plot results / Save data when successful results exist
├─ dmts_batch_plot -> _plot_dmts_batch()
│  └─ dmts_batch.plot_batch(results) -> _show_dmts_figure()
└─ dmts_batch_save -> _save_dmts_batch()
   └─ asks for .pkl filename and saves the DMTS batch payload
```

A new mouse-folder scan invalidates previous batch workers and polls using `_dmts_batch_generation`. An in-progress file load is not forcibly interrupted; old results are ignored and the worker checks generation before processing another file. Plot and save handlers require results and a finished batch.

```text
dmts_batch.summarize_session(session, path)
├─ requires TaskType/task_type == DMTS
├─ requires nonempty ResultsTable with SavedOutcome, SampleSoundId, TestSoundId
├─ classifies each trial
│  ├─ sample == test == 0 -> blank
│  ├─ sample == test -> match
│  └─ otherwise -> nonmatch
├─ eligible outcomes: Hit / Miss / FalseAlarm / Correct on nonblank trials
├─ correct: Hit/Correct -> 1; Miss/FalseAlarm -> 0; ineligible -> None
└─ returns file, trials, total, match, nonmatch
   └─ percentage correct over eligible trials; no eligible trials -> NaN
```

This batch path uses **recorded SavedOutcome**, without calling `analyze_dmts()` to rescore lick signals. Overall accuracy pools all eligible trials; it is not the balanced Go/NoGo mean. Trial records contain one-based `trial`, `kind`, `outcome`, `correct`, `sample_id`, and `test_id`.

```text
dmts_batch.plot_batch(results)
├─ upper panel: Overall / Match / Non-match accuracy per successful session
│  └─ sessions remain in file-path order, numbered from 1
└─ lower panel: rolling performance across sessions
   ├─ x = one-based cumulative trial number, including ineligible trials
   ├─ each curve rolls over its own last 25 eligible trials
   ├─ initial windows use available trials; windows cross session boundaries
   └─ vertical lines mark session boundaries
```

Unlike the Go/NoGo rolling curve's 25-total-trial window, the DMTS Match and Non-match curves each use up to 25 eligible trials of that category. Blanks and unknown outcomes do not enter any accuracy denominator, but retain positions on the cumulative trial axis.

`_save_dmts_batch()` defaults to `<mouse-folder-name>_dmts_batch.pkl` and writes:

| Payload key | Value |
| --- | --- |
| `format` | `dmts_batch_v1` |
| `outcome_source` | `saved` |
| `rolling_window` | `25` |
| `mouse_folder` | Selected folder path |
| `sessions` | Successful session summaries, including trial records |
| `errors` | Skipped-file records containing `file` and `error` |

Rolling arrays are computed when plotting; the export stores trial records and the window size. This format is separate from the Go/NoGo Groups PKL schema and currently has no corresponding GUI import action.

## Terminal Map

```text
main() --nogui
├─ --batch-folder -> run_nogui_folder_batch()
│  ├─ discover raw session folders
│  ├─ _process_batch_session() per folder
│  └─ write <animal>_folder_batch_performance.json
├─ --batch-nwb -> run_nogui_nwb_batch()
│  ├─ behavior_functions.run_nwb_batch_analysis()
│  └─ write <animal>_nwb_batch_performance.json
└─ otherwise -> run_nogui()
   ├─ load session; extract_performance(); analyze_session_responses()
   ├─ write results-table CSV and summary JSON
   └─ --show-plots: generate and save PNGs using the Agg backend
```

Relevant arguments: `--folder`, `--file`, `--outdir`, `--hit-source {IR,Licks}`, `--animal`, `--folder-root`, and `--nwb-root`. In single-session terminal mode, a valid NWB file takes precedence over a valid folder. If both batch flags are supplied, folder-batch dispatch takes precedence.

`_process_batch_session()` uses cached DMTS hit-by-sound after performance extraction for DMTS; otherwise it selects IR or lick trial analysis using the chosen hit-by-sound function. `save_batch_dict()`, `load_batch_dict()`, and `load_batch_dicts()` provide separate programmatic pickle helpers; they do not by themselves produce the GUI Groups export schema.

## Offline Learning and Threshold Helpers

These helpers in `behavior_plots.py` are separate from the live GUI batch and Groups curves described above.

```text
plot_batch_go_performance_by_window()
└─ bins alldataGO per animal/session and returns performance curves

plot_batch_go_mean_curve()
├─ batch_go_performance_matrix()
├─ plots mean with variability/error bars
└─ optional sigmoid fit / trials-to-threshold estimate

plot_batch_go_performance_with_threshold_subplot()
├─ per-animal windowed curves
├─ sigmoid or first-bin threshold estimate
└─ trials-to-threshold summary bars
```

Additional offline entry points include `plot_batch_go_performance_with_threshold_protocol_columns()`, `plot_trials_to_threshold_summary()`, `plot_trials_to_threshold_boxplot_summary()`, and `compare_trials_to_threshold_groups()` (with permutation-test support). Sound-level helpers include `plot_mean_go_by_sound()`, `fit_sigmoid_to_group_go()`, and `plot_mean_go_by_sound_with_sigmoid()`.

## Maintenance Check

When v9 changes, review this map against GUI callbacks, `analyze_session_responses()`, `extract_performance()`, plot signatures, and export schemas. Update the verification date only after checking the source. Changes to the Groups input contract, DMTS dispatch, rolling-window semantics, or terminal export formats should be reflected explicitly.

