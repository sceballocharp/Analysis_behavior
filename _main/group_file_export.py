"""Build per-group animal/session dictionaries from compact Go/noGo IR summaries."""
from pathlib import Path
import os
import pickle
import re
import numpy as np
import pandas as pd
from session_order import session_sort_key, session_start_time
from behavior_functions import (
    load_session_data_fromFile, load_session_data_fromFolder,
    detect_ir_events, analyze_ir_by_trial,
)
from dmts_analysis import parameters

GO_TYPE = 1
NOGO_TYPE = 2


def _recover_moved_nwb(path):
    """Recover a session moved from a protocol folder into its mouse subfolder."""
    match = re.search(r"(?:^|[_-])(M\d+)(?=[_-]|$)", path.stem, flags=re.IGNORECASE)
    if match:
        animal = match.group(1)
        for folder_name in dict.fromkeys((animal, animal.upper(), animal[1:])):
            candidate = path.parent / folder_name / path.name
            if candidate.is_file():
                return candidate
    if path.is_file():
        raise ValueError(f"Session loader returned no data for existing NWB file: {path}")
    raise FileNotFoundError(f"NWB file not found: {path}. Check the saved session path or its animal subfolder.")


def extract_fork_summary(path):
    """Use the same IR occupancy duration criterion as extract_hit_by_sound_IR."""
    path = Path(path)
    original_path = path
    session = (load_session_data_fromFile(path) if path.suffix.lower() == ".nwb"
               else load_session_data_fromFolder(path))
    if session is None and path.suffix.lower() == ".nwb":
        path = _recover_moved_nwb(path)
        session = load_session_data_fromFile(path)
    if not isinstance(session, dict):
        raise ValueError(f"Session loader returned no session dictionary: {path}")
    params = parameters(session)
    task = str(params.get("TaskType", params.get("task_type", ""))).strip().upper()
    if task == "DMTS":
        return None
    table = session["ResultsTable"].reset_index(drop=True)
    if "TrialType" not in table:
        raise ValueError("ResultsTable has no TrialType column.")
    trial_types = pd.to_numeric(table["TrialType"], errors="raise")
    events = detect_ir_events(session["dataIR"]["full"])
    analysis = analyze_ir_by_trial(session, events)
    threshold_ms = float(analysis["stay_threshold_ms"])
    sample_rate = float(analysis["sample_rate_hz"])
    if not np.isfinite(sample_rate) or sample_rate <= 0:
        raise ValueError("Fork analysis has an invalid sample rate.")
    if not np.isfinite(threshold_ms) or threshold_ms < 0:
        raise ValueError("Fork analysis has an invalid stay threshold.")
    rows = []
    for trial_index, trial in analysis["dict_data_IRxTrial"].items():
        if trial_index < 0 or trial_index >= len(table):
            raise ValueError("Fork trial index exceeds ResultsTable length.")
        trial_type = trial_types.iloc[trial_index]
        if trial_type not in (GO_TYPE, NOGO_TYPE):
            continue
        duration_ms = float(np.sum(trial["timespent_each_time"]) * 1000 / sample_rate)
        if not np.isfinite(duration_ms) or duration_ms < 0:
            raise ValueError(f"Invalid fork duration in trial {trial_index + 1}.")
        responded = bool(duration_ms >= threshold_ms)
        is_go = trial_type == GO_TYPE
        rows.append(dict(trial=int(trial_index) + 1, trial_type=int(trial_type),
                         sound_id=table.iloc[trial_index].get("SoundId", None),
                         fork_duration_ms=duration_ms, responded=responded,
                         outcome=("Hit" if responded else "Miss") if is_go
                                 else ("FalseAlarm" if responded else "Correct")))
    trials = pd.DataFrame(rows)
    if trials.empty:
        raise ValueError("No eligible Go/NoGo trials with fork analysis.")
    trials = trials.sort_values("trial", kind="stable").reset_index(drop=True)
    n_go = int(trials["trial_type"].eq(GO_TYPE).sum())
    n_nogo = int(trials["trial_type"].eq(NOGO_TYPE).sum())
    hits = int(trials["outcome"].eq("Hit").sum())
    crs = int(trials["outcome"].eq("Correct").sum())
    return dict(file=str(path), original_source_path=str(original_path), session_start_time=session_start_time(session),
                stay_threshold_ms=threshold_ms, sample_rate_hz=sample_rate,
                n_recorded_trials=len(table), n_analyzed_trials=len(trials),
                n_go=n_go, n_nogo=n_nogo, HIT=hits, CR=crs,
                hit_pct=100 * hits / n_go if n_go else np.nan,
                cr_pct=100 * crs / n_nogo if n_nogo else np.nan,
                performance_pct=100 * (hits + crs) / len(trials), trials=trials)


def build_group_files(exports, assignments, destination, progress=lambda text: None, reader=extract_fork_summary):
    """Write one pickle per assigned group. Duplicate animal/session pairs count once."""
    collected, identities = {}, {}
    for export_path, payload in exports.items():
        group = assignments.get(export_path)
        if not group:
            continue
        name = str(payload.get("animal_name", "")).strip()
        if not name:
            raise ValueError(f"Missing animal name: {export_path}")
        identity = name.casefold()
        if identity in identities and identities[identity][0] != group:
            raise ValueError(f"Animal {name} is assigned to more than one group")
        identities.setdefault(identity, (group, name))
        animal = identities[identity][1]
        files = collected.setdefault(group, {}).setdefault(animal, {})
        for source, performance in payload.get("performance_by_file", {}).items():
            if not isinstance(performance, dict) or "error" in performance:
                continue
            # Relative references originate beside the animal batch export.
            path = Path(source)
            if not path.is_absolute():
                path = Path(export_path).resolve().parent / path
            path = path.resolve()
            files.setdefault(os.path.normcase(str(path)), (path, performance))
    if not collected:
        raise ValueError("Assign PKL files to groups before generating group files")
    groups, warnings = {}, []
    for group, animals in collected.items():
        result = {}
        for animal, files in animals.items():
            sessions, errors, skipped_sessions = [], [], []
            for path, performance in files.values():
                progress(f"Analyzing {group} / {animal}: {path}")
                try:
                    item = reader(path)
                    if item is None:
                        skipped_sessions.append(dict(file=str(path), reason="DMTS session"))
                        progress(f"Skipped DMTS session: {path}")
                        continue
                    item = dict(item)
                    item["source_path"] = item.get("file") or str(path)
                    if item["source_path"] != str(path):
                        progress(f"Recovered moved session: {path} -> {item['source_path']}")
                    if not item.get("session_start_time"):
                        item["session_start_time"] = performance.get("session_start_time")
                    sessions.append(item)
                    progress(f"Stored {animal} / {path.name}: {item['n_analyzed_trials']} analyzed trials")
                    if session_sort_key((str(path), item))[0]:
                        warnings.append(f"{animal} / {path.name}: unknown start time; ordered after dated sessions by path")
                except Exception as exc:
                    errors.append(dict(file=str(path), error=str(exc)))
                    warnings.append(f"Skipped {animal} / {path}: {exc}")
            sessions.sort(key=lambda item: session_sort_key((item["source_path"], item)))
            parent_folders = [str(path.parent if path.suffix.lower() == ".nwb" else path) for path, _ in files.values()]
            try:
                folder = os.path.commonpath(parent_folders) if parent_folders else ""
            except ValueError:
                folder = ""
            result[animal] = dict(animal_name=animal, folder=folder, sessions=sessions,
                                  errors=errors, skipped_sessions=skipped_sessions)
            progress(f"{animal}: stored {len(sessions)} sessions; {len(errors)} errors; {len(skipped_sessions)} DMTS skips")
            if not sessions:
                warnings.append(f"{animal}: no eligible Go/NoGo fork sessions; retained error/skip details")
        if result:
            groups[group] = result
        else:
            warnings.append(f"Group {group}: no readable sessions; no empty group file was written")

    if not groups:
        raise ValueError("No assigned animal data found.")
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    sources = []
    for index, (group, animals) in enumerate(groups.items(), 1):
        safe = re.sub(r"[^\w.-]+", "_", str(group)).strip("._")[:80] or "group"
        path = destination / f"{index:02d}_{safe}_gonogo_allAnimals_dataframes.pkl"
        temporary = path.with_suffix(".pkl.tmp")
        try:
            with temporary.open("wb") as stream:
                pickle.dump(animals, stream, protocol=pickle.HIGHEST_PROTOCOL)
            temporary.replace(path)
        finally:
            if temporary.exists():
                temporary.unlink()
        sources.append(dict(group=group, path=str(path)))
        progress(f"Saved {path} | {len(animals)} animals")
    return groups, sources, warnings
