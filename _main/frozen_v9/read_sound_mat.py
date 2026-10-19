"""Read waveforms from a MATLAB .mat file containing a 1x16 Sound cell.

Examples
--------
Inspect the Sound variable:
    python read_sound_mat.py path/to/file.mat

Save every waveform as a .npy file:
    python read_sound_mat.py path/to/file.mat --out sound_waveforms

Save every waveform as a .wav file if you know the sampling rate:
    python read_sound_mat.py path/to/file.mat --out sound_wavs --wav --fs 24414

Estimate the dominant frequency of sound number 3:
    python read_sound_mat.py path/to/file.mat --frequency --index 3 --fs 24414
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

import numpy as np


def _flatten_waveform(value) -> np.ndarray:
    """Convert one MATLAB cell entry into a 1D numeric waveform."""
    arr = np.asarray(value)

    # scipy.io.loadmat often wraps cell contents in singleton object arrays.
    while arr.dtype == object and arr.size == 1:
        arr = np.asarray(arr.item())

    return np.asarray(arr, dtype=float).squeeze()


def _load_with_scipy(mat_path: Path, variable: str) -> list[np.ndarray]:
    from scipy.io import loadmat

    mat = loadmat(mat_path, squeeze_me=False, struct_as_record=False)
    if variable not in mat:
        available = sorted(k for k in mat if not k.startswith("__"))
        raise KeyError(f"Variable {variable!r} not found. Available: {available}")

    sound_cell = np.asarray(mat[variable], dtype=object).ravel(order="F")
    return [_flatten_waveform(cell) for cell in sound_cell]


def _read_hdf5_reference(file_handle, value) -> np.ndarray:
    """Dereference MATLAB v7.3 cell entries stored as HDF5 object references."""
    import h5py

    if isinstance(value, h5py.Reference):
        value = file_handle[value]

    if hasattr(value, "shape") and hasattr(value, "dtype"):
        data = value[()]
    else:
        data = value

    if isinstance(data, np.ndarray) and data.dtype == object:
        data = np.array([_read_hdf5_reference(file_handle, x) for x in data.ravel()])

    return _flatten_waveform(data)


def _load_with_h5py(mat_path: Path, variable: str) -> list[np.ndarray]:
    import h5py

    with h5py.File(mat_path, "r") as mat:
        if variable not in mat:
            available = sorted(mat.keys())
            raise KeyError(f"Variable {variable!r} not found. Available: {available}")

        dataset = mat[variable]
        entries = dataset[()].ravel(order="F")
        return [_read_hdf5_reference(mat, entry) for entry in entries]


def load_sound_waveforms(mat_path: str | Path, variable: str = "Sound") -> list[np.ndarray]:
    """Load waveforms from a MATLAB cell variable."""
    path = Path(mat_path)
    try:
        return _load_with_scipy(path, variable)
    except NotImplementedError:
        # scipy raises this for MATLAB v7.3 files.
        return _load_with_h5py(path, variable)


def _save_npy(waveforms: Iterable[np.ndarray], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for idx, waveform in enumerate(waveforms, start=1):
        np.save(out_dir / f"sound_{idx:02d}.npy", waveform)


def _save_wav(waveforms: Iterable[np.ndarray], out_dir: Path, fs: int) -> None:
    from scipy.io.wavfile import write

    out_dir.mkdir(parents=True, exist_ok=True)
    for idx, waveform in enumerate(waveforms, start=1):
        write(out_dir / f"sound_{idx:02d}.wav", fs, waveform.astype(np.float32))


def estimate_dominant_frequency(
    waveform: np.ndarray,
    fs: int,
    min_freq: float = 20.0,
    max_freq: float | None = None,
) -> tuple[float, float]:
    """Return the strongest FFT frequency and its magnitude."""
    signal = np.asarray(waveform, dtype=float).squeeze()
    signal = signal[np.isfinite(signal)]

    if signal.size < 2:
        raise ValueError("Waveform is too short to estimate frequency.")

    signal = signal - np.mean(signal)
    window = np.hanning(signal.size)
    spectrum = np.abs(np.fft.rfft(signal * window))
    freqs = np.fft.rfftfreq(signal.size, d=1.0 / fs)

    if max_freq is None:
        max_freq = fs / 2

    keep = (freqs >= min_freq) & (freqs <= max_freq)
    if not np.any(keep):
        raise ValueError(
            f"No FFT bins found between {min_freq:g} and {max_freq:g} Hz."
        )

    kept_freqs = freqs[keep]
    kept_spectrum = spectrum[keep]
    peak_index = int(np.argmax(kept_spectrum))
    return float(kept_freqs[peak_index]), float(kept_spectrum[peak_index])


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read a MATLAB .mat file containing a Sound cell array of waveforms."
    )
    parser.add_argument("mat_file", type=Path, help="Path to the .mat file.")
    parser.add_argument(
        "--variable",
        default="Sound",
        help="Name of the MATLAB variable to read. Default: Sound.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="Optional output directory. Saves each waveform as sound_01.npy, etc.",
    )
    parser.add_argument(
        "--wav",
        action="store_true",
        help="Save .wav files instead of .npy files. Requires --fs.",
    )
    parser.add_argument(
        "--fs",
        type=int,
        help="Sampling rate in Hz, required when using --wav or --frequency.",
    )
    parser.add_argument(
        "--frequency",
        action="store_true",
        help="Estimate dominant frequency using an FFT.",
    )
    parser.add_argument(
        "--index",
        type=int,
        help="1-based Sound cell index for --frequency. If omitted, analyzes all sounds.",
    )
    parser.add_argument(
        "--min-freq",
        type=float,
        default=20.0,
        help="Lowest frequency to consider for --frequency. Default: 20 Hz.",
    )
    parser.add_argument(
        "--max-freq",
        type=float,
        help="Highest frequency to consider for --frequency. Default: Nyquist frequency.",
    )
    args = parser.parse_args()

    if args.wav and args.fs is None:
        parser.error("--wav requires --fs, for example: --wav --fs 24414")
    if args.frequency and args.fs is None:
        parser.error("--frequency requires --fs, for example: --frequency --fs 24414")

    waveforms = load_sound_waveforms(args.mat_file, variable=args.variable)

    print(f"Loaded {len(waveforms)} waveforms from {args.variable!r}")
    for idx, waveform in enumerate(waveforms, start=1):
        print(
            f"{idx:02d}: shape={waveform.shape}, "
            f"samples={waveform.size}, "
            f"min={np.nanmin(waveform):.6g}, max={np.nanmax(waveform):.6g}"
        )

    if args.out:
        if args.wav:
            _save_wav(waveforms, args.out, args.fs)
            print(f"Saved WAV files to {args.out}")
        else:
            _save_npy(waveforms, args.out)
            print(f"Saved NPY files to {args.out}")

    if args.frequency:
        if args.index is not None:
            if args.index < 1 or args.index > len(waveforms):
                parser.error(f"--index must be between 1 and {len(waveforms)}")
            selected = [(args.index, waveforms[args.index - 1])]
        else:
            selected = list(enumerate(waveforms, start=1))

        print("Dominant frequency estimates:")
        for idx, waveform in selected:
            freq, magnitude = estimate_dominant_frequency(
                waveform,
                fs=args.fs,
                min_freq=args.min_freq,
                max_freq=args.max_freq,
            )
            print(f"{idx:02d}: {freq:.3f} Hz (FFT magnitude {magnitude:.6g})")


if __name__ == "__main__":
    main()
