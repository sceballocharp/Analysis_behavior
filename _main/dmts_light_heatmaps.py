"""Aggregate location dictionaries saved from DMTS voltage/performance maps."""
from pathlib import Path
import re
import numpy as np


def collect_location_maps(payloads):
    groups = {'performance': {}, 'voltage': {}}
    for filename, payload in payloads.items():
        name = Path(filename).stem.casefold()
        kind = 'performance' if 'performance' in name else 'voltage' if 'voltage' in name else None
        if kind is None:
            continue
        values = {}
        for position, value in payload.items():
            if not re.fullmatch(r'P(?:10|[1-9])N(?:10|[1-9])', position):
                continue
            if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            if not np.isfinite(value) or (kind == 'performance' and not 0 <= value <= 100):
                continue
            values[position] = float(value)
        if values:
            groups[kind][filename] = values
    return groups


def plot_location_maps(maps, kind, title='', cmap='viridis', cmin=2, cmax=5):
    from dmts_voltage_viewer import plot_voltage_position_heatmap
    if not maps:
        raise ValueError(f'No valid {kind} location dictionaries were loaded.')
    performance = kind == 'performance'
    if performance:
         pcmin=0 
         pcmax=100
    else:
        pcmin=2
        pcmax=5 
    fig = plot_voltage_position_heatmap(maps, title=title,
                cmap=cmap,cmin = pcmin, cmax = pcmax)
    unit = 'Match hit rate (%)' if performance else 'Mean voltage (V)'
    fig.axes[0].set_title(f'{len(maps)} JSON files | {unit}')
    fig.heatmap_kind = 'performance_percent' if performance else 'voltage_V'
    if performance:
        for text in fig.axes[0].texts:
            text.set_text(f'{float(text.get_text()):.1f}%')
        fig.axes[1].set_ylabel(unit)
    fig.texts[-1].set_text('Each cell: mean of available file values at that location (equal weight per JSON file).\n'
                          'Gray: no valid data. P increases right; N increases up.')
    return fig
