"""Light-versus-sound saved-outcome performance across NWB sessions."""
from pathlib import Path
import numpy as np
from matplotlib.figure import Figure
from dmts_batch import session_sort_key

METRICS = ('Overall accuracy', 'Match hit rate', 'Non-match CR rate')


def summarize_modality_session(session, path):
    table = session['ResultsTable']
    required = {'StimulusSource', 'SampleSoundId', 'TestSoundId', 'SavedOutcome'}
    if not required.issubset(table.columns):
        raise ValueError('Missing per-trial light/sound identities or saved outcomes.')
    aliases = {'hit': 'HIT', 'miss': 'MISS', 'correct': 'CR', 'correctrejection': 'CR',
               'cr': 'CR', 'falsealarm': 'FA', 'fa': 'FA'}
    records = []
    unknown_sources = unknown_outcomes = blanks = 0
    for _, row in table.iterrows():
        if row.SampleSoundId == row.TestSoundId == 0:
            blanks += 1
            continue
        raw_source = row.StimulusSource
        source = (raw_source.decode('utf-8') if isinstance(raw_source, bytes) else str(raw_source)).strip().lower()
        if source not in ('led', 'sound'):
            unknown_sources += 1
            continue
        raw = row.SavedOutcome
        raw = raw.decode('utf-8') if isinstance(raw, bytes) else str(raw)
        outcome = aliases.get(raw.strip().lower().replace(' ', '').replace('_', ''))
        if outcome is None:
            unknown_outcomes += 1
        records.append((source, row.SampleSoundId == row.TestSoundId, outcome))
    if not records or not any(record[2] is not None for record in records):
        raise ValueError('No eligible Light or Sound trials with recognized saved outcomes.')
    stats = {}
    for source, label in (('led', 'Light'), ('sound', 'Sound')):
        values = [record for record in records if record[0] == source]
        stats[label] = {}
        for index, metric in enumerate(METRICS):
            eligible = [r for r in values if r[2] is not None and (index == 0 or r[1] == (index == 1))]
            correct = sum(r[2] == ('HIT' if r[1] else 'CR') for r in eligible)
            count = len(eligible)
            stats[label][metric] = dict(correct=correct, n=count, percent=100*correct/count if count else float('nan'))
    return dict(file=str(Path(path)), session_start_time=session.get('session_start_time'), stats=stats,
                excluded=dict(blanks=blanks, unknown_sources=unknown_sources, unknown_outcomes=unknown_outcomes))


def plot_modality_sessions(results):
    if not results:
        raise ValueError('Run L&S batch analysis first.')
    sessions = sorted(results, key=session_sort_key)
    figure = Figure(figsize=(max(11, len(sessions)*.6), 9))
    axes = figure.subplots(3, 1, sharex=True)
    x = np.arange(1, len(sessions)+1)
    for ax, metric in zip(axes, METRICS):
        for label, color in (('Light', '#59A14F'), ('Sound', '#4C78A8')):
            points = [s['stats'][label][metric] for s in sessions]
            ax.plot(x, [p['percent'] for p in points], marker='o', color=color, label=label)
            for index, point in zip(x, points):
                if point['n']:
                    ax.annotate(f"n={point['n']}", (index, point['percent']),
                                xytext=(0, 7 if label == 'Light' else -13), textcoords='offset points',
                                ha='center', fontsize=7, color=color)
        ax.set(title=metric, ylabel='Performance (%)', ylim=(-5, 110))
        ax.set_yticks(range(0, 101, 20)); ax.grid(axis='y', alpha=.2); ax.legend(loc='best')
    axes[-1].set_xticks(x, [f"{i}. {Path(s['file']).stem}\n{s.get('session_start_time') or 'Unknown time'}" for i,s in enumerate(sessions,1)],
                        rotation=45, ha='right', fontsize=8)
    axes[-1].set_xlabel('NWB sessions (chronological; unknown times last)')
    figure.suptitle('Light vs Sound performance across files')
    figure.text(.5, .015, 'Saved outcomes; blanks and unknown modality/outcomes excluded. Missing trial categories remain gaps.\n'
                 'Overall accuracy: HIT on match trials and CR on non-match trials. n = eligible trials.', ha='center', fontsize=8)
    figure.tight_layout(rect=(0,.065,1,.96))
    return figure
