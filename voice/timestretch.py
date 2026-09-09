"""Change how long speech takes without changing its pitch.

ZipVoice's `speed` argument is a poor control surface: on this checkpoint 0.90
produced 6.66 s and 1.08 produced 2.43 s for the same sentence, and the
exponent keeps steepening. Rather than searching that cliff for every sentence,
generate once and fix the pacing here, where the factor applied is the factor
requested.

This is WSOLA -- overlap-add where each grain is nudged to the position that
correlates best with what the previous grain led into. The alignment search is
what keeps the pitch intact and stops the buzzing that plain overlap-add
produces on voiced speech.
"""

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

FRAME = 1024      # about 43 ms at 24 kHz, longer than a pitch period
TOLERANCE = 512   # how far a grain may slide to find its best fit


def stretch(x, factor, frame=FRAME, tolerance=TOLERANCE):
    """Return `x` lasting `factor` times as long. 1.5 slows down, 0.7 speeds up."""
    if abs(factor - 1.0) < 0.02 or len(x) < 4 * frame:
        return x

    hop_out = frame // 2
    hop_in = max(1, int(round(hop_out / factor)))
    window = np.hanning(frame).astype(np.float32)

    out = np.zeros(int(len(x) * factor) + 2 * frame, dtype=np.float32)
    weight = np.zeros_like(out)

    # what the previously placed grain naturally ran into; the next grain is
    # chosen to continue it rather than to sit at an arbitrary phase
    expected = None
    read = 0
    write = 0

    while read + frame + tolerance < len(x) and write + frame < len(out):
        if expected is None:
            best = read
        else:
            lo = max(0, read - tolerance)
            hi = min(len(x) - frame, read + tolerance)
            if hi <= lo:
                best = max(0, min(read, len(x) - frame))
            else:
                candidates = sliding_window_view(x[lo:hi + frame], frame)
                best = lo + int(np.argmax(candidates @ expected))

        out[write:write + frame] += x[best:best + frame] * window
        weight[write:write + frame] += window

        tail = x[best + hop_out:best + hop_out + frame]
        expected = tail if len(tail) == frame else None

        read += hop_in
        write += hop_out

    end = write + frame
    weight[weight < 1e-6] = 1.0
    return (out[:end] / weight[:end]).astype(np.float32)


def to_pace(x, sr, words, target_wps, limit=2.2):
    """Stretch `x` so it reads at `target_wps`, refusing implausible factors."""
    seconds = len(x) / sr
    factor = (words / target_wps) / seconds
    factor = float(np.clip(factor, 1 / limit, limit))
    return stretch(x, factor), factor
