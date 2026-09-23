# -*- coding: utf-8 -*-
"""
Utilities to load and summarize mouse behavior sessions.
"""

from pathlib import Path
import pickle

import numpy as np
import pandas as pd
import sys

from tqdm import tqdm

import matplotlib
import matplotlib as mpl
import matplotlib.cm as cm
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import matplotlib.image as mpimg
import matplotlib.colors as mcolors
import matplotlib.mlab as mlab
import matplotlib.ticker as plticker

SOUND_ID_GO = 1
SOUND_ID_NOGO = 2

CODE_folder = str(Path(__file__).resolve().parent)
sys.path.append(CODE_folder)
import nwb_obj

def save_batch_dict(batch_dict: dict, save_path: Path) -> Path:
    save_path = Path(save_path)
    save_path.parent.mkdir(parents=True, exist_ok=True)
    with save_path.open("wb") as file:
        pickle.dump(batch_dict, file)
    print(f"Saved batch dict: {save_path}")
    return save_path

def load_batch_dict(save_path: Path) -> dict:
    save_path = Path(save_path)
    with save_path.open("rb") as file:
        batch_dict = pickle.load(file)
    print(f"Loaded batch dict: {save_path}")
    return batch_dict

def merge_dict_keys(data, keys_to_merge, new_key, remove_old=True):
    data = data.copy()
    merged_values = {}

    for key in keys_to_merge:
        merged_values.update(data[key])

    data[new_key] = merged_values

    if remove_old:
        for key in keys_to_merge:
            del data[key]

    return data

def read_params(params):
    """Parse a parameters table into a dict of lists."""
    allparams = {}

    for row in params.itertuples(index=False):
        current_key = None

        for cell in row:
            if pd.isna(cell):
                continue

            for token in str(cell).split():
                if "=" in token:
                    key, val = token.split("=", 1)
                    current_key = key
                    allparams.setdefault(key, []).append(val)
                elif current_key is not None:
                    allparams[current_key].append(token)

    return allparams


def extract_mouse_performance(base_folder, mouse_name):
    """
    Aggregate session performance for one mouse across all available sessions.

    Returns one row per valid session. Sessions with missing files or malformed
    content are skipped with a warning instead of aborting the full mouse load.
    """
    mouse_dir = Path(base_folder) / mouse_name

    if not mouse_dir.exists():
        raise FileNotFoundError(
            f"Dossier introuvable pour la souris '{mouse_name}' : {mouse_dir}"
        )

    allsessionsrows = []

    for date_dir in tqdm(sorted(mouse_dir.iterdir())):
        if not date_dir.is_dir():
            continue

        for datafolder_dir in sorted(date_dir.iterdir()):
            if not datafolder_dir.is_dir():
                continue

            date = date_dir.name
            datafolder = datafolder_dir.name

            try:
                session_datadict = load_session_data_fromFolder(datafolder_dir)
                parameters = read_params(session_datadict["parameters"])
                perfdict = extract_performance(session_datadict)
            except (FileNotFoundError, KeyError, ValueError) as exc:
                print(f"[Avertissement] Session ignorée {datafolder_dir}: {exc}")
                continue

            row_session_data = {
                "mouse": mouse_name,
                "date": date,
                "datafolder": datafolder,
                "ITI": [
                    int(parameters["ITI"][0]),
                    int(parameters["ITIrand"][0]),
                ],
                "TimeOut": [int(value) for value in parameters["PunishInterval"]],
                "n_trials": session_datadict["nTotalTrials"],
                "n_go": perfdict["n_go"],
                "n_nogo": perfdict["n_nogo"],
                "perf_go": perfdict["go"],
                "perf_nogo": perfdict["nogo"],
                "perf_total": perfdict["total"],
            }
            allsessionsrows.append(row_session_data)

    if not allsessionsrows:
        print(f"[Avertissement] Aucune session valide trouvée pour {mouse_name}.")
        return pd.DataFrame(
            columns=[
                "mouse",
                "date",
                "datafolder",
                "ITI",
                "TimeOut",
                "n_trials",
                "n_go",
                "n_nogo",
                "perf_go",
                "perf_nogo",
                "perf_total",
            ]
        )

    return pd.DataFrame(allsessionsrows).sort_values(
        by=["date", "datafolder"], ignore_index=True
    )


def load_mouse_performance(base_folder, mouse_name):
    """Backward-compatible alias for older callers."""
    return extract_mouse_performance(base_folder, mouse_name)


def load_session_data(session_data_folder):
    """Backward-compatible folder loader for older GUI versions."""
    return load_session_data_fromFolder(session_data_folder)


def load_session_data_fromFolder(session_data_folder):
    """
    Load the core data for one behavior session from its folder.

    Returns a dict containing the parameters table, raw signals, valid trial
    table, and simple session-level metadata.
    """
    folder = Path(session_data_folder)
    params_path = folder / "parameters.dat"
    ir_path = folder / "IRFork.bin"
    fallback_ir_path = folder / "Lick.bin"
    trialtype_path = folder / "TrialType.bin"
    sounds_path = folder / "TTLtrigsounds.bin"
    log_path = folder / "Trial_log.csv"

    for path in [params_path, trialtype_path, sounds_path, log_path]:
        if not path.exists():
            raise FileNotFoundError(f"Fichier manquant : {path}")

    chosen_ir_path = None
    if ir_path.exists():
        chosen_ir_path = ir_path
    elif fallback_ir_path.exists():
        chosen_ir_path = fallback_ir_path
       
    params_df = pd.read_csv(params_path)
    sound_signal = np.fromfile(sounds_path, dtype=np.float64)
    if chosen_ir_path is None:
        # Some experiments have no IR channel file. Keep pipeline alive with empty IR.
        data_ir = np.array([], dtype=np.float64)
    else:
        data_ir = np.fromfile(chosen_ir_path, dtype=np.float64)
    data_trial_id = np.fromfile(trialtype_path, dtype=np.float64)

    results_table = _load_results_table(log_path)

    return {
        "parameters": params_df,
        "dataIR": {
            "full": data_ir,
            "mean": float(np.mean(data_ir)) if data_ir.size else np.nan,
        },
        "trialID": {
            "full": data_trial_id,
            "types": np.unique(data_trial_id),
        },
        "sound_signal": sound_signal,
        "ResultsTable": results_table,
        "nTotalTrials": len(results_table),
    }

def load_session_data_fromFile(session_data_nwbFile):
    """
    Load the core data for one behavior session from file.

    Returns a dict containing the parameters table, raw signals, valid trial
    table, and simple session-level metadata.
    """
    if session_data_nwbFile.is_file() and session_data_nwbFile.suffix.lower() == ".nwb":
        nwbOjb = nwb_obj.session_data_nwb(nwbfile = session_data_nwbFile)
        
        nwbOjb.read_paths()
        nwbOjb.extract_continuous_signal() 
        nwbOjb.generate_results_table() 
        nwbOjb.get_parameters() 
        data_ir = nwbOjb.IR_signal
        return {
            "parameters": nwbOjb.parameters,
            "dataIR": {
                "full": data_ir,
                "mean": float(data_ir.mean()) if len(data_ir) > 0 else float("nan"),
            },
            "trialID": {
                "full": nwbOjb.trialtype,
                "types": sorted(set(nwbOjb.trialtype.tolist())),
            },
            "sound_signal": nwbOjb.sound_signal,
            "ResultsTable": nwbOjb.results_table,
            "nTotalTrials": len(nwbOjb.results_table),
        }
    

def _load_results_table(log_path):
    """Load the session trial log and keep only rows with a valid SoundId."""
    raw = pd.read_csv(log_path, sep=";")

    if len(raw.columns) == 1 and ";" in raw.columns[0]:
        split_df = raw.iloc[:, 0].str.split(";", expand=True)
        split_df.columns = raw.columns[0].split(";")
    else:
        split_df = raw.copy()

    if "SoundId" not in split_df.columns:
        raise ValueError(f"Colonne 'SoundId' absente dans {log_path}")

    sound_ids = pd.to_numeric(split_df["SoundId"], errors="coerce")
    gooddata = split_df.loc[sound_ids.notna()].reset_index(drop=True)

    return gooddata


def extract_performance(session_datadict):
    """
    Compute Go, NoGo, and total performance for one session.
    """
    data_r = session_datadict["ResultsTable"]
    if data_r.empty:
        raise ValueError("ResultsTable est vide, impossible de calculer les performances.")

    sound_ids = pd.to_numeric(data_r["SoundId"], errors="raise").astype(int)
    trial_type = None
    try:
        trial_type = pd.to_numeric(data_r["TrialType"], errors="raise").astype(int).to_numpy()
    except (KeyError, ValueError, TypeError):
        # Some sessions do not expose TrialType; rebuild from SoundId.
        username = ""
        params_obj = session_datadict.get("parameters", None)
        if isinstance(params_obj, pd.DataFrame) and not params_obj.empty:
            try:
                row = params_obj.iloc[0]
                username = str(row.index[0]).split("=")[-1]
            except Exception:
                username = ""
        elif isinstance(params_obj, dict):
            username = str(params_obj.get("User", ""))

        trial_type = np.zeros(session_datadict["nTotalTrials"], dtype=int)
        if username == "Eya":
            print("USERNAME:" + username)
            trial_type[sound_ids == 1] = 1
            trial_type[sound_ids == 16] = 2
        else:
            # Generic fallback: use SoundId as trial type.
            trial_type = sound_ids.to_numpy(dtype=int)

    # Persist normalized/computed trial type in-place without altering other columns.
    data_r["TrialType"] = trial_type
    
    hits = pd.to_numeric(data_r["Hit"], errors="raise").astype(int)
    crs = pd.to_numeric(data_r["CR"], errors="raise").astype(int)

    go_mask = trial_type == SOUND_ID_GO
    nogo_mask = trial_type == SOUND_ID_NOGO

    n_go = int(go_mask.sum())
    n_nogo = int(nogo_mask.sum())

    if n_go == 0:
        raise ValueError(f"Aucun essai Go (SoundId={SOUND_ID_GO}) trouvé dans ResultsTable.")

    perf_go = round((hits[go_mask].sum() / n_go) * 100, 2)

    if n_nogo == 0:
        perf_nogo = np.nan
        perf_total = perf_go
    else:
        perf_nogo = round((crs[nogo_mask].sum() / n_nogo) * 100, 2)
        perf_total = round((perf_go + perf_nogo) / 2, 2)

    return {
        "go": perf_go,
        "nogo": perf_nogo,
        "n_go": n_go,
        "n_nogo": n_nogo,
        "total": perf_total,
    }

def extract_hit_by_sound_IR(session_datadict, trial_ir_analysis):
    """
    Compute hit metrics independently for each SoundId present in ResultsTable.

    Returns a dict keyed by SoundId (int), each with:
    - n_trials
    - n_hits
    - hit_pct
    """
    data_r = session_datadict["ResultsTable"]
    if data_r.empty:
        return {}

    sound_ids = pd.to_numeric(data_r["SoundId"], errors="raise").astype(int)
    
    hit_by_sound = {}
    
    for sid in sorted(sound_ids.unique()):
        print(sid)
        sid_idxs = np.where(sound_ids == sid)[0]
        n_trials = len(sid_idxs)
        
        FAs = []
        allTrialsAsGO = []

        for itr,tr_idx in enumerate(sid_idxs):
            timespent = 0 
            try:
                fork_events = trial_ir_analysis['dict_data_IRxTrial'][tr_idx]['timespent_each_time']
                if len(fork_events)>0:
                    timespent = np.sum(fork_events)
                    if timespent >= 750:
                        FAs.append(1)
                        allTrialsAsGO.append(1)
                    else:
                        allTrialsAsGO.append(0)
            except KeyError:
                    pass
                
        n_FAs = len(FAs)
        FA_pct = float((n_FAs / n_trials) * 100.0) if n_trials > 0 else np.nan

        hit_by_sound[int(sid)] = {
                "n_trials": n_trials,
                "n_FAs": n_FAs,
                "FAs_pct": round(FA_pct, 2) if n_trials > 0 else np.nan,
                "allTrialsAsGO": allTrialsAsGO
            }
    return hit_by_sound

def extract_hit_by_sound_licks(session_datadict, trial_ir_analysis):
    """
    Compute hit metrics independently for each SoundId present in ResultsTable.

    Returns a dict keyed by SoundId (int), each with:
    - n_trials
    - n_hits
    - hit_pct
    """
    data_r = session_datadict["ResultsTable"]
    if data_r.empty:
        return {}

    sound_ids = pd.to_numeric(data_r["SoundId"], errors="raise").astype(int)
    
    hit_by_sound = {}
    for sid in sorted(sound_ids.unique()):
        sid_idxs = np.where(sound_ids == sid)[0]
        n_trials = len(sid_idxs)
        
        FAs = []
        allTrialsAsGO = []
        for itr,tr_idx in enumerate(sid_idxs):
            n_licks = 0
            try:
                licks_events = trial_ir_analysis['dict_data_IRxTrial'][tr_idx]['forks_timestamps']
                n_licks = len(licks_events)
                if n_licks >= 5:
                    FAs.append(1)
                    allTrialsAsGO.append(1)
                else:
                    allTrialsAsGO.append(0)
            except KeyError:
                pass
        
        n_FAs = len(FAs)
        FA_pct = float((n_FAs / n_trials) * 100.0) if n_trials > 0 else np.nan

        hit_by_sound[int(sid)] = {
                "n_trials": n_trials,
                "n_FAs": n_FAs,
                "FAs_pct": round(FA_pct, 2) if n_trials > 0 else np.nan,
                "allTrialsAsGO": allTrialsAsGO
            }

    return hit_by_sound


def detect_ir_events(data_ir, rise_threshold=0.5, fall_threshold=-1.0):
    """Detect IR beam-break events from derivative threshold crossings."""
    data_ir = np.asarray(data_ir)
    y_diff = np.diff(data_ir)
    indice_debut = np.where(y_diff > rise_threshold)[0]

    if indice_debut.size == 0:
        return {
            "Y": y_diff,
            "debut_fork": np.array([], dtype=int),
            "debut_nontaken": np.array([], dtype=int),
            "end_fork": np.array([], dtype=int),
            "timespent_each_fork_event": np.array([], dtype=int),
        }

    is_new_event = np.r_[True, np.diff(indice_debut) != 1]
    debut_fork = indice_debut[is_new_event]
    debut_nontaken = indice_debut[~is_new_event]

    end_fork = []
    valid_debut = []
    for start_idx in debut_fork:
        rel_end = np.where(y_diff[start_idx:] < fall_threshold)[0]
        if rel_end.size == 0:
            continue
        end_idx = int(rel_end[0] + start_idx)
        end_fork.append(end_idx)
        valid_debut.append(int(start_idx))

    debut_fork = np.array(valid_debut, dtype=int)
    end_fork = np.array(end_fork, dtype=int)
    timespent_each_fork_event = end_fork - debut_fork

    if not (
        len(debut_fork) == len(end_fork) == len(timespent_each_fork_event)
    ):
        raise ValueError("IR event detection mismatch between starts, ends, and durations.")

    return {
        "Y": y_diff,
        "debut_fork": debut_fork,
        "debut_nontaken": np.asarray(debut_nontaken, dtype=int),
        "end_fork": end_fork,
        "timespent_each_fork_event": timespent_each_fork_event,
    }


def analyze_ir_by_trial(
    data_session_dict,
    ir_events,
    rw_fix=1.0,
    trial_bin_s=0.1,
    fe=1000,
    timereward_ms=1000,
    pre_rw_entry_tolerance_ms=150,
    occupancy_mode="reward_window",
):
    """
    Build a trial x time IR occupancy map.

    occupancy_mode="reward_window" keeps the historical 2-second window aligned
    to reward-window start. occupancy_mode="full_trial" uses each trial's full
    start/stop interval and pads shorter trials to the longest trial duration.
    """
    data_trial_id = np.asarray(data_session_dict["trialID"]["full"])
    data_ir = np.asarray(data_session_dict["dataIR"]["full"])
    mean_ir_val = float(data_session_dict["dataIR"]["mean"])
    debut_fork = np.asarray(ir_events["debut_fork"], dtype=int)
    end_fork = np.asarray(ir_events["end_fork"], dtype=int)
    timespent_each_fork_event = np.asarray(ir_events["timespent_each_fork_event"], dtype=int)

    total_trials = int(data_session_dict["nTotalTrials"])
    dict_data_ir_x_trial = {}
    occupancy_mode = str(occupancy_mode).lower()
    if occupancy_mode not in {"reward_window", "full_trial"}:
        raise ValueError("occupancy_mode must be 'reward_window' or 'full_trial'.")

    if occupancy_mode == "full_trial":
        results_table = data_session_dict.get("ResultsTable")
        trial_bounds = []
        if (
            results_table is not None
            and {"StartTime", "StopTime"}.issubset(results_table.columns)
        ):
            start_times = pd.to_numeric(results_table["StartTime"], errors="coerce").to_numpy()
            stop_times = pd.to_numeric(results_table["StopTime"], errors="coerce").to_numpy()
            for row_idx, (start_s, stop_s) in enumerate(zip(start_times, stop_times)):
                if not (np.isfinite(start_s) and np.isfinite(stop_s)):
                    continue
                trial_start = int(round(float(start_s) * fe))
                trial_end = int(round(float(stop_s) * fe))
                if trial_end > trial_start:
                    trial_bounds.append((row_idx, trial_start, trial_end))
        else:
            indxs_with_val99 = np.where(data_trial_id == 99)[0]
            if len(indxs_with_val99) > 1:
                tps_trial = np.arange(
                    trial_bin_s,
                    len(data_trial_id) * trial_bin_s + trial_bin_s,
                    trial_bin_s,
                )
                rw_samples = (tps_trial[indxs_with_val99] * fe).astype(int)
                for row_idx in range(min(total_trials, len(rw_samples) - 1)):
                    trial_start = int(rw_samples[row_idx])
                    trial_end = int(rw_samples[row_idx + 1])
                    if trial_end > trial_start:
                        trial_bounds.append((row_idx, trial_start, trial_end))

        if not trial_bounds:
            viz_visits = np.full((max(total_trials, 1), 1), np.nan, dtype=float)
            return {
                "dict_data_IRxTrial": dict_data_ir_x_trial,
                "viz_visits": viz_visits,
                "n_analyzed_trials": 0,
                "pct_above_750ms": 0.0,
                "occupancy_mode": occupancy_mode,
                "occupancy_x_label": "Time from trial start (samples)",
                "occupancy_title": "IR occupancy across full trial",
            }

        max_trial_duration = max(trial_end - trial_start for _, trial_start, trial_end in trial_bounds)
        viz_visits = np.full((max(total_trials, 1), max_trial_duration), np.nan, dtype=float)

        for row_idx, trial_start, trial_end in trial_bounds:
            trial_start = max(0, min(int(trial_start), len(data_ir) - 1))
            trial_end = max(trial_start + 1, min(int(trial_end), len(data_ir)))
            trial_duration = trial_end - trial_start
            viz_visits[row_idx, :trial_duration] = 0

            forkdata = (debut_fork < trial_end) & (end_fork > trial_start)
            trial_debuts = debut_fork[forkdata]
            trial_ends = end_fork[forkdata]
            clipped_starts = np.maximum(trial_debuts, trial_start)
            clipped_ends = np.minimum(trial_ends, trial_end)
            trial_times = clipped_ends - clipped_starts

            dict_data_ir_x_trial[row_idx] = {
                "TrialStart": trial_start,
                "TrialEnd": trial_end,
                "forks_timestamps": trial_debuts,
                "timespent_each_time": trial_times,
            }

            for event_start, event_end in zip(clipped_starts, clipped_ends):
                start_idx = int(event_start - trial_start)
                end_idx = int(event_end - trial_start)
                if end_idx > start_idx:
                    viz_visits[row_idx, start_idx:end_idx] = 1

        return {
            "dict_data_IRxTrial": dict_data_ir_x_trial,
            "viz_visits": viz_visits,
            "n_analyzed_trials": len(dict_data_ir_x_trial),
            "pct_above_750ms": 0.0,
            "occupancy_mode": occupancy_mode,
            "occupancy_x_label": "Time from trial start (samples)",
            "occupancy_title": "IR occupancy across full trial",
        }

    viz_visits = np.zeros((max(total_trials, 1), 2000), dtype=np.uint8)

    indxs_with_val99 = np.where(data_trial_id == 99)[0]
    if len(indxs_with_val99) == 0 or total_trials <= 2:
        return {
            "dict_data_IRxTrial": dict_data_ir_x_trial,
            "viz_visits": viz_visits,
            "n_analyzed_trials": 0,
            "pct_above_750ms": 0.0,
            "occupancy_mode": occupancy_mode,
            "occupancy_x_label": "Time (samples; 1000 = RW start)",
            "occupancy_title": "IR occupancy aligned to reward window",
        }

    # I am passing here from full acq rate 
    tps_trial = np.arange(trial_bin_s, len(data_trial_id) * trial_bin_s + trial_bin_s, trial_bin_s)
    temps_debut = tps_trial[indxs_with_val99]
    debut_rw = temps_debut.copy()
    fin_rw = temps_debut + rw_fix

    n_iter = min(total_trials, len(debut_rw))

    for j in range(1, n_iter - 1):
        early_enter = False
        t_start_rw = int(debut_rw[j] * fe)
        t_end_rw = int(fin_rw[j] * fe)
        if t_start_rw >= len(data_ir):
            continue
        t_end_rw = min(t_end_rw, len(data_ir) - 1)

        time_to_sound = 0
        early_outdebut = t_start_rw

        if data_ir[t_start_rw] > mean_ir_val:
            prior_entries = np.where(debut_fork < t_start_rw)[0]
            if len(prior_entries) > 0:
                indx_last = prior_entries[-1]
                time_to_sound = int(t_start_rw - debut_fork[indx_last])
                early_outdebut = int(end_fork[indx_last])
                early_enter = True

        valid_entry_start = t_start_rw - int(pre_rw_entry_tolerance_ms)
        forkdata = (debut_fork >= valid_entry_start) & (debut_fork <= t_end_rw)
        trial_debuts = debut_fork[forkdata]
        trial_times = timespent_each_fork_event[forkdata]

        dict_data_ir_x_trial[j] = {
            "DebutRW": t_start_rw,
            "FinRW": t_end_rw,
            "forks_timestamps": trial_debuts,
            "timespent_each_time": trial_times,
        }

        if len(trial_debuts) > 0:
            for tt, timespent in zip(trial_debuts, trial_times):
                timevisit = int(tt - t_start_rw)
                timevisit_tmp = int(timevisit + 1000)
                if timevisit_tmp >= viz_visits.shape[1]:
                    continue

                if timevisit + timespent > timereward_ms:
                    duration = max(int(timereward_ms - timevisit), 0)
                else:
                    duration = int(timespent)

                if duration <= 0:
                    continue

                end_idx = min(timevisit_tmp + duration, viz_visits.shape[1])
                viz_visits[j, max(timevisit_tmp, 0):end_idx] = 1

        if early_enter:
            if time_to_sound > 1000:
                time_to_sound = 1000
            start_for_arr = int(1000 - time_to_sound)
            if (early_outdebut - t_start_rw) > timereward_ms:
                end_for_arr = viz_visits.shape[1]
            else:
                end_for_arr = int((early_outdebut - t_start_rw) + 1000)

            start_for_arr = max(0, start_for_arr)
            end_for_arr = min(viz_visits.shape[1], end_for_arr)
            if end_for_arr > start_for_arr:
                viz_visits[j, start_for_arr:end_for_arr] = 1

    analyzed_rows = list(dict_data_ir_x_trial.keys())
    if len(analyzed_rows) == 0:
        pct_above_750ms = 0.0
    else:
        reward_col = 1000 + 750
        if reward_col >= viz_visits.shape[1]:
            reward_col = viz_visits.shape[1] - 1
        pct_above_750ms = float(np.mean(viz_visits[analyzed_rows, reward_col]) * 100.0)

    return {
        "dict_data_IRxTrial": dict_data_ir_x_trial,
        "viz_visits": viz_visits,
        "n_analyzed_trials": len(analyzed_rows),
        "pct_above_750ms": pct_above_750ms,
        "occupancy_mode": occupancy_mode,
        "occupancy_x_label": "Time (samples; 1000 = RW start)",
        "occupancy_title": "IR occupancy aligned to reward window",
    }


def find_nwb_files_for_animal(nwb_root: Path | str, animal_name: str) -> list[Path]:
    """
    Recursively find NWB files whose filename or parent path contains animal_name.
    """
    nwb_root = Path(nwb_root)
    animal_l = str(animal_name or "").strip().lower()
    return sorted(
        [
            p for p in nwb_root.rglob("*.nwb")
            if not animal_l
            or animal_l in p.name.lower()
            or animal_l in str(p.parent).lower()
        ]
    )


def _get_hit_by_sound_func(hit_source: str):
    if hit_source == "Licks":
        return extract_hit_by_sound_licks
    return extract_hit_by_sound_IR


def _get_session_date(data_session_dict: dict, source_path: Path) -> str:
    parameters = data_session_dict.get("parameters", {})
    if isinstance(parameters, dict):
        return str(parameters.get("date", source_path.stem))
    if hasattr(parameters, "columns") and "date" in parameters.columns:
        try:
            return str(parameters["date"].iloc[0])
        except Exception:
            pass
    if source_path.parent.name:
        return source_path.parent.name
    try:
        return str(parameters["date"])
    except Exception:
        return source_path.stem


def merge_hit_by_sound(
    batch_hit_by_sound: dict[int, dict],
    single_hit_by_sound: dict,
) -> None:
    for sound_id, stats in single_hit_by_sound.items():
        sound_id = int(sound_id)
        current = batch_hit_by_sound.setdefault(
            sound_id,
            {
                "n_trials": 0,
                "n_FAs": 0,
                "FAs_pct": 0.0,
            },
        )
        current["n_trials"] += int(stats.get("n_trials", 0))
        current["n_FAs"] += int(stats.get("n_FAs", 0))

    for stats in batch_hit_by_sound.values():
        n_trials = stats["n_trials"]
        if n_trials > 0:
            stats["FAs_pct"] = round((stats["n_FAs"] / n_trials) * 100.0, 2)


def append_trials_by_sound_id(
    trials_by_sound_id: dict[int, list[dict]],
    data_session_dict: dict,
    source_path: Path,
) -> None:
    results_table = data_session_dict.get("ResultsTable")
    if results_table is None or results_table.empty:
        return

    session_date = _get_session_date(data_session_dict, source_path)
    for trial_index, row in results_table.iterrows():
        try:
            sound_id = int(row["SoundId"])
        except (KeyError, TypeError, ValueError):
            continue

        trials_by_sound_id.setdefault(sound_id, []).append(
            {
                "session_date": session_date,
                "nwb_file": source_path.name,
                "nwb_path": str(source_path),
                "trial_index": int(trial_index),
                "trial": row.to_dict(),
            }
        )


def process_batch_session(
    source_path: Path,
    data_session_dict: dict,
    hit_by_sound_func,
    trials_by_sound_id: dict[int, list[dict]],
    batch_hit_by_sound: dict[int, dict],
) -> tuple[dict, dict]:
    single_session_performance = extract_performance(data_session_dict)
    ir_events = detect_ir_events(data_session_dict["dataIR"]["full"])
    trial_ir_analysis = analyze_ir_by_trial(data_session_dict, ir_events)
    single_hit_by_sound = hit_by_sound_func(
        data_session_dict,
        trial_ir_analysis,
    )
    append_trials_by_sound_id(
        trials_by_sound_id,
        data_session_dict,
        source_path,
    )
    merge_hit_by_sound(batch_hit_by_sound, single_hit_by_sound)
    return single_session_performance, single_hit_by_sound


def run_nwb_batch_analysis(
    nwb_root: Path | str,
    animal_name: str,
    hit_source: str = "IR",
    continue_on_error: bool = True,
    verbose: bool = True,
) -> dict:
    """
    Shared NWB batch engine used by GUI/CLI wrappers.

    Returns a JSON-ready-shaped payload except for numpy/pandas scalar values,
    which callers can normalize before writing.
    """
    nwb_root = Path(nwb_root)
    if not nwb_root.exists() or not nwb_root.is_dir():
        raise FileNotFoundError(f"Invalid NWB root folder: {nwb_root}")

    animal_name = str(animal_name or "").strip()
    if not animal_name:
        raise ValueError("Animal name is required for NWB batch mode.")

    matching_files = find_nwb_files_for_animal(nwb_root, animal_name)
    if not matching_files:
        raise FileNotFoundError(
            f"No .nwb files found for animal '{animal_name}' under {nwb_root}"
        )

    performance_by_file: dict[str, dict] = {}
    trials_by_sound_id: dict[int, list[dict]] = {}
    batch_hit_by_sound: dict[int, dict] = {}
    hit_by_sound_func = _get_hit_by_sound_func(hit_source)

    for idx, nwb_path in enumerate(matching_files):
        if verbose:
            print(idx, nwb_path)

        session_payload = {"data": [], "params": []}
        try:
            data_session_dict = load_session_data_fromFile(nwb_path)
            single_session_performance, single_hit_by_sound = process_batch_session(
                nwb_path,
                data_session_dict,
                hit_by_sound_func,
                trials_by_sound_id,
                batch_hit_by_sound,
            )
            datestring = _get_session_date(data_session_dict, nwb_path)
            session_payload["params"] = data_session_dict["parameters"]
            session_payload["data"] = single_session_performance
            session_payload["hit_by_sound"] = single_hit_by_sound

            unique_key = datestring
            suffix_idx = 2
            while unique_key in performance_by_file:
                unique_key = f"{datestring}_{suffix_idx}"
                suffix_idx += 1
            performance_by_file[unique_key] = session_payload

            if verbose:
                print(f"OK: {nwb_path.name}")
        except Exception as exc:
            if not continue_on_error:
                raise
            performance_by_file[str(nwb_path)] = {"error": str(exc)}
            if verbose:
                print(f"ERROR: {nwb_path.name} -> {exc}")

    return {
        "animal_name": animal_name,
        "nwb_root": str(nwb_root),
        "n_files": len(matching_files),
        "hit_source": hit_source,
        "performance_by_file": performance_by_file,
        "hit_by_sound": batch_hit_by_sound,
        "trials_by_sound_id": trials_by_sound_id,
        "matching_files": matching_files,
    }


def batch_ir_go_by_sound_from_nwb(
    animal_id: str,
    protocol: str,
    from_server: bool = True,
    data_basil_server: str = "Y:/User_folders/Sebastian/behavior_data/",
    data_basil: str = "Y:/Bathellierlab_gaia/BASIL/BASIL_FAIR/BASILapp/NWB/",
    nwb_root: Path | str | None = None,
    go_threshold_ms: int = 750,
    save_folder: Path | str | None = None,
    save_filename: str | None = None,
) -> dict:
    """
    Batch-load NWB sessions for one animal and compute IR-based trial outcomes.

    Returns a dict keyed by session date. Each session contains:
    - full: extract_hit_by_sound_IR output
    - alldataGO: one value per trial, 1 for correct IR-based outcome
    - alldatatime: summed IR time per trial
    - alldatatypes: TrialType values from ResultsTable
    """
    if nwb_root is None:
        data_folder = data_basil_server if from_server else data_basil
        nwb_root = Path(data_folder + '/' + animal_id + '/' + protocol)
    else:
        nwb_root = Path(nwb_root)

    print("searching", nwb_root)
    matching_files = find_nwb_files_for_animal(nwb_root, animal_id)

    batch_hit_by_sound = {}
    for nwb_path in matching_files:
        data_session_dict = load_session_data_fromFile(nwb_path)
        datestring = str(data_session_dict["parameters"]["date"])
        print(nwb_path,datestring)

        session_key = datestring
        suffix_idx = 2
        while session_key in batch_hit_by_sound:
            session_key = f"{datestring}_{suffix_idx}"
            suffix_idx += 1

        batch_hit_by_sound[session_key] = {"full": []}

        ir_events = detect_ir_events(data_session_dict["dataIR"]["full"])
        trial_ir_analysis = analyze_ir_by_trial(data_session_dict, ir_events)

        results_table = data_session_dict["ResultsTable"]
        n_trials = len(results_table["TrialType"])
        all_data_time = np.zeros(n_trials)
        all_data_go = np.zeros(n_trials)
        all_data_types = np.array(results_table["TrialType"])

        for trial_type in [1, 2]:
            data_mask = results_table["TrialType"] == trial_type
            trial_idxs = np.array(results_table["TrialsId"][data_mask])
            for trial_idx in trial_idxs:
                trial_idx = int(trial_idx)
                if trial_idx < 0 or trial_idx >= n_trials:
                    continue
                try:
                    timespent_each_time = trial_ir_analysis["dict_data_IRxTrial"][trial_idx]["timespent_each_time"]
                    if len(timespent_each_time) > 0:
                        all_time = np.sum(timespent_each_time)
                        all_data_time[trial_idx] = int(all_time)
                        if (trial_type == 1) and (all_time >= go_threshold_ms):
                            all_data_go[trial_idx] = 1
                        elif (trial_type == 2) and (all_time < go_threshold_ms):
                            all_data_go[trial_idx] = 1
                except KeyError:
                    pass

        single_hit_by_sound = extract_hit_by_sound_IR(data_session_dict, trial_ir_analysis)
        batch_hit_by_sound[session_key]["full"] = single_hit_by_sound
        batch_hit_by_sound[session_key]["alldataGO"] = all_data_go
        batch_hit_by_sound[session_key]["alldatatime"] = all_data_time
        batch_hit_by_sound[session_key]["alldatatypes"] = all_data_types

    if save_folder is not None:
        save_folder = Path(save_folder)
        save_folder.mkdir(parents=True, exist_ok=True)
        if save_filename is None:
            safe_protocol = "".join(char if char.isalnum() else "_" for char in protocol).strip("_")
            safe_animal = "".join(char if char.isalnum() else "_" for char in str(animal_id)).strip("_")
            save_filename = f"{safe_animal}_{safe_protocol}_batch_ir_go_by_sound.pkl"
        save_path = save_folder / save_filename
        with save_path.open("wb") as file:
            pickle.dump(batch_hit_by_sound, file)
        print(f"Saved batch IR GO by sound: {save_path}")

    return batch_hit_by_sound


def _is_session_folder(folder: Path) -> bool:
    required_files = [
        "parameters.dat",
        "TrialType.bin",
        "TTLtrigsounds.bin",
        "Trial_log.csv",
    ]
    return all((folder / filename).exists() for filename in required_files)


def find_session_folders_for_animal(folder_root: Path | str, animal_name: str = "",  protocol_name: Path | str | None = None) -> list[Path]:
    """
    Find raw behavior session folders below a root folder.

    A session folder is detected by the presence of Trial_log.csv plus the other
    required raw behavior files.
    """
    if protocol_name is not None:
        folder_root = Path(folder_root + '/' +  animal_name + '/' + protocol_name)
    else:
        folder_root = Path(folder_root)
    print(folder_root)

    animal_l = (animal_name or "").strip().lower()
    session_folders = []
    candidate_folders = [folder_root] if _is_session_folder(folder_root) else []
    candidate_folders.extend(path.parent for path in folder_root.rglob("Trial_log.csv"))

    seen = set()
    for folder in candidate_folders:
        if folder in seen:
            continue
        seen.add(folder)
        if not _is_session_folder(folder):
            continue
        if animal_l and animal_l not in str(folder).lower():
            continue
        session_folders.append(folder)
    return sorted(session_folders)


def _trial_type_from_results_table(data_session_dict: dict) -> np.ndarray:
    data_r = data_session_dict["ResultsTable"]
    sound_ids = pd.to_numeric(data_r["SoundId"], errors="raise").astype(int)
    try:
        trial_type = pd.to_numeric(data_r["TrialType"], errors="raise").astype(int).to_numpy()
    except (KeyError, ValueError, TypeError):
        username = ""
        params_obj = data_session_dict.get("parameters", None)
        if isinstance(params_obj, pd.DataFrame) and not params_obj.empty:
            try:
                row = params_obj.iloc[0]
                username = str(row.index[0]).split("=")[-1]
            except Exception:
                username = ""
        elif isinstance(params_obj, dict):
            username = str(params_obj.get("User", ""))

        trial_type = np.zeros(data_session_dict["nTotalTrials"], dtype=int)
        if username == "Eya":
            trial_type[sound_ids == 1] = 1
            trial_type[sound_ids == 16] = 2
        else:
            trial_type = sound_ids.to_numpy(dtype=int)
    return trial_type


def batch_lick_go_by_sound_from_folders(
    animal_id: str,
    protocol: str = "Eya_HfGoNoGo",
    from_server: bool = True,
    data_basil_server: str = "Y:/User_folders/Sebastian/behavior_data/",
    data_basil_github: str = "C:/Users/seceball/Documents/GitHub/pyBASIL/data/",
    folder_root: Path | str | None = None,
    lick_threshold: int = 5,
    save_folder: Path | str | None = None,
    save_filename: str | None = None,
) -> dict:
    """
    Batch-load raw behavior folders and compute lick-count based Go/NoGo outcomes.

    Returns a dict keyed by session date/folder. Each session contains:
    - full: extract_hit_by_sound_licks output
    - alldataGO: one value per trial, 1 for correct lick-based outcome, 0 for incorrect, NaN if missing
    - alldatatime: number of licks/events per trial
    - alldatatypes: TrialType values, with Eya fallback SoundId 1->Go and 16->NoGo
    """
    
    if folder_root is None:
        folder_root = data_basil_server if from_server else data_basil_github
 
    matching_folders = find_session_folders_for_animal(folder_root = folder_root,                                                       
                                                       animal_name= animal_id,
                                                       protocol_name = protocol)
    if not matching_folders:
        raise FileNotFoundError(
            f"No session folders found for animal '{animal_id}' under {folder_root}"
        )

    batch_hit_by_sound = {}
    for folder in matching_folders:
        data_session_dict = load_session_data_fromFolder(folder)
        datestring = folder.parent.name
        session_key = datestring
        suffix_idx = 2
        while session_key in batch_hit_by_sound:
            session_key = f"{datestring}_{suffix_idx}"
            suffix_idx += 1

        batch_hit_by_sound[session_key] = {"full": []}

        ir_events = detect_ir_events(data_session_dict["dataIR"]["full"])
        trial_ir_analysis = analyze_ir_by_trial(data_session_dict, ir_events)

        data_r = data_session_dict["ResultsTable"]
        n_trials = len(data_r)
        trial_type = _trial_type_from_results_table(data_session_dict)
        data_r["TrialType"] = trial_type

        all_data_time = np.zeros(n_trials)
        all_data_go = np.zeros(n_trials) * np.nan
        all_data_types = trial_type

        for ttype in [1, 2]:
            data_mask = trial_type == ttype
            trial_idxs = np.array(data_r["TrialsId"][data_mask])
            for trial_idx in trial_idxs:
                trial_idx = int(trial_idx) - 1
                if trial_idx < 0 or trial_idx >= n_trials:
                    continue
                try:
                    all_licks = trial_ir_analysis["dict_data_IRxTrial"][trial_idx]["forks_timestamps"]
                    n_licks = len(all_licks)
                    all_data_time[trial_idx] = n_licks

                    if (ttype == 1) and (n_licks >= lick_threshold):
                        all_data_go[trial_idx] = 1
                    elif (ttype == 1) and (n_licks < lick_threshold):
                        all_data_go[trial_idx] = 0
                    elif (ttype == 2) and (n_licks < lick_threshold):
                        all_data_go[trial_idx] = 1
                    elif (ttype == 2) and (n_licks >= lick_threshold):
                        all_data_go[trial_idx] = 0
                except KeyError:
                    pass

        single_hit_by_sound = extract_hit_by_sound_licks(data_session_dict, trial_ir_analysis)
        batch_hit_by_sound[session_key]["full"] = single_hit_by_sound
        batch_hit_by_sound[session_key]["alldataGO"] = all_data_go
        batch_hit_by_sound[session_key]["alldatatime"] = all_data_time
        batch_hit_by_sound[session_key]["alldatatypes"] = all_data_types

    if save_folder is not None:
        save_folder = Path(save_folder)
        save_folder.mkdir(parents=True, exist_ok=True)
        if save_filename is None:
            safe_protocol = "".join(char if char.isalnum() else "_" for char in protocol).strip("_")
            safe_animal = "".join(char if char.isalnum() else "_" for char in str(animal_id)).strip("_")
            save_filename = f"{safe_protocol}__{safe_animal}_for_learningcuves.pkl"
        save_path = save_folder / save_filename
        with save_path.open("wb") as file:
            pickle.dump(batch_hit_by_sound, file)
        print(f"Saved batch lick GO by sound: {save_path}")

    return batch_hit_by_sound

def batch_ir_go_by_sound_from_folders_freelymoving(
    animal_id: str,
    protocol: str = "Antonin_optoled_gonogo",
    from_server: bool = True,
    data_basil_server: str = "Y:/User_folders/Sebastian/behavior_data/",
    data_basil_github: str = "C:/Users/seceball/Documents/GitHub/pyBASIL/data/",
    folder_root: Path | str | None = None,
    go_threshold_ms: int = 750,
    save_folder: Path | str | None = None,
    save_filename: str | None = None,
) -> dict:
    """
    Batch-load raw behavior folders and compute beam crossings based Go/NoGo outcomes.

    Returns a dict keyed by session date/folder. Each session contains:
    - full: extract_hit_by_sound_licks output
    - alldataGO: one value per trial, 1 for correct outcome, 0 for incorrect, NaN if missing
    - alldatatime: number of crossing events per trial
    - alldatatypes: TrialType values, with Eya fallback SoundId 1->Go and 16->NoGo
    """
    if folder_root is None:
        folder_root = data_basil_server if from_server else data_basil_github
 

    matching_folders = find_session_folders_for_animal(folder_root,                                                       
                                                       animal_id,
                                                       protocol_name = protocol)
    if not matching_folders:
        raise FileNotFoundError(
            f"No session folders found for animal '{animal_id}' under {folder_root}"
        )

    batch_hit_by_sound = {}
    for folder in matching_folders:
        data_session_dict = load_session_data_fromFolder(folder)
        datestring = folder.parent.name
        session_key = datestring
        suffix_idx = 2
        while session_key in batch_hit_by_sound:
            session_key = f"{datestring}_{suffix_idx}"
            suffix_idx += 1

        batch_hit_by_sound[session_key] = {"full": []}

        ir_events = detect_ir_events(data_session_dict["dataIR"]["full"])
        trial_ir_analysis = analyze_ir_by_trial(data_session_dict, ir_events)

        data_r = data_session_dict["ResultsTable"]
        n_trials = len(data_r)
        trial_type = _trial_type_from_results_table(data_session_dict)
        data_r["TrialType"] = trial_type

        all_data_time = np.zeros(n_trials)
        all_data_go = np.zeros(n_trials) 
        all_data_types = trial_type

        for ttype in [1, 2]:
            data_mask = trial_type == ttype
            trial_idxs = np.array(data_r["TrialsId"][data_mask])
            for trial_idx in trial_idxs:
                trial_idx = int(trial_idx) - 1
                if trial_idx < 0 or trial_idx >= n_trials:
                    continue
                try:
                    timespent_each_time = trial_ir_analysis["dict_data_IRxTrial"][trial_idx]["timespent_each_time"]
                    if len(timespent_each_time) > 0:
                        all_time = np.sum(timespent_each_time)
                        all_data_time[trial_idx] = int(all_time)
                        if (ttype == 1) and (all_time >= go_threshold_ms):
                            all_data_go[trial_idx] = 1
                        elif (ttype == 2) and (all_time < go_threshold_ms):
                            all_data_go[trial_idx] = 1
                except KeyError:
                    pass

        single_hit_by_sound = extract_hit_by_sound_IR(data_session_dict, trial_ir_analysis)
        batch_hit_by_sound[session_key]["full"] = single_hit_by_sound
        batch_hit_by_sound[session_key]["alldataGO"] = all_data_go
        batch_hit_by_sound[session_key]["alldatatime"] = all_data_time
        batch_hit_by_sound[session_key]["alldatatypes"] = all_data_types

    if save_folder is not None:
        save_folder = Path(save_folder)
        save_folder.mkdir(parents=True, exist_ok=True)
        if save_filename is None:
            safe_protocol = "".join(char if char.isalnum() else "_" for char in protocol).strip("_")
            safe_animal = "".join(char if char.isalnum() else "_" for char in str(animal_id)).strip("_")
            save_filename = f"{safe_protocol}__{safe_animal}_for_learningcuves.pkl"
        save_path = save_folder / save_filename
        with save_path.open("wb") as file:
            pickle.dump(batch_hit_by_sound, file)
        print(f"Saved batch lick GO by sound: {save_path}")

    return batch_hit_by_sound


def load_batch_ir_go_by_sound_files(paths) -> dict:
    """
    Load one or more pickle files saved by batch_ir_go_by_sound_from_nwb().

    Parameters
    ----------
    paths:
        One .pkl path, one folder containing .pkl files, or a list/tuple of .pkl
        paths.

    Returns
    -------
    dict
        Dict keyed by file stem, each value containing one loaded batch dict.
    """
    if isinstance(paths, (str, Path)):
        path = Path(paths)
        if path.is_dir():
            pkl_paths = sorted(path.glob("*.pkl"))
        else:
            pkl_paths = [path]
    else:
        pkl_paths = [Path(path) for path in paths]

    if not pkl_paths:
        raise FileNotFoundError("No pickle files found.")

    loaded_batches = {}
    for pkl_path in pkl_paths:
        if not pkl_path.exists():
            raise FileNotFoundError(f"Pickle file not found: {pkl_path}")
        with pkl_path.open("rb") as file:
            loaded_batches[pkl_path.stem] = pickle.load(file)

    return loaded_batches


def load_extended_batch_ir_go_by_sound_files(protocol_paths_by_animal, labels=None) -> dict:
    """
    Load and concatenate learning-curve pickle files across protocols.

    Parameters
    ----------
    protocol_paths_by_animal:
        Either a dict mapping animal labels to ordered pickle paths, or a
        list/tuple where each item is the ordered pickle paths for one animal.
        The order of paths is the order used in the final learning curve.
    labels:
        Animal labels when protocol_paths_by_animal is a list/tuple.

    Returns
    -------
    dict
        Dict keyed by animal label, each value containing one concatenated
        batch dict suitable for plot_batch_go_performance_with_threshold_subplot().
    """
    if isinstance(protocol_paths_by_animal, dict):
        animal_items = list(protocol_paths_by_animal.items())
    else:
        animal_path_groups = list(protocol_paths_by_animal)
        if labels is None:
            labels = [f"animal_{idx + 1}" for idx in range(len(animal_path_groups))]
        if isinstance(labels, str):
            labels = [labels]
        labels = list(labels)
        if len(labels) != len(animal_path_groups):
            raise ValueError("labels must have the same length as protocol_paths_by_animal.")
        animal_items = list(zip(labels, animal_path_groups))

    extended_batches = {}
    for animal_label, protocol_paths in animal_items:
        if isinstance(protocol_paths, (str, Path)):
            protocol_paths = [protocol_paths]

        combined_batch = {}
        for protocol_idx, protocol_path in enumerate(protocol_paths, start=1):
            protocol_path = Path(protocol_path)
            loaded_protocol = load_batch_ir_go_by_sound_files(protocol_path)
            protocol_name, protocol_batch = next(iter(loaded_protocol.items()))
            for session_key in sorted(protocol_batch.keys()):
                combined_key = f"p{protocol_idx:02d}_{protocol_name}_{session_key}"
                combined_batch[combined_key] = protocol_batch[session_key]

        extended_batches[str(animal_label)] = combined_batch

    return extended_batches


def _normalize_batch_go_inputs(batch_hit_by_sound, labels=None):
    if (
        isinstance(batch_hit_by_sound, (list, tuple))
        and len(batch_hit_by_sound) == 1
        and isinstance(batch_hit_by_sound[0], dict)
        and not any(
            isinstance(value, dict) and "alldataGO" in value
            for value in batch_hit_by_sound[0].values()
        )
    ):
        batch_hit_by_sound = batch_hit_by_sound[0]

    is_loaded_batches = (
        isinstance(batch_hit_by_sound, dict)
        and len(batch_hit_by_sound) > 0
        and not any(
            isinstance(value, dict) and "alldataGO" in value
            for value in batch_hit_by_sound.values()
        )
        and all(isinstance(value, dict) for value in batch_hit_by_sound.values())
    )

    if is_loaded_batches:
        batch_dicts = list(batch_hit_by_sound.values())
        loaded_labels = list(batch_hit_by_sound.keys())
    elif isinstance(batch_hit_by_sound, (list, tuple)):
        batch_dicts = list(batch_hit_by_sound)
        loaded_labels = None
    else:
        batch_dicts = [batch_hit_by_sound]
        loaded_labels = None

    if labels is None:
        labels = loaded_labels or [f"animal_{idx + 1}" for idx in range(len(batch_dicts))]
    elif isinstance(labels, str):
        labels = [labels]
    else:
        labels = list(labels)

    if len(labels) != len(batch_dicts):
        raise ValueError("labels must have the same length as batch_hit_by_sound.")

    return batch_dicts, labels


def batch_go_performance_matrix(
    loaded_batches,
    labels=None,
    alldays_datekeys=None,
    n_size_window: int = 10,
) -> dict:
    """
    Convert loaded animal batch dicts into an aligned performance matrix.

    Rows are animals. Columns are consecutive trial-window performance bins.
    Animals with fewer bins are padded with NaN, so use np.nanmean/np.nanstd
    across axis=0.
    """
    batch_dicts, animal_labels = _normalize_batch_go_inputs(loaded_batches, labels=labels)

    if alldays_datekeys is None:
        all_key_lists = [sorted(batch_dict.keys()) for batch_dict in batch_dicts]
    elif (
        len(batch_dicts) > 1
        and isinstance(alldays_datekeys, (list, tuple))
        and len(alldays_datekeys) == len(batch_dicts)
        and all(isinstance(item, (list, tuple)) for item in alldays_datekeys)
    ):
        all_key_lists = [list(keys) for keys in alldays_datekeys]
    else:
        all_key_lists = [list(alldays_datekeys) for _ in batch_dicts]

    perf_arrays = []
    for batch_dict, datekeys in zip(batch_dicts, all_key_lists):
        all_perf = []
        for datekey in datekeys:
            alldata_go = np.asarray(batch_dict[datekey]["alldataGO"], dtype=float)
            n = len(alldata_go) // n_size_window * n_size_window
            if n == 0:
                continue

            a_reshaped = alldata_go[:n].reshape(-1, n_size_window)
            n_trials_x_arr = np.sum(~np.isnan(a_reshaped), axis=1)
            perf_across_session = np.divide(
                np.nansum(a_reshaped, axis=1),
                n_trials_x_arr,
                out=np.full(a_reshaped.shape[0], np.nan),
                where=n_trials_x_arr > 0,
            )
            all_perf.extend(perf_across_session)
        perf_arrays.append(np.asarray(all_perf, dtype=float))

    max_len = max((len(arr) for arr in perf_arrays), default=0)
    perf_matrix = np.full((len(perf_arrays), max_len), np.nan, dtype=float)
    for row_idx, perf_array in enumerate(perf_arrays):
        perf_matrix[row_idx, :len(perf_array)] = perf_array

    mean_curve = np.nanmean(perf_matrix, axis=0)
    std_curve = np.nanstd(perf_matrix, axis=0, ddof=1)
    n_by_bin = np.sum(~np.isnan(perf_matrix), axis=0)
    sem_curve = np.divide(
        std_curve,
        np.sqrt(n_by_bin),
        out=np.full_like(std_curve, np.nan),
        where=n_by_bin > 0,
    )
    x = (np.arange(max_len) + 1) * n_size_window

    return {
        "labels": animal_labels,
        "x": x,
        "perf_matrix": perf_matrix,
        "mean_curve": mean_curve,
        "std_curve": std_curve,
        "sem_curve": sem_curve,
        "n_by_bin": n_by_bin,
        "n_size_window": n_size_window,
    }


def load_batch_dicts(batch_paths) -> list[dict]:
    if isinstance(batch_paths, (str, Path)):
        batch_path = Path(batch_paths)
        if batch_path.is_dir():
            paths = sorted(batch_path.glob("*.pkl"))
        else:
            paths = [batch_path]
    else:
        paths = [Path(path) for path in batch_paths]

    if not paths:
        raise FileNotFoundError("No .pkl batch files found.")

    batch_dicts = []
    for path in paths:
        batch_dict = load_batch_dict(path)
        batch_dict["_pkl_path"] = str(path)
        batch_dicts.append(batch_dict)
    return batch_dicts

def compute_mean_go_by_sound_from_pkls(
    batch_paths,
    sound_in_khz=None,
    value_key: str = "FAs_pct",
) -> dict:
    batch_dicts = load_batch_dicts(batch_paths)
    all_sound_ids = sorted(
        {
            int(sound_id)
            for batch_dict in batch_dicts
            for sound_id in batch_dict.get("hit_by_sound", {}).keys()
        }
    )
    if not all_sound_ids:
        raise ValueError("No hit_by_sound data found in the provided batch dicts.")

    if sound_in_khz is None:
        sound_in_khz = np.linspace(4, 16, len(all_sound_ids))
    else:
        sound_in_khz = np.asarray(sound_in_khz, dtype=float)
        if len(sound_in_khz) != len(all_sound_ids):
            raise ValueError(
                "sound_in_khz must have the same length as the number of SoundIds."
            )

    mouse_names = []
    go_matrix = np.full((len(batch_dicts), len(all_sound_ids)), np.nan, dtype=float)
    n_trials_matrix = np.full((len(batch_dicts), len(all_sound_ids)), np.nan, dtype=float)

    for mouse_idx, batch_dict in enumerate(batch_dicts):
        mouse_name = batch_dict.get("animal_name") or Path(
            batch_dict.get("_pkl_path", f"mouse_{mouse_idx + 1}")
        ).stem
        mouse_names.append(str(mouse_name))
        hit_by_sound = batch_dict.get("hit_by_sound", {})
        normalized_hit_by_sound = {
            int(sound_id): stats for sound_id, stats in hit_by_sound.items()
        }
        for sound_idx, sound_id in enumerate(all_sound_ids):
            stats = normalized_hit_by_sound.get(sound_id)
            if not stats:
                continue
            go_matrix[mouse_idx, sound_idx] = float(stats[value_key])
            n_trials_matrix[mouse_idx, sound_idx] = float(stats.get("n_trials", np.nan))

    n_mice_by_sound = np.sum(~np.isnan(go_matrix), axis=0)
    mean_go_pct = np.nanmean(go_matrix, axis=0)
    sem_go_pct = np.zeros(len(all_sound_ids), dtype=float)
    for sound_idx in range(len(all_sound_ids)):
        values = go_matrix[:, sound_idx]
        values = values[~np.isnan(values)]
        if len(values) > 1:
            sem_go_pct[sound_idx] = np.std(values, ddof=1) / np.sqrt(len(values))

    return {
        "batch_dicts": batch_dicts,
        "mouse_names": mouse_names,
        "sound_ids": all_sound_ids,
        "sound_in_khz": sound_in_khz,
        "go_matrix": go_matrix,
        "n_trials_matrix": n_trials_matrix,
        "n_mice_by_sound": n_mice_by_sound,
        "mean_go_pct": mean_go_pct,
        "sem_go_pct": sem_go_pct,
        "value_key": value_key,
    }
