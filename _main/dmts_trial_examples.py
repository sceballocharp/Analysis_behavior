"""One chronological example of each DMTS outcome with raw lick voltages."""
import numpy as np
from matplotlib.figure import Figure
from dmts_analysis import analyze_dmts, crossings, parameters, signal_times


def plot_trial_examples(session, title="DMTS session"):
    analysis = analyze_dmts(session)
    signals = session['signals']
    p = parameters(session)
    duration = float(p.get('SoundDuration_s', p.get('sound_duration_s')))
    clocks = {name: signal_times(signal) for name, signal in signals.items()
              if name in ('LeftLick', 'RightLick', 'Reward')}
    events = {side: crossings(signals[side + 'Lick'], analysis['thresholds'][side])
              for side in ('Left', 'Right') if side + 'Lick' in signals}
    fig = Figure(figsize=(14, 8.5))
    axes = fig.subplots(2, 2)
    for ax, outcome, label in zip(axes.flat, ('Hit', 'Miss', 'Correct', 'FalseAlarm'),
                                  ('HIT', 'MISS', 'CR', 'FA')):
        trial = next((t for t in analysis['trials'] if t['kind'] != 'blank' and
                      (t['outcome'] if t['outcome'] is not None else t['saved_outcome']) == outcome), None)
        ax.set_title(label)
        if trial is None:
            ax.text(.5, .5, 'No ' + label + ' trials in this session',
                    transform=ax.transAxes, ha='center', va='center')
            ax.set_axis_off()
            continue
        start = trial['start']
        lo, hi = start - .5, trial['response_end'] + .5
        for side, color in (('Left', '#2878B5'), ('Right', '#DB7130')):
            name = side + 'Lick'
            if name not in signals:
                ax.plot([], [], color=color, label=side + ' channel missing')
                continue
            times = clocks[name]
            values = np.asarray(signals[name]['data'])
            mask = (times >= lo) & (times <= hi)
            ax.plot(times[mask] - start, values[mask], color=color, lw=.85, label=side + ' lick')
            threshold = analysis['thresholds'][side]
            ax.axhline(threshold, color=color, ls='--', lw=.8,
                       label=f'{side} threshold {threshold:g} V')
            detected = events[side]
            detected = detected[(detected >= lo) & (detected <= hi)]
            indices = np.searchsorted(times, detected)
            ax.scatter(detected - start, values[indices], color=color, marker='v', s=24,
                       zorder=4, label=side + ' detected licks')
        if 'Reward' in signals:
            times = clocks['Reward']
            mask = (times >= lo) & (times <= hi)
            ax.plot(times[mask] - start, np.asarray(signals['Reward']['data'])[mask],
                    color='#444444', lw=1, alpha=.75, label='Reward (V)')
        else:
            ax.plot([], [], color='#444444', label='Reward channel missing')
        ax.axvspan(0, duration, color='#729BC5', alpha=.15, label='Sample')
        ax.axvspan(trial['test_start'] - start, trial['test_start'] - start + duration,
                   color='#B392C7', alpha=.15, label='Test')
        ax.axvspan(trial['response_start'] - start, trial['response_end'] - start,
                   color='#73B87A', alpha=.15, label='Response window')
        source = 'signal' if trial['outcome'] is not None else 'saved; incomplete signals'
        ax.set_title(f"{label} · trial {trial['index'] + 1} · {trial['sample_id']} → {trial['test_id']}\n"
                     f"{source}; saved: {trial['saved_outcome'] or 'unavailable'}", fontsize=10)
        ax.set_xlabel('Time from sample onset (s)')
        ax.set_ylabel('Voltage (V)')
        ax.set_xlim(-.5, hi - start)
        ax.grid(alpha=.2)
        ax.legend(fontsize=6, loc='upper right', ncol=2)
    fig.suptitle(title + '\nTrial Examples — first trial per outcome', fontsize=12)
    fig.text(.5, .015, 'Licks: upward threshold crossings on raw traces. Outcomes: existing DMTS response-window scoring. '
             'Shading uses the existing trial timing.', ha='center', fontsize=8)
    fig.tight_layout(rect=(0, .04, 1, .92))
    return fig
