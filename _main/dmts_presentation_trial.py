"""Single DMTS trial figure for Spyder, using the GUI's DMTS trial plot.

Run the console example in dmts_presentation_trial_spyder.py after setting paths.
Sound IDs must map to the actual stimulus waveforms used in the session.
"""
import numpy as np
from dmts_analysis import analyze_dmts, parameters, plot_dmts_trial


def trial_numbers_by_outcome(session):
    """Return 1-based trial numbers; use saved outcomes if signals are incomplete.

    Blank trials and trials without a recognized outcome are excluded.
    """
    groups = {'Hit': [], 'Miss': [], 'CorrectRejection': [], 'FalseAlarm': []}
    for trial in analyze_dmts(session)['trials']:
        if trial['kind'] == 'blank':
            continue
        outcome = trial['outcome'] if trial['outcome'] is not None else trial['saved_outcome']
        key = 'CorrectRejection' if outcome == 'Correct' else outcome
        if key in groups:
            groups[key].append(trial['index'] + 1)
    return groups


def plot_presentation_trial(session, sounds, sound_fs, trial_number=None,
                     dynamic_range_db=70, show=True):
    """Plot stimulus spectrograms, raw L/R licks and task epochs.

    sounds: dict {sound_id: mono waveform}, with IDs matching ResultsTable.
    sound_fs: actual waveform sampling rate in Hz (never inferred).
    trial_number: 1-based session trial number of any type; None selects the
        first trial. Returns (figure, selected_trial). Sound ID 0 is silence.
    Spectra share a peak-relative dB scale; these are stimulus files, not a
    microphone recording. Shorter waveforms occupy only their actual duration
    within the protocol sound window; longer waveforms are rejected.
    """
    import matplotlib.pyplot as plt
    from scipy.signal import spectrogram

    if not np.isfinite(sound_fs) or sound_fs <= 0:
        raise ValueError('sound_fs must be the positive stimulus sampling rate in Hz.')
    if not np.isfinite(dynamic_range_db) or dynamic_range_db <= 0:
        raise ValueError('dynamic_range_db must be positive.')
    analysis = analyze_dmts(session)
    if not analysis['trials']:
        raise ValueError('This session has no trials.')
    if trial_number is None:
        trial = analysis['trials'][0]
    else:
        if int(trial_number) != trial_number or not 1 <= trial_number <= len(analysis['trials']):
            raise ValueError('trial_number must be a 1-based session trial number.')
        trial = analysis['trials'][int(trial_number) - 1]
    missing = [side for side in ('LeftLick', 'RightLick') if side not in session['signals']]
    if missing:
        raise ValueError('Both lick traces are required; missing: ' + ', '.join(missing))
    p = parameters(session)
    duration = float(p.get('SoundDuration_s', p.get('sound_duration_s')))
    spectra = []
    for sid in (trial['sample_id'], trial['test_id']):
        if sid == 0:
            spectra.append(None)
            continue
        if sid not in sounds:
            raise ValueError(f'No stimulus waveform supplied for sound ID {sid}.')
        wave = np.asarray(sounds[sid], dtype=float).squeeze()
        if wave.ndim != 1 or wave.size < 8 or not np.all(np.isfinite(wave)):
            raise ValueError(f'Sound {sid} requires a finite mono waveform (at least 8 samples).')
        if wave.size / sound_fs - duration > max(2 / sound_fs, .001):
            raise ValueError(f'Sound {sid} duration {wave.size / sound_fs:g} s exceeds '
                             f'task duration {duration:g} s. Supply the actual played segment.')
        nperseg = min(wave.size, max(8, int(round(.008 * sound_fs))))
        f, t, power = spectrogram(wave, fs=sound_fs, nperseg=nperseg,
                                  noverlap=int(.875 * nperseg), detrend=False)
        spectra.append((f, t, power))
    peak = max((s[2].max() for s in spectra if s is not None), default=1.)
    if peak <= 0:
        raise ValueError('Stimulus waveform is silent; no spectrogram can be displayed.')

    # Keep the GUI's trace drawing, thresholds, lick events and timing shading.
    fig = plot_dmts_trial(session, trial_index=trial['index'], show=False)
    left, right, task, reward = fig.axes
    reward.remove()
    task.clear()
    fig.set_size_inches(11, 6.5)
    grid = fig.add_gridspec(4, 1, height_ratios=(.55, 1.5, 1, 1),
                           left=.1, right=.86, bottom=.13, top=.87, hspace=.12)
    spec = fig.add_subplot(grid[1], sharex=left)
    for row, ax in ((0, task), (2, left), (3, right)):
        cell = grid[row, 0]
        ax.set_subplotspec(cell)
        ax.set_position(cell.get_position(fig))
        ax.spines[['top', 'right']].set_visible(False)
    mesh = None
    for spectrum, onset in zip(spectra, (0, trial['test_start'] - trial['start'])):
        if spectrum is None:
            continue
        f, t, power = spectrum
        db = 10 * np.log10(np.maximum(power / peak, 10 ** (-dynamic_range_db / 10)))
        mesh = spec.pcolormesh(t + onset, f / 1000, db, shading='auto',
                               cmap='jet', vmin=-dynamic_range_db, vmax=0,
                               rasterized=True)
    spec.set_ylabel('Frequency (kHz)')
    spec.set_ylim(0, sound_fs / 2000)
    if mesh is not None:
        spec_box = spec.get_position()
        cax = fig.add_axes([.89, spec_box.y0, .015, spec_box.height])
        fig.colorbar(mesh, cax=cax, label='Power (dB re. peak)')
    else:
        spec.text(.5, .5, 'Blank trial: no sounds played',
                  transform=spec.transAxes, ha='center', va='center')
    test = trial['test_start'] - trial['start']
    response = trial['response_start'] - trial['start']
    end = trial['response_end'] - trial['start']
    for lo, hi, label, color in ((0, duration, 'Sample', '#729BC5'),
                                 (duration, test, 'Delay', '#D9D9D9'),
                                 (test, response, 'Test', '#B392C7'),
                                 (response, end, 'Response', '#73B87A')):
        if label == 'Sample' and trial['sample_id'] == 0:
            label = 'Sample (silent)'
        if label == 'Test' and trial['test_id'] == 0:
            label = 'Test (silent)'
        task.axvspan(lo, hi, color=color, alpha=.5)
        if hi > lo:
            task.text((lo + hi) / 2, .5, f'{label}\n{hi - lo:g} s',
                      ha='center', va='center', fontsize=9)
    task.set_ylim(0, 1)
    task.set_yticks([])
    task.set_ylabel('Task')
    right.set_xlabel('Time from sample onset (s)')
    right.tick_params(labelbottom=True)
    for ax in (task, spec, left):
        ax.set_xlabel('')
        ax.tick_params(labelbottom=False)
    if left.get_legend() is not None:
        left.get_legend().remove()
    outcome = trial['outcome'] or f"{trial['saved_outcome']} (saved; incomplete signals)"
    fig.suptitle(f"{trial['kind'].capitalize()} trial {trial['index'] + 1} · "
                 f"sample {trial['sample_id']} → test {trial['test_id']} · {outcome}", fontsize=14)
    fig.texts[-1].set_text('Timing: ' + trial['timing'] +
                           ' | Spectrograms: supplied stimulus waveforms')
    if show:
        plt.show(block=False)
    return fig, trial


# Backward compatibility for existing Spyder console calls; accepts all types.
plot_match_trial = plot_presentation_trial
