# -*- coding: utf-8 -*-
"""
Created on Mon Apr 27 13:18:17 2026

@author: seceball
"""

from pathlib import Path
from datetime import datetime
import sys
import numpy as np
import pandas as pd
import h5py

class session_data_nwb():
    
    """
    nwb_path: Path
    Load behavior session data from an NWB file.

    This requires `h5py` to be installed in the current Python environment.
    The function tries a few common key names and keeps backward-compatible
    output keys used by the rest of this codebase.
    
    ['/acquisition/Lick/data',
     '/acquisition/Lick/starting_time',
     '/acquisition/Parameters/id',
     '/acquisition/Parameters/key',
     '/acquisition/Parameters/value',
     '/acquisition/Reward/data',
     '/acquisition/Reward/starting_time',
     '/acquisition/TTLstartcam1/data',
     '/acquisition/TTLstartcam1/starting_time',
     '/acquisition/TTLstartcam2/data',
     '/acquisition/TTLstartcam2/starting_time',
     '/acquisition/TTLtrigcamera1/data',
     '/acquisition/TTLtrigcamera1/starting_time',
     '/acquisition/TTLtrigcamera2/data',
     '/acquisition/TTLtrigcamera2/starting_time',
     '/acquisition/TTLtrigsounds/data',
     '/acquisition/TTLtrigsounds/starting_time',
     '/acquisition/TrialType/data',
     '/acquisition/TrialType/starting_time',
     '/file_create_date',
     '/general/source_script',
     '/general/subject/age',
     '/general/subject/sex',
     '/general/subject/species',
     '/general/subject/subject_id',
     '/identifier',
     '/intervals/trials/HMCF',
     '/intervals/trials/id',
     '/intervals/trials/response_time',
     '/intervals/trials/sound_ids',
     '/intervals/trials/start_time',
     '/intervals/trials/stop_time',
     '/intervals/trials/trial_type',
     '/session_description',
     '/session_start_time',
     '/specifications/core/2.9.0/namespace',
     '/specifications/core/2.9.0/nwb.base',
     '/specifications/core/2.9.0/nwb.behavior',
     '/specifications/core/2.9.0/nwb.device',
     '/specifications/core/2.9.0/nwb.ecephys',
     '/specifications/core/2.9.0/nwb.epoch',
     '/specifications/core/2.9.0/nwb.file',
     '/specifications/core/2.9.0/nwb.icephys',
     '/specifications/core/2.9.0/nwb.image',
     '/specifications/core/2.9.0/nwb.misc',
     '/specifications/core/2.9.0/nwb.ogen',
     '/specifications/core/2.9.0/nwb.ophys',
     '/specifications/core/2.9.0/nwb.retinotopy',
     '/specifications/hdmf-common/1.8.0/base',
     '/specifications/hdmf-common/1.8.0/namespace',
     '/specifications/hdmf-common/1.8.0/sparse',
     '/specifications/hdmf-common/1.8.0/table',
     '/specifications/hdmf-experimental/0.5.0/experimental',
     '/specifications/hdmf-experimental/0.5.0/namespace',
     '/specifications/hdmf-experimental/0.5.0/resources',
     '/specifications/ndx-sound/0.1.0/namespace',
     '/specifications/ndx-sound/0.1.0/ndx-sound.extensions',
     '/stimulus/presentation/SoundCopy/data',
     '/stimulus/presentation/SoundCopy/starting_time',
     '/stimulus/presentation/WhichSound/data',
     '/stimulus/presentation/WhichSound/starting_time',
     '/stimulus/templates/1/data',
     '/stimulus/templates/1/starting_time',
     '/stimulus/templates/10/data',
     '/stimulus/templates/10/starting_time',
     '/stimulus/templates/11/data',
     '/stimulus/templates/11/starting_time',
     '/stimulus/templates/12/data',
     '/stimulus/templates/12/starting_time',
     '/stimulus/templates/13/data',
     '/stimulus/templates/13/starting_time',
     '/stimulus/templates/14/data',
     '/stimulus/templates/14/starting_time',
     '/stimulus/templates/15/data',
     '/stimulus/templates/15/starting_time',
     '/stimulus/templates/16/data',
     '/stimulus/templates/16/starting_time',
     '/stimulus/templates/2/data',
     '/stimulus/templates/2/starting_time',
     '/stimulus/templates/3/data',
     '/stimulus/templates/3/starting_time',
     '/stimulus/templates/4/data',
     '/stimulus/templates/4/starting_time',
     '/stimulus/templates/5/data',
     '/stimulus/templates/5/starting_time',
     '/stimulus/templates/6/data',
     '/stimulus/templates/6/starting_time',
     '/stimulus/templates/7/data',
     '/stimulus/templates/7/starting_time',
     '/stimulus/templates/8/data',
     '/stimulus/templates/8/starting_time',
     '/stimulus/templates/9/data',
     '/stimulus/templates/9/starting_time',
     '/timestamps_reference_time']
    """
    
    def __init__(self,**kwargs):
        
        try:
            import h5py
        except Exception:
            raise ImportError("NWB loading requires h5py (or pynwb) in this Python environment.") 
        
        #print(kwargs)
        nwbfile = kwargs['nwbfile']
        self.nwb_path = Path(nwbfile)
        
        return
    
    ############################# 
    # INTERNAL

    def _all_dataset_paths(self,h5obj):
        paths = []
    
        def _visitor(name, obj):
            if isinstance(obj, h5py.Dataset):
                paths.append("/" + name)
    
        h5obj.visititems(_visitor)
        return paths
 
    #########################
    # MAIN
    
    def read_paths(self):
        with h5py.File(self.nwb_path, "r") as h5f:
            ds_paths = self._all_dataset_paths(h5f)
            self.ds_paths =  ds_paths
        return 
    
    def extract_continuous_signal(self):
        with h5py.File(self.nwb_path, "r") as h5f:
            
            sound_signal = np.array(h5f['stimulus']['presentation']['SoundCopy']['data'])
            whichSound = np.array(h5f['stimulus']['presentation']['WhichSound']['data'])
            reward = np.array(h5f['acquisition']['Reward']['data'])
            trialtype = np.array(h5f['acquisition']['TrialType']['data'])
            IRdata = np.array(h5f['acquisition']['IRFork']['data'])
            
            self.sound_signal = sound_signal
            self.whichSound = whichSound
            self.reward_signal = reward
            self.trialtype = trialtype
            self.IR_signal = IRdata
            
        return
    
    def generate_results_table(self):
        
        with h5py.File(self.nwb_path, "r") as h5f:
            result_by_trial_string = np.array([val.decode("utf-8", errors="ignore") for val in h5f['intervals']['trials']['HMCF'][:]])
            trial_type_string = np.array([val.decode("utf-8", errors="ignore") for val in h5f['intervals']['trials']['trial_type'][:]])
            
            ntrials = len(trial_type_string)
            ttypearr = np.zeros(ntrials)
            ttypeGO =  np.array(trial_type_string == 'Go').astype(bool)
            ttypeNoGO =  np.array(trial_type_string == 'NoGo').astype(bool)
            ttypearr[ttypeGO] = 1
            ttypearr[ttypeNoGO] = 2
            
            HIT = np.array(result_by_trial_string == 'Hit').astype(int)
            MISS = np.array(result_by_trial_string == 'Miss').astype(int)
            CR = np.array(result_by_trial_string == 'Correct').astype(int)
            FA = np.array(result_by_trial_string == 'FalseAlarm').astype(int)

            data = {
                "TrialsId": np.array(h5f['intervals']['trials']['id'][:]),
                "SoundId": np.array(h5f['intervals']['trials']['sound_ids'][:]),
                "TrialType": np.array(ttypearr).astype(int),
                "Hit":      HIT,
                "Miss":     MISS,
                "CR":       CR,
                "FA":       FA,
            }
            
            self.results_table = pd.DataFrame(data)
        
        return 
    
    def get_parameters(self):
        with h5py.File(self.nwb_path, "r") as h5f:

            date_raw = h5f['file_create_date'][:]
            date_string_full = date_raw[0].decode('utf-8')
            dtf = datetime.fromisoformat(date_string_full)
            onlydatestring = dtf.date().isoformat()

            values_string = np.array([val.decode("utf-8", errors="ignore") for val in h5f['acquisition']['Parameters']['value'][:]])
            keys_strings = np.array([val.decode("utf-8", errors="ignore") for val in h5f['acquisition']['Parameters']['key'][:]])
            parameters = {}
            parameters['date'] = onlydatestring
            for key,val in zip(keys_strings,values_string):
                parameters[key] = val
            
            self.parameters = parameters
        return
