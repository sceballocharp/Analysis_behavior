"""Dual-lick DMTS analysis, with explicit timing and channel provenance."""
import numpy as np


def parameters(session):
    def decode(value):
        return value.decode('utf-8') if isinstance(value, bytes) else str(value)
    source = session.get('parameters', {})
    return {decode(k): decode(v) for k, v in source.items()} if isinstance(source, dict) else {}


def is_dmts_lick(session):
    p = parameters(session)
    return p.get('TaskType', p.get('task_type', '')).upper() == 'DMTS' and p.get('TriggerType', '').lower() == 'lick'


def signal_times(signal):
    if 'timestamps' in signal:
        return np.asarray(signal['timestamps'], dtype=float)
    return float(signal['start']) + np.arange(len(signal['data'])) / float(signal['rate'])


def crossings(signal, threshold):
    high = np.asarray(signal['data']) >= threshold
    return signal_times(signal)[np.flatnonzero(high & ~np.r_[False, high[:-1]])]


def score_trial(left, right, minimum, kind):
    if kind == 'blank':
        return 'Blank', ''
    lt = left[minimum - 1] if len(left) >= minimum else np.inf
    rt = right[minimum - 1] if len(right) >= minimum else np.inf
    if kind == 'nonmatch':
        return ('FalseAlarm', 'left') if np.isfinite(lt) else ('Correct', '')
    if not np.isfinite(min(lt, rt)):
        return 'Miss', ''
    return ('Hit', 'left') if lt <= rt else ('FalseAlarm', 'right')


def analyze_dmts(session):
    if 'dmts_analysis' in session:
        return session['dmts_analysis']
    p = parameters(session)
    def number(key, fallback=None):
        raw = p.get(key, p.get(fallback) if fallback else None)
        try:
            value = float(raw)
        except (TypeError, ValueError):
            raise ValueError(f'DMTS requires a valid {key} parameter.') from None
        if not np.isfinite(value):
            raise ValueError(f'DMTS requires a finite {key} parameter.')
        return value
    duration = number('SoundDuration_s', 'sound_duration_s')
    delay = number('Delay_s', 'delay_s')
    response = number('ResponseWindow_s', 'response_window_s')
    minimum_value = number('Minlickcount', 'min_lick_count')
    if duration <= 0 or delay < 0 or response <= 0 or minimum_value < 1 or not minimum_value.is_integer():
        raise ValueError('Invalid DMTS timing or minimum lick count.')
    minimum = int(minimum_value)
    signals = session.get('signals', {})
    missing = [name for name in ('LeftLick', 'RightLick') if name not in signals]
    thresholds = {side: number('TAC' + side + 'Threshold', 'tac_' + side.lower() + '_threshold')
                  for side in ('Left', 'Right')}
    events = {side: crossings(signals[side + 'Lick'], thresholds[side])
              for side in ('Left', 'Right') if side + 'Lick' in signals}
    clocks = {side: signal_times(signals[side + 'Lick']) for side in events}
    table = session['ResultsTable']
    if not {'SampleSoundId', 'TestSoundId'}.issubset(table.columns):
        raise ValueError('DMTS requires per-trial sample_sound_ids and test_sound_ids.')
    marker_signal = signals.get('TrialType')
    markers = (signal_times(marker_signal)[np.asarray(marker_signal['data']) == 99]
               if marker_signal is not None else np.flatnonzero(session['trialID']['full'] == 99) * 0.1)
    if 'StartTime' not in table and len(markers) != len(table):
        raise ValueError('DMTS trial markers do not match trial rows; cannot align lick counts safely.')
    which = signals.get('WhichSound')
    sound_onsets = []
    if which is not None:
        ids = np.asarray(which['data'])
        edges = np.flatnonzero((ids > 0) & (ids != np.r_[0, ids[:-1]]))
        sound_onsets = list(zip(signal_times(which)[edges], ids[edges]))
    trials = []
    for index, (_, row) in enumerate(table.iterrows()):
        sample, test = int(row.SampleSoundId), int(row.TestSoundId)
        kind = 'blank' if sample == 0 and test == 0 else 'match' if sample == test else 'nonmatch'
        start = float(row.StartTime) if 'StartTime' in table else float(markers[index])
        if not np.isfinite(start):
            raise ValueError(f'DMTS trial {index + 1} has no valid start time.')
        timing = 'trial start_time' if 'StartTime' in table else 'trial marker (0.1 s resolution)'
        candidates = [t for t, sid in sound_onsets if sid == sample and abs(t - start) <= 0.051]
        if candidates and kind != 'blank':
            start = min(candidates, key=lambda t: abs(t - start))
            timing = 'recorded sound onset + protocol durations'
        test_start = start + duration + delay
        rw_start, rw_end = test_start + duration, test_start + duration + response
        counts = {side: times[(times >= rw_start - 1e-9) & (times < rw_end - 1e-9)]
                  for side, times in events.items()}
        def covers_window(side):
            times = clocks[side]
            step = float(np.median(np.diff(times))) if len(times) > 1 else 0.
            selected = (times >= rw_start) & (times < rw_end)
            return (len(times) > 1 and times[0] <= rw_start and times[-1] + step >= rw_end - 1e-9
                    and selected.any() and np.all(np.isfinite(np.asarray(signals[side + 'Lick']['data'])[selected])))
        complete = not missing and all(covers_window(side) for side in ('Left', 'Right'))
        outcome, choice = score_trial(counts.get('Left', []), counts.get('Right', []), minimum, kind) if complete else (None, '')
        saved = str(row.get('SavedOutcome', ''))
        if kind == 'blank':
            saved = 'Blank'
        trials.append(dict(index=index, sample_id=sample, test_id=test, kind=kind,
                           start=start, test_start=test_start, response_start=rw_start,
                           response_end=rw_end, timing=timing, events=counts,
                           outcome=outcome, saved_outcome=saved, choice=choice))
    # Missing channels/partial recordings retain recorded outcomes, explicitly labelled.
    effective = [t['outcome'] if t['outcome'] is not None else t['saved_outcome'] for t in trials]
    for name, values in {
        'DMTSKind': [t['kind'] for t in trials],
        'DMTSOutcome': effective,
        'DMTSOutcomeSource': ['signal' if t['outcome'] is not None else 'saved (incomplete signals)' for t in trials],
        'LeftLickCount': [len(t['events']['Left']) if 'Left' in t['events'] else np.nan for t in trials],
        'RightLickCount': [len(t['events']['Right']) if 'Right' in t['events'] else np.nan for t in trials],
        'DMTSChoice': [t['choice'] for t in trials],
        'ResponseStart': [t['response_start'] for t in trials],
        'ResponseEnd': [t['response_end'] for t in trials],
        'DMTSTiming': [t['timing'] for t in trials],
    }.items():
        table[name] = values
    def accuracy(kind):
        valid = [o for t, o in zip(trials, effective) if t['kind'] == kind and o in ('Hit', 'Miss', 'Correct', 'FalseAlarm')]
        return 100 * sum(o in ('Hit', 'Correct') for o in valid) / len(valid) if valid else float('nan')
    valid = [o for t, o in zip(trials, effective) if t['kind'] != 'blank' and o in ('Hit', 'Miss', 'Correct', 'FalseAlarm')]
    perf = dict(go=accuracy('match'), nogo=accuracy('nonmatch'),
                total=100 * sum(o in ('Hit', 'Correct') for o in valid) / len(valid) if valid else float('nan'),
                n_go=sum(t['kind'] == 'match' for t in trials),
                n_nogo=sum(t['kind'] == 'nonmatch' for t in trials),
                n_blank=sum(t['kind'] == 'blank' for t in trials), task='DMTS')
    by_sound = {}
    for sid in sorted({t['test_id'] for t in trials if t['kind'] != 'blank'}):
        values = [int(o in ('Hit', 'Correct')) for t, o in zip(trials, effective)
                  if t['test_id'] == sid and t['kind'] != 'blank' and o in ('Hit', 'Miss', 'Correct', 'FalseAlarm')]
        by_sound[sid] = dict(n_trials=len(values), n_FAs=sum(values),
                             FAs_pct=100 * sum(values) / len(values) if values else float('nan'),
                             allTrialsAsGO=values, metric='DMTS correct')
    result = dict(trials=trials, thresholds=thresholds, minimum=minimum, missing_channels=missing,
                  performance=perf, hit_by_sound=by_sound,
                  mismatch_count=sum(t['outcome'] is not None and t['outcome'] != t['saved_outcome'] for t in trials),
                  saved_fallback_count=sum(t['outcome'] is None for t in trials))
    session['dmts_analysis'] = result
    return result


def plot_dmts_trial(session, trial_index=0, show=True, block=False):
    import matplotlib.pyplot as plt
    analysis = analyze_dmts(session)
    trial = analysis['trials'][trial_index]
    start = trial['start']
    fig, axes = plt.subplots(4, 1, figsize=(8, 8.5), sharex=True)
    for ax, side, color in zip(axes[:2], ('Left', 'Right'), ('#2878B5', '#DB7130')):
        signal = session['signals'].get(side + 'Lick')
        if signal is None:
            ax.text(.5, .5, side + ' lick channel not recorded', transform=ax.transAxes, ha='center')
        else:
            times = signal_times(signal)
            mask = (times >= start - .5) & (times <= trial['response_end'] + .5)
            ax.plot(times[mask] - start, np.asarray(signal['data'])[mask], color=color, lw=.9)
            ax.axhline(analysis['thresholds'][side], color=color, ls='--', lw=.8)
            for event in trial['events'][side]:
                ax.axvline(event - start, color=color, alpha=.5, lw=.8)
        ax.set_ylabel(side + ' lick (V)')
    for ax, name in zip(axes[2:], ('SoundCopy', 'Reward')):
        signal = session['signals'].get(name)
        if signal is not None:
            times = signal_times(signal)
            mask = (times >= start - .5) & (times <= trial['response_end'] + .5)
            ax.plot(times[mask] - start, np.asarray(signal['data'])[mask], color='#555555', lw=.8)
        ax.set_ylabel('Sound' if name == 'SoundCopy' else 'Reward')
    p = parameters(session)
    duration = float(p.get('SoundDuration_s', p.get('sound_duration_s')))
    for ax in axes:
        if trial['kind'] != 'blank':
            ax.axvspan(0, duration, color='#729BC5', alpha=.18, label='Sample')
            ax.axvspan(trial['test_start'] - start, trial['test_start'] - start + duration,
                       color='#B392C7', alpha=.2, label='Test')
        ax.axvspan(trial['response_start'] - start, trial['response_end'] - start,
                   color='#73B87A', alpha=.17, label='Response window')
        ax.set_xlim(-.5, trial['response_end'] - start + .5)
        ax.grid(alpha=.18)
    axes[0].legend(loc='upper right', fontsize=8)
    left = len(trial['events']['Left']) if 'Left' in trial['events'] else 'missing'
    right = len(trial['events']['Right']) if 'Right' in trial['events'] else 'missing'
    fig.suptitle(f"DMTS trial {trial_index + 1} · {trial['kind']} · sample {trial['sample_id']} → test {trial['test_id']}\n"
                 f"L/R counts: {left}/{right} · minimum {analysis['minimum']} · choice: {trial['choice'] or 'none'}\n"
                 f"Recalculated: {trial['outcome'] or 'unavailable'} · saved: {trial['saved_outcome'] or 'unavailable'}", fontsize=11)
    axes[-1].set_xlabel('Time from sample / blank onset (s)')
    fig.text(.5, .015, 'Timing: ' + trial['timing'], ha='center', fontsize=8)
    fig.tight_layout(rect=(0, .035, 1, .9))
    if show:
        plt.show(block=block)
    return fig
