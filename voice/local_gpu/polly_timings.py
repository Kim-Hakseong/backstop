"""Read the narration timings out of a video that is already cut.

Replacing the voiceover in a finished edit is a timing problem, not a synthesis
problem. The cuts, the titles and the screen recording are all placed against
the old narration, so a new clip of a different length desynchronises everything
after it. This measures what the old narration actually does -- where each
spoken run starts and how long it lasts -- so the new segments can be generated
onto the same grid.

It splits on silence, so it finds spoken runs rather than sentences: a pause
mid-sentence starts a new segment, and two quick sentences may land in one. Read
the output as a starting point to merge by hand, not as a transcript.

    python polly_timings.py intro.mp4 > timings.json
    python polly_timings.py intro.mp4 --threshold -45dB --min-silence 0.5

Needs ffmpeg on PATH. Paste the segment list into your script JSON, add a
`text` for each, and generate with --match-duration.
"""

import argparse
import json
import re
import subprocess
import sys


def detect_silence(path, threshold, min_silence):
    """Return [(start, end)] of silent stretches, via ffmpeg's silencedetect."""
    result = subprocess.run(
        ["ffmpeg", "-i", path, "-af",
         f"silencedetect=noise={threshold}:d={min_silence}", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    if result.returncode != 0 and "silence_start" not in result.stderr:
        sys.exit(f"ffmpeg failed:\n{result.stderr[-800:]}")

    starts = [float(m) for m in re.findall(r"silence_start: ([\d.]+)", result.stderr)]
    ends = [float(m) for m in re.findall(r"silence_end: ([\d.]+)", result.stderr)]
    return list(zip(starts, ends + [None] * (len(starts) - len(ends))))


def duration(path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", path],
        capture_output=True, text=True,
    )
    return float(result.stdout.strip())


def speech_runs(silences, total, min_speech):
    """Invert the silences into spoken runs, dropping ones too short to be words."""
    runs, cursor = [], 0.0
    for start, end in silences:
        if start - cursor >= min_speech:
            runs.append((cursor, start))
        cursor = end if end is not None else total
    if total - cursor >= min_speech:
        runs.append((cursor, total))
    return runs


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("source", help="the cut video, or its audio track")
    ap.add_argument("--threshold", default="-40dB",
                    help="below this counts as silence; -45dB for noisy mixes")
    ap.add_argument("--min-silence", type=float, default=0.35,
                    help="seconds of quiet before a segment is considered over")
    ap.add_argument("--min-speech", type=float, default=0.6,
                    help="drop spoken runs shorter than this; they are usually breaths")
    args = ap.parse_args()

    total = duration(args.source)
    silences = detect_silence(args.source, args.threshold, args.min_silence)
    runs = speech_runs(silences, total, args.min_speech)

    samples = [{"id": "%02d_segment" % (i + 1),
                "text": "",
                "start": round(start, 2),
                "seconds": round(end - start, 2)}
               for i, (start, end) in enumerate(runs)]

    print(json.dumps({"source": args.source,
                      "total_seconds": round(total, 2),
                      "prompt_text": "",
                      "samples": samples}, indent=2, ensure_ascii=False))

    spoken = sum(s["seconds"] for s in samples)
    print(f"\n{len(samples)} spoken runs, {spoken:.1f}s of {total:.1f}s "
          f"({100 * spoken / total:.0f}% speech)", file=sys.stderr)
    print("Fill in `text` for each, then generate with --match-duration.",
          file=sys.stderr)


if __name__ == "__main__":
    main()
