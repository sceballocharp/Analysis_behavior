"""Background discovery and status wording shared by Animal tabs."""
import os
from pathlib import Path


def scan_sessions(folder, kind, animal, cancel, messages):
    """Send directory-sized results; never access GUI objects from a worker."""
    required = {'parameters.dat', 'trialtype.bin', 'ttltrigsounds.bin', 'trial_log.csv'}
    count = 0
    def warning(exc):
        messages.put(('warning', f"Cannot read {exc.filename}: {exc.strerror}"))
    try:
        if not Path(folder).is_dir():
            raise ValueError(f"Folder unavailable: {folder}")
        for directory, dirs, files in os.walk(folder, onerror=warning, followlinks=False):
            if cancel.is_set():
                return
            dirs.sort(key=str.casefold)
            if kind == 'nwb':
                paths = [Path(directory) / name for name in sorted(files, key=str.casefold)
                         if Path(name).suffix.lower() == '.nwb']
            else:
                paths = [Path(directory)] if required.issubset({name.casefold() for name in files}) and animal.casefold() in directory.casefold() else []
            count += 1
            messages.put(('progress', (count, paths)))
    except Exception as exc:
        messages.put(('error', str(exc)))
    finally:
        messages.put(('done', None))


def discovery_status(directories, count, kind):
    unit = 'NWB files' if kind == 'nwb' else 'session folders'
    return f"Scanning: {directories} folders; {count} {unit}"


def discovery_complete(count, kind, warnings=0):
    unit = 'NWB file(s)' if kind == 'nwb' else 'session folder(s)'
    text = f"Search complete: {count} {unit} found." if count else f"No {unit} found."
    return text + (f" {warnings} warning(s); search may be incomplete." if warnings else '')


def batch_complete(successes, skipped):
    return f"Batch complete: {successes} sessions; {skipped} skipped."
