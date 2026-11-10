"""First/last-session fork-duration distributions and means by trial type."""
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

COLORS = {'Go': '#4477AA', 'NoGo': '#CC6677'}


def _trial_types(trials):
    column = next((name for name in ('trial_type', 'TrialType', 'trialtype', 'Trial Type') if name in trials.columns), None)
    if column is None:
        raise ValueError('missing trial-type column (expected trial_type or TrialType)')
    def normalize(value):
        if isinstance(value, bytes):
            value = value.decode('utf-8', errors='replace')
        value = str(value).strip().lower().replace(' ', '').replace('_', '').replace('-', '')
        return {'go': 'Go', 'nogo': 'NoGo', '1': 'Go', '1.0': 'Go', '2': 'NoGo', '2.0': 'NoGo'}.get(value)
    return trials[column].map(normalize).to_numpy()


def plot_first_session_fork_durations(groups):
    """Keep the public entry point; compare sessions[0] and sessions[-1]."""
    records, skipped = {}, []
    for group, animals in groups.items():
        for animal, data in animals.items():
            for label, index in (("First session", 0), ("Last session", -1)):
                try:
                    sessions = data['sessions']
                    if not sessions:
                        raise ValueError('no sessions')
                    trials = sessions[index]['trials']
                    durations = pd.to_numeric(trials['fork_duration_ms'], errors='coerce').to_numpy(dtype=float, na_value=np.nan)
                    types = _trial_types(trials)
                    valid = np.isfinite(durations) & (durations >= 0)
                    known = np.isin(types, ['Go', 'NoGo'])
                    keep = valid & known
                    if not keep.any():
                        raise ValueError('no finite non-negative fork durations with known trial types')
                    by_type = {kind: durations[valid & (types == kind)] for kind in COLORS}
                    records[(group, animal, label)] = dict(values=durations[keep], excluded=int((~keep).sum()),
                        unknown_trial_types=int((~known).sum()), by_trial_type=by_type, only_session=len(sessions)==1,
                        means={kind: float(values.mean()) if len(values) else float('nan') for kind,values in by_type.items()})
                except (KeyError, TypeError, ValueError, IndexError, AttributeError) as exc:
                    skipped.append(f'{group} / {animal} / {label}: {exc}')
    if not records:
        raise ValueError('No fork durations with trial types found. ' + '; '.join(skipped[:5]))
    bins = np.histogram_bin_edges(np.concatenate([r['values'] for r in records.values()]), bins=30)
    figures = []
    for group, group_animals in groups.items():
        if not any(key[0] == group for key in records):
            continue
        animals = list(group_animals)
        fig,axes=plt.subplots(2,len(animals),figsize=(4.5*len(animals),7),squeeze=False,sharex=True,sharey=True)
        for row,label in enumerate(('First session','Last session')):
            for column,animal in enumerate(animals):
                ax=axes[row,column]
                record=records.get((group,animal,label))
                ax.set_title(str(animal) + (' (only session)' if record and record['only_session'] else ''))
                ax.set_xlabel('Fork duration (ms)')
                if column == 0:
                    ax.set_ylabel(label + '\nTrials within type (%)')
                if record is None:
                    ax.text(.5,.5,'No valid data',ha='center',va='center',transform=ax.transAxes)
                    continue
                for kind,color in COLORS.items():
                    values=record['by_trial_type'][kind]
                    if not len(values):
                        ax.plot([], [], color=color, label=f'{kind}: no valid trials')
                        continue
                    mean=record['means'][kind]
                    ax.hist(values,bins=bins,weights=np.full(len(values),100/len(values)),
                            color=color,alpha=.4,edgecolor=color,label=f'{kind} (n={len(values)})')
                    ax.axvline(mean,color=color,ls='--',label=f'{kind} mean: {mean:.1f} ms')
                ax.legend(frameon=False,fontsize=8);ax.grid(axis='y',alpha=.2)
        fig.suptitle(f'{group} — first vs last session fork duration by trial type')
        fig.tight_layout(rect=(0,0,1,.95));figures.append(fig)

        fig,axes=plt.subplots(2,1,figsize=(max(6,len(animals)*1.1),8),layout='constrained',squeeze=False)
        x=np.arange(len(animals))
        for row,label in enumerate(('First session','Last session')):
            ax=axes[row,0]
            for offset,(kind,color) in zip((-.19,.19),COLORS.items()):
                means=[records.get((group,animal,label),{}).get('means',{}).get(kind,np.nan) for animal in animals]
                ax.bar(x+offset,means,width=.36,color=color,alpha=.75,label=kind)
                for position,mean,animal in zip(x+offset,means,animals):
                    if np.isfinite(mean):
                        record=records[(group,animal,label)]
                        ax.annotate(f"{mean:.1f}\nn={len(record['by_trial_type'][kind])}",
                                    (position,mean),xytext=(0,3),textcoords='offset points',ha='center',fontsize=8)
            ax.set_xticks(x,[str(animal) for animal in animals],rotation=30,ha='right')
            ax.set_ylabel('Mean fork duration (ms)')
            ax.set_title(label)
            ax.legend(frameon=False);ax.set_axisbelow(True);ax.grid(axis='y',alpha=.2);ax.margins(y=.2)
        fig.suptitle(f'{group} — mean duration by animal and trial type');figures.append(fig)
    return figures,records,skipped
