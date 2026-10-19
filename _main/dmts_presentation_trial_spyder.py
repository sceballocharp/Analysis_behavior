# %% Paste/run this cell in Spyder after editing the paths and sampling rate.
from pathlib import Path
import sys

MODULE_DIR = Path(r'C:\Users\seceball\Documents\ChatGPT\Analysis\_Behavior\_main')
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

from behavior_functions import load_session_data_fromFile
from read_sound_mat import load_sound_waveforms
from dmts_presentation_trial import plot_presentation_trial

NWB_FILE = Path(r'C:\path\to\session.nwb')
SOUND_MAT = Path(r'C:\path\to\sounds.mat')
SOUND_FS = None  # Set the ACTUAL stimulus sampling rate in Hz before running.
TRIAL_NUMBER = None  # Any 1-based session trial number; None selects first trial.

if SOUND_FS is None:
    raise ValueError('Set SOUND_FS to the actual stimulus sampling rate in Hz.')

session = load_session_data_fromFile(NWB_FILE)
waveforms = load_sound_waveforms(SOUND_MAT)
# Verify this mapping: MATLAB Sound cell 1 -> sound ID 1, etc.
sounds = {sid: waveform for sid, waveform in enumerate(waveforms, start=1)}
fig, trial = plot_presentation_trial(session, sounds, SOUND_FS, trial_number=TRIAL_NUMBER)
print(f"Selected session trial {trial['index'] + 1}; timing: {trial['timing']}")

# %% Optional export once the example trial is chosen.
# fig.savefig(MODULE_DIR / 'dmts_match_trial.pdf', bbox_inches='tight')
# fig.savefig(MODULE_DIR / 'dmts_match_trial.png', dpi=300, bbox_inches='tight')
