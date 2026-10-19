# Behavior GUI v10 Function Maps

Verified against the local source on **2026-10-16**. Entry point: `behavior_gui_v10.py`. This is a source-level workflow map, not a record of an interactive GUI test. Unqualified Go/NoGo methods belong to `ScanMediaFoldersApp`; DMTS methods belong to `DmtsPanel`; Lever methods belong to `LeverPanel`.

## Modules and Ownership

| File | Responsibility |
| --- | --- |
| `behavior_gui_v10.py` | Application shell, Go/NoGo UI, discovery, session/batch processing, Groups, console, terminal runners |
| `dmts_gui.py` | Independent `DmtsPanel`, held as `app.dmts`; File, Animal and Groups workflows |
| `lever_gui.py` | Independent `LeverPanel`; NWB loading, trial viewer and lever plots |
| `gui_fonts.py` | `GuiFonts`: shared Tk/Matplotlib font configuration |
| `behavior_functions.py` | Session loaders, response/performance analysis and batch helpers |
| `behavior_plots.py` | Go/NoGo session, trial, batch, group and offline learning plots |
| `dmts_analysis.py` | Dual-lick scoring, timing/coverage provenance and trial plots |
| `dmts_pretraining.py` / `dmts_matchonly.py` | Time-window and trial-aligned lick plots |
| `dmts_summary.py` / `dmts_trial_examples.py` | Saved-outcome summaries, StimID performance and example trials |
| `dmts_batch.py` | Session summaries, chronological ordering, engagement and batch plots |
| `dmts_blanks.py` | Blank-response validity, summaries and rolling rates |
| `dmts_groups.py` | DMTS export validation, rolling curves and equal-file group means |
| `dmts_voltage_viewer.py` | CSV presentation parsing, voltage grids and stimulus averages |
| `nwb_obj.py` | `session_data_nwb` reader |
| `gui_preferences.json` | Guide preference, default NWB folder, plot layout and fonts |
| `Launch Behavior_GUI.bat` | Launches highest numeric `behavior_gui_v*.py` version using local environment |
| `NWB_BEHAVIOR_GUI_DATA_CONTRACT.md` | Companion data-contract document |

## Startup and UI Assembly

```text
main()
├─ parses CLI arguments
├─ --nogui -> terminal runners (below)
└─ GUI mode
   ├─ checks dependencies; clears stale Tk/Matplotlib state on rerun
   ├─ root = tk.Tk()
   ├─ ScanMediaFoldersApp(root, initial_folder, initial_file)
   │  ├─ title BEHAVIOR v10; input/batch/Groups/viewer/console state
   │  ├─ reads preferences; GuiFonts(preferences).apply(root)
   │  ├─ _build_ui()
   │  └─ input traces -> _sync_current_input_label()
   ├─ optional _show_getting_started() scheduled after idle
   └─ root.mainloop()

ScanMediaFoldersApp._build_ui()
├─ _build_menu() / _build_main_tabs()
├─ _build_gonogo_layout(): Folder or File / Animal / Groups
├─ _build_gonogo_groups_controls() / _build_gonogo_input_controls()
├─ _build_gonogo_animal_controls() / _build_gonogo_output()
├─ _build_gonogo_canvas()
├─ DmtsPanel(self): File / Animal / Groups
│  └─ File contains Main / Plot settings
├─ _build_lever_panel() -> LeverPanel(self): File
└─ _configure_layout_reporting()
```

`_select_gonogo_layout()` switches Go/NoGo input panels and shows the full-width Groups table only on that subtab; `_restore_groups_table_height()` restores its splitter position. Help opens the guide, and `_save_guide_preference()` persists its startup preference. `GuiFonts.tk()` / `mpl()` supply configured font sections for controls, notebooks, output, console, guide and canvas text.

## Go/NoGo Input, Detection and Reset

```text
_browse_folder() -> select folder; manual IR/Licks source
_browse_nwb() -> select file -> _detect_nwb_hit_source()
├─ reads acquisition/Parameters key/value metadata with h5py
├─ _normalize_trigger_type(): IR/infrared/irfork -> IR; lick/licks -> Licks
└─ unknown/missing metadata -> clears source; requires manual selection
_manual_hit_source() -> override status; rerun applies selection

_reset_session()
├─ closes session console and trial viewer
├─ increments scan_generation; invalidates old worker callbacks
├─ clears session/batch results and input state
└─ disables viewer and clears canvas
```

Reset does not forcibly terminate a worker. Automatic source detection is attached to single-file browsing; batch loops use the current source selection, not per-file metadata detection.

## Go/NoGo Animal Discovery

```text
_find_nwb_files_for_animal()
├─ choose root; recursively collect .nwb files case-insensitively
├─ _group_nwb_files() -> _infer_animal_name_from_nwb_filename()
├─ store nwb_scanned_files, nwb_search_root, nwb_groups
└─ populate Detected animal; report unidentified files
_select_nwb_group()
└─ reset session; set animal_var and found_nwb_files; redraw
_search_nwb_animal_override()
└─ case-insensitive full-path search over all scanned files,
   including files automatic grouping could not identify
_find_session_folders_for_animal() [method]
└─ _find_session_folders_for_animal(root, animal) [module helper]
   └─ _is_session_folder() identifies raw session folders
```

Automatic NWB discovery waits for animal selection. The standalone `find_nwb_files_for_animal()` helper is also used by batch code.

## Go/NoGo Single Session and Response Dispatch

```text
Run canvas action -> _start_scan()
├─ validate input, resolve active_input, require IR or Licks
└─ daemon thread -> _run_scan_worker(path, source, generation)
   ├─ load_session_data_fromFolder() OR load_session_data_fromFile()
   ├─ extract_performance()
   ├─ analyze_session_responses()
   └─ root.after() -> _deliver_scan_result()
      ├─ ignore obsolete generation
      ├─ _handle_scan_success(): store outputs, log, enable viewer, redraw
      └─ _handle_scan_error(): report failure

analyze_session_responses(session, hit_source)
├─ is_dmts_lick() -> analyze_dmts() -> (None, None, DMTS hit_by_sound)
└─ detect_ir_events(session["dataIR"]["full"])
   ├─ Licks -> analyze_lick_events_by_trial() -> extract_hit_by_sound_licks()
   │  └─ returns (None, None, hit_by_sound)
   └─ IR -> analyze_ir_by_trial() -> extract_hit_by_sound_IR()
      └─ returns (events, trial_analysis, hit_by_sound)
```

Licks mode counts signal events and does not return IR occupancy outputs. Dual-lick DMTS recognition takes precedence over the chosen source.

`extract_performance()` dispatches dual-lick DMTS to `analyze_dmts()`. Otherwise it requires a nonempty ResultsTable, normalizes TrialType (Eya fallback: SoundId 1 -> Go and 16 -> NoGo; generic fallback: SoundId), and persists TrialType. Go uses Hit, NoGo uses CR. Results `go`, `nogo`, `total` are percentages rounded to two decimals, alongside `n_go` and `n_nogo`. No Go raises an error; no NoGo gives `nogo=NaN` and `total=go`; otherwise total is the balanced mean of Go and NoGo percentages.

## Go/NoGo Batch and Rolling Curve

```text
_run_all_found_nwb_files() / _run_all_found_session_folders()
├─ clear batch dictionaries
└─ for each selected input
   ├─ load -> extract_performance() -> analyze_session_responses()
   ├─ store batch_performance_by_file
   ├─ build trial correctness: Go Hit / NoGo CR
   │  └─ DMTSOutcome override: Hit/Correct=1, Miss/FalseAlarm=0, other=NaN
   ├─ store batch_trial_performance_by_file (trial_type, correct)
   ├─ _append_trials_by_sound_id() / _merge_hit_by_sound()
   └─ log success or per-session error

_draw_selected_input_box()
├─ Groups -> _draw_groups_canvas()
├─ Animal -> _draw_animal_canvas()
└─ single-session actions
_handle_main_canvas_pick() -> _open_batch_session_performance_plot()
└─ plot_batch_session_performance()
   ├─ natural session-name sorting; skip error entries
   ├─ session Go/NoGo/Total panel
   └─ with trial data: correctness panel and rolling performance panel
      └─ batch_rolling_trial_data(window=25)
```

Go/NoGo batch loops execute in their GUI handlers, unlike the threaded DMTS batch. Rolling windows include the current trial, cross session boundaries and use available initial trials. Each window spans 25 total trials; category percentages use finite outcomes of that category within the window. Total averages available Go/NoGo percentages. Indices are zero-based. Batch/group layout accepts `dpi`, `subplot_width_px`, `subplot_height_px` preferences with validated defaults.

## Go/NoGo Export and Groups

```text
_export_batch_data()
└─ schema_version=1 PKL:
   animal_name, performance_by_file, trial_performance_by_file,
   trials_by_sound_id, hit_by_sound, rolling_trial_data

_load_group_folder() -> _read_group_export() -> file/animal/counts table
_assign_selected_group() / _remove_selected_group()
└─ _refresh_group_assignments()
_save_group_assignments() / _load_group_assignments()
└─ separate JSON mapping of relative file paths to group names
_open_group_average_plot() -> plot_group_average_performance()
└─ group_animal_curves() -> _mean_aligned_curves()
```

Rolling exports include trial/session indices, correctness, percentages and window metadata. Groups requires this schema and 25-trial rolling data, ignores unassigned files, rejects cross-group assignments for the same animal, averages duplicate-animal exports first, then averages available animals by cumulative trial index. Grey curves represent animals; colored curves represent group means. DMTS PKLs use a different schema and loader.

## Go/NoGo Plots, Viewer and Console

| Handler | Target |
| --- | --- |
| `_open_performance_plot()` | `plot_performance()` |
| `_open_ir_occupancy_plot()` | `plot_ir_occupancy_by_sound()` |
| `_open_hit_by_sound_plot()` | `plot_hit_by_sound()` |
| `_open_trial_viewer()` / `_change_trial()` / `_render_trial_viewer_plot()` | Zero-based navigation with `plot_trial_ir_and_sound()` |
| `_update_plots()` | `plot_session_visualizations()` |
| `_open_session_console()` / `_execute_session_command()` | Python commands and final expression results in Output |

The console exposes `np` and five `single_session_*` objects, retains a namespace for the loaded session, and resets on session change. Commands can modify session data and files.

## DMTS File Panel

All handlers here belong to `dmts_gui.DmtsPanel`, not `ScanMediaFoldersApp`.

```text
DmtsPanel._build_ui()
├─ _build_dmts_layout()
├─ _build_dmts_groups_controls() / _build_dmts_animal_controls()
├─ _build_dmts_file_controls() / _build_dmts_plot_settings()
└─ _build_dmts_canvas()

_browse_dmts_nwb() / _select_dmts_example() -> _select_dmts_file()
├─ close old trial viewer; clear cached data and export readiness
├─ inspect NWB datasets -> _dmts_file_actions
│  ├─ LeftLick + RightLick + Reward -> time-window plot
│  └─ sample_sound_ids + test_sound_ids + HMCF -> summary/StimID performance
│     └─ plus both lick signals -> aligned licks/trial examples
└─ _draw_dmts_canvas() offers Run NWB file

_load_dmts_file()
├─ daemon worker loads required session and/or pretraining signals
├─ queue and Tk polling deliver results
├─ discard result if selected filename/actions changed
└─ cache _dmts_session / _dmts_loaded_signals; enable supported actions
```

`_handle_dmts_canvas_pick()` routes actions with loaded/busy/capability guards. File output and Animal output are separate.

| Action / handler | Target |
| --- | --- |
| Plot Session Rawdata: `_open_dmts_summary()` | `dmts_summary.plot_session_summary()`; adjustable eligible-trial window |
| Plot Time Window: `_run_dmts_pretraining()` | `dmts_pretraining.plot_pretraining()`; cached signals and time/threshold/smoothing controls |
| Plot Trial-Aligned Licks: `_run_dmts_matchonly()` | `dmts_matchonly.plot_matchonly()`; caches events/histogram/trial order |
| Performance by StimID: `_open_dmts_sound_performance()` | `dmts_summary.plot_performance_by_sound()` |
| Trial Examples: `_open_dmts_trial_examples()` | `dmts_trial_examples.plot_trial_examples()` |
| Trial Viewer: `_open_dmts_trial_viewer()` | `plot_trial_ir_and_sound()` -> `plot_dmts_trial()` for DMTS |
| Export results: `_export_dmts_file_results()` | Explicit CSV export after time-window or aligned analysis |

`_show_dmts_figure()` embeds plots and toolbar. File exports go beside the NWB in `<stem>_lick_analysis`: either `pretraining_lick_events.csv`, or `lick_events.csv`, `lick_histogram.csv` and `trial_order.csv`. Export is a separate action.

## DMTS Scoring Sources

```text
is_dmts_lick(): TaskType/task_type == DMTS and TriggerType == lick
analyze_dmts()
├─ use cached dmts_analysis if available
├─ validate task timing, thresholds and minimum lick count
├─ signal_times() / crossings() -> timed response-window events
├─ score_trial() when signals cover the response window
├─ saved-outcome fallback for incomplete signals
└─ store performance, hit-by-sound, trial coverage, outcome provenance,
   mismatch count and saved-fallback count
```

General performance/response dispatch uses this analysis. DMTS summary, StimID performance and Animal batch accuracy use recorded `SavedOutcome`. Batch additionally calls `analyze_dmts()` for engagement and blank responses without replacing saved accuracy outcomes.

## DMTS CSV Voltage Tools

```text
_dmts_voltage_logs() -> sibling CSVs excluding TrialLog.csv / Parameters.csv
_select_dmts_csv_log()
└─ only candidate or unique date/time-token match; report ambiguity otherwise
_load_dmts_csv() -> parse_dmts_log_file() -> _dmts_csv_loaded()
_open_dmts_voltage_viewer() -> DMTSVoltageViewer
├─ browse/load, Previous/Next/Go -> update_plot()
└─ voltages_to_pattern_grid() / draw_voltage_grid()
_open_dmts_csv_average() -> DMTSVoltageViewer.open_stim_summary()
└─ voltage_presentations_by_stim() / plot_voltage_stim_summary()
```

CSV presentation tools are independent of NWB behavioral scoring.

## DMTS Animal Batch

```text
_browse_dmts_mouse_folder() -> _start_dmts_folder_scan()
├─ invalidate prior batch generation; clear results/errors
├─ cancel previous scan Event and scheduled poll
├─ daemon worker: os.walk(followlinks=False), case-insensitive NWB matching
└─ Tk queue polling updates files, warnings and progress
_run_dmts_batch()
├─ requires >=2 files, finished scan, no running batch
├─ validates positive silent-match threshold (default 5)
├─ worker loads paths -> dmts_batch.summarize_session()
├─ Tk poll collects results/errors and logs engagement/blank summaries
└─ completion sorts results using session_sort_key()
```

Workers visit files in path order; plots and exports use timezone-aware NWB `session_start_time`, normalized to UTC. Invalid/naive/missing times go last with file-path tie breaking. Generation checks discard obsolete results; an ongoing file load is not forcibly interrupted.

```text
summarize_session(session, path, silent_match_threshold=5)
├─ require DMTS and nonempty SavedOutcome / SampleSoundId / TestSoundId
├─ classify blank (both IDs zero), match (equal), nonmatch (different)
├─ correctness: Hit/Correct=1, Miss/FalseAlarm=0, blank/unknown=None
├─ analyze_dmts() supplies lick counts and window coverage
├─ add_blank_responses() / blank_summary()
├─ mark_engagement()
└─ file, session_start_time, trials, total/match/nonmatch,
   engagement, blank_response
```

Accuracy pools eligible saved outcomes. Trial records are one-based. Failed lick analysis preserves saved accuracy and marks engagement unknown with a warning.

`mark_engagement()` allows N silent match trials; disengagement begins at N+1 without backdating. A match with any lick restores engagement; unknown match counts reset to unknown. Other trial kinds inherit state. Summaries include periods, eligible/engaged/unknown counts and engaged accuracy.

Blank responses are separate from accuracy and engagement. A side needs full response-window coverage; either-side validity needs both channels. `blank_rolling()` uses 25 valid blanks per session, independently of engagement filtering.

| Animal action | Target |
| --- | --- |
| `_plot_dmts_batch()` | `plot_batch()`; chronological session accuracy, rolling curves, disengagement shading, blank panels |
| `_plot_dmts_batch_stim_hit()` | `plot_hit_by_stim_sessions()` / `session_hit_rates_by_stim()` |
| `_plot_dmts_outcome_counts()` | `plot_session_outcome_counts()`; absolute saved HIT/CR counts |
| `_save_dmts_batch()` | Versioned DMTS PKL |
| `_load_dmts_batch()` | Validate and restore PKL; cancel obsolete scans/batches |

Accuracy curves use 25 eligible trials per category across sessions, retaining all trial positions on x. Optional engaged-only display adds overall engaged curves to the original curves. Blank windows reset per session.

## DMTS Export and Groups

New exports use `format=dmts_batch_v2`, `outcome_source=saved`, `rolling_window=25`, `session_order=session_start_time`, plus `mouse_folder`, sorted `sessions` and `errors`. Trial records include engagement/blank information. Rolling arrays are calculated from records when plotting.

```text
_load_dmts_batch() / _load_dmts_groups()
└─ dmts_groups.export_curves() accepts dmts_batch_v1 and dmts_batch_v2
   ├─ timestamp ordering when timestamps exist; otherwise stored order
   └─ engaged-only mode requires engagement flags

DMTS Groups: _load_dmts_groups()
├─ load PKLs directly in selected folder; validate/report skipped files
└─ default group "All files"
_assign_dmts_group() -> selected files; empty name means All files
_plot_dmts_groups() -> dmts_groups.plot_groups()
├─ export_curves(): overall/match/nonmatch rolling curves, optional filter
├─ forward-fill within each export's recorded span
├─ separate per-session blank curves, independent of engagement filter
└─ mean_curves(): equal-file means and finite contributor counts
```

Thin curves represent PKLs; bold curves represent group means. Optional blank panels appear when valid blank data exist. Short recordings do not extend beyond their span. `dmts_group_averages` retains means and contributor counts. Unlike Go/NoGo Groups, DMTS Groups averages files without deduplicating animals and has no assignment save/load handlers.

## Lever Panel

```text
_build_lever_panel() -> LeverPanel(app)
├─ browse(): select NWB, increment generation, clear data/viewer
├─ draw() / on_pick(): lever_load, lever_plot, lever_crossing
├─ load(): daemon worker -> load_lever_file(); Tk queue polling
│  ├─ ignore obsolete generations
│  ├─ populate channel and inferred Go/Test labels
│  └─ enable viewer if trial timing exists
├─ open_plot()
│  ├─ plot_lever_trials() -> Go/Test heatmaps and mean/SEM traces
│  │  └─ lever_mean_sem()
│  └─ distribution=True -> plot_crossing_distribution()
└─ open_viewer(): trial navigation, recorded signals and event annotations
```

`load_lever_file()` reads supported numeric signals with h5py, validates timestamp/start-rate timing, and applies conversion/offset metadata. Trial intervals come from `intervals/trials`, falling back to rising TrialType==99 anchors. Missing stops extend to the next anchor or signal end. Recorded labels and task sound-ID parameters determine Go/Test defaults.

Event fields are `trigger_time_s`, `crossing_duration_s`, `trial_end_s`. Missing values can be filled from sibling `TrialLog.csv` only on a unique unused trigger match within 0.101 s. Otherwise markers remain missing. The viewer interprets hold/release modes from task parameters. Across-trial plots use selected channel, editable labels and positive window duration, preserve trial order, and mask samples outside trial limits. Lever does not use the Go/NoGo or DMTS scoring pipeline.

## Terminal Runners

```text
main() --nogui
├─ --batch-folder -> run_nogui_folder_batch()
│  ├─ discover folders -> _process_batch_session()
│  └─ <animal>_folder_batch_performance.json
├─ --batch-nwb -> run_nogui_nwb_batch()
│  ├─ behavior_functions.run_nwb_batch_analysis()
│  └─ <animal>_nwb_batch_performance.json
└─ run_nogui()
   ├─ load -> extract_performance() -> analyze_session_responses()
   ├─ results-table CSV and summary JSON
   └─ --show-plots -> plot_session_visualizations() -> PNGs via Agg
```

Arguments include `--folder`, `--file`, `--outdir`, `--hit-source {IR,Licks}`, `--animal`, `--folder-root`, `--nwb-root`. A valid NWB takes precedence over a valid folder in single-session terminal mode; folder batch wins if both batch flags are set. These are the existing general runners, not DMTS Animal or Lever CLI equivalents.

`_process_batch_session()` uses cached DMTS hit-by-sound after performance extraction, otherwise IR/lick trial analysis. `save_batch_dict()`, `load_batch_dict()` and `load_batch_dicts()` are separate programmatic pickle helpers; they do not construct GUI export schemas automatically.

## Offline Learning Helpers

These functions remain separate from live Go/NoGo and DMTS batch curves:

- `plot_batch_go_performance_by_window()`: bins alldataGO per animal/session.
- `plot_batch_go_mean_curve()`: `batch_go_performance_matrix()`, variability, optional sigmoid/threshold estimate.
- `plot_batch_go_performance_with_threshold_subplot()` and `plot_batch_go_performance_with_threshold_protocol_columns()`: windowed learning/threshold views.
- `plot_trials_to_threshold_summary()`, `plot_trials_to_threshold_boxplot_summary()`, `compare_trials_to_threshold_groups()`: threshold summaries/comparisons.
- `plot_mean_go_by_sound()`, `fit_sigmoid_to_group_go()`, `plot_mean_go_by_sound_with_sigmoid()`: sound-level curves/fits.

## Maintenance

Review module ownership, canvas action IDs, loader capabilities, scoring sources, ordering/window semantics and export versions when updating this map. Keep Go/NoGo animal averages distinct from DMTS equal-file averages, and saved outcomes distinct from signal-derived scores. Update the verification date after checking the source.
