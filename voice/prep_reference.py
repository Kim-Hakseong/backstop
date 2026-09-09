"""Turn a raw voice recording into a reference clip ZipVoice can use.

The model conditions on one short clip, so the clip does the work: mono, no
leading room tone, no clipping, and long enough to carry the timbre but short
enough that the duration predictor stays sane. 8-15 seconds is the band that
behaves; the checks below report anything that would quietly degrade the clone
rather than fail loudly.
"""

import argparse
import sys

import numpy as np
import soundfile as sf

TARGET_SR = 24000
GOOD_SECONDS = (8.0, 15.0)


def load(path):
    """Read the recording, falling back to PyAV for phone formats.

    libsndfile handles wav and flac and, on recent builds, mp3 -- but not the
    AAC inside an .m4a, which is what a phone voice memo actually is. PyAV ships
    its own ffmpeg, so this stays a pip install rather than a system dependency.
    """
    try:
        return sf.read(path, dtype="float32", always_2d=False)
    except Exception:
        import av

        with av.open(path) as container:
            stream = container.streams.audio[0]
            resampler = av.AudioResampler(format="fltp", layout="mono",
                                          rate=stream.codec_context.sample_rate)
            chunks = []
            for frame in container.decode(stream):
                for out in resampler.resample(frame):
                    chunks.append(out.to_ndarray().reshape(-1))
            return np.concatenate(chunks), stream.codec_context.sample_rate


def to_mono(x):
    return x if x.ndim == 1 else x.mean(axis=1)


def resample(x, sr_in, sr_out):
    if sr_in == sr_out:
        return x
    n = int(round(len(x) * sr_out / sr_in))
    return np.interp(
        np.linspace(0.0, len(x) - 1, n, dtype=np.float64),
        np.arange(len(x), dtype=np.float64),
        x.astype(np.float64),
    ).astype(np.float32)


def trim_silence(x, sr, threshold_db=-40.0, pad_ms=80):
    """Drop leading/trailing room tone, keeping a short pad on each side."""
    win = max(1, int(sr * 0.02))
    frames = len(x) // win
    if frames == 0:
        return x
    rms = np.sqrt((x[: frames * win].reshape(frames, win) ** 2).mean(axis=1) + 1e-12)
    loud = rms > (10 ** (threshold_db / 20.0)) * rms.max()
    if not loud.any():
        return x
    pad = int(sr * pad_ms / 1000)
    start = max(0, np.argmax(loud) * win - pad)
    end = min(len(x), (frames - np.argmax(loud[::-1])) * win + pad)
    return x[start:end]


def normalize(x, target_rms=0.06, peak_ceiling=0.95):
    rms = float(np.sqrt((x ** 2).mean() + 1e-12))
    x = x * (target_rms / rms)
    peak = float(np.abs(x).max())
    if peak > peak_ceiling:
        x = x * (peak_ceiling / peak)
    return x.astype(np.float32)


def inspect(x, sr, clipped_fraction):
    """Report the things that make a clone come out wrong."""
    seconds = len(x) / sr
    notes = []
    if seconds < GOOD_SECONDS[0]:
        notes.append(f"clip is {seconds:.1f}s, shorter than {GOOD_SECONDS[0]:.0f}s "
                     "-- the clone will sound thin")
    elif seconds > GOOD_SECONDS[1]:
        notes.append(f"clip is {seconds:.1f}s, longer than {GOOD_SECONDS[1]:.0f}s "
                     "-- trim it with --start/--seconds, generation slows down")
    if clipped_fraction > 5e-4:
        notes.append(f"{clipped_fraction * 100:.2f}% of the source sits at full "
                     "scale -- re-record with lower input gain")

    # crude noise floor: the quietest 10% of 20 ms frames against the loudest
    win = max(1, int(sr * 0.02))
    frames = len(x) // win
    if frames > 10:
        rms = np.sqrt((x[: frames * win].reshape(frames, win) ** 2).mean(axis=1) + 1e-12)
        floor_db = 20 * np.log10(np.percentile(rms, 10) / (rms.max() + 1e-12) + 1e-12)
        spread_db = 20 * np.log10(np.percentile(rms, 95) /
                                  (np.percentile(rms, 5) + 1e-12) + 1e-12)
        if spread_db < 15:
            notes.append(f"the envelope only spans {spread_db:.0f} dB -- the "
                         "recorder's automatic gain flattened the pauses, and the "
                         "clone inherits that compressed feel")
        elif floor_db > -35:
            notes.append(f"noise floor is {floor_db:.0f} dB below speech -- "
                         "record somewhere quieter, the clone will inherit the hiss")
    return seconds, notes


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("source")
    ap.add_argument("-o", "--out", default="voice/out/reference.wav")
    ap.add_argument("--start", type=float, default=0.0, help="seconds to skip")
    ap.add_argument("--seconds", type=float, default=None, help="length to keep")
    args = ap.parse_args()

    x, sr = load(args.source)
    clipped = float((np.abs(x) > 0.995).mean()) if x.size else 0.0
    x = resample(to_mono(x), sr, TARGET_SR)

    if args.start:
        x = x[int(args.start * TARGET_SR):]
    if args.seconds:
        x = x[: int(args.seconds * TARGET_SR)]

    x = normalize(trim_silence(x, TARGET_SR))
    seconds, notes = inspect(x, TARGET_SR, clipped)

    import os
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    sf.write(args.out, x, TARGET_SR)

    print(f"wrote {args.out}  {seconds:.1f}s mono {TARGET_SR} Hz")
    for note in notes:
        print(f"  warning: {note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
