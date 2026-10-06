"""Speak arbitrary text in the voice of a reference recording.

ZipVoice is zero-shot: it never trains on the reference, it conditions on one
clip plus that clip's transcript and imitates the timbre. That is what makes the
cross-lingual trick work -- record yourself in Korean, hand it English text, and
the English comes out in your voice.

The transcript matters as much as the audio. It is romanized before it reaches
the model (see romanize.py for why), and it has to match what was actually said:
the model divides prompt audio by prompt tokens to guess your speaking rate, so
a transcript that drifts from the recording stretches or crushes every sample.
"""

import argparse
import json
import os
import re
import sys
import time

import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from romanize import romanize  # noqa: E402

DEFAULT_MODEL = "voice/models/sherpa-onnx-zipvoice-distill-zh-en-emilia"


# A natural English narration sits near 2.6 words per second (about 155 wpm).
# ZipVoice does not know that: it estimates speaking rate as prompt audio length
# divided by prompt token count, and a romanized Korean prompt inflates the token
# count badly -- "annyeonghaseyo" is fourteen Latin characters for five syllables,
# and espeak reads every one of them. The rate comes out roughly 70% too fast, so
# the pacing is measured and corrected rather than trusted.
NATURAL_WPS = 2.6
WPS_TOLERANCE = 0.15
SENTENCE_PAUSE = 0.32  # seconds of silence between sentences


def split_sentences(text):
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p for p in parts if p]


def probe_duration(tts, text, prompt, audio, sr, speed):
    """Length of the audio this speed would produce, generated as cheaply as possible.

    Duration is decided before the flow-matching sampler runs, so it does not
    depend on the step count: 2 steps and 16 steps return byte-identical lengths.
    That makes a 2-step probe a free measurement of what a 16-step generation
    will do, which is what lets the search below afford several iterations.
    """
    out = tts.generate(text, prompt, audio, sr, speed=speed, num_steps=2)
    return len(out.samples) / out.sample_rate


def pace_target(text, target_wps):
    """Seconds this text should take.

    Whitespace words are meaningless for Chinese and Japanese, where one line
    can be a single "word" and the pacing search then aims at nonsense. CJK
    characters are counted individually and priced at a syllable each, which is
    roughly what they are; Latin words are priced at 1.6 syllables.
    """
    cjk = sum(1 for c in text if "\u3040" <= c <= "\u30ff" or "\u4e00" <= c <= "\u9fff")
    words = len([w for w in text.split() if any(ch.isalpha() for ch in w)])
    syllables = cjk + 1.6 * words
    return syllables / (target_wps * 1.6)


def fit_speed(tts, text, prompt, audio, sr, target_wps, lo=0.5, hi=1.6, iters=7,
              target_seconds=None):
    """Bisect for the speed that lands this sentence on the target pace.

    `speed` is a violent knob on this checkpoint -- on one test sentence 0.90
    gave 6.66 s and 1.08 gave 2.43 s, a 2.7x swing for a 20% input change, and
    the exponent keeps steepening. Nothing derived from a single measurement
    survives that, and one speed shared across sentences produced a set ranging
    from 2.4 to 4.7 words per second. Duration is monotone in speed though, so
    bisection is stable where extrapolation is not.
    """
    target = target_seconds or pace_target(text, target_wps)
    for _ in range(iters):
        mid = (lo + hi) / 2
        if probe_duration(tts, text, prompt, audio, sr, mid) > target:
            lo = mid  # still too slow, push speed up
        else:
            hi = mid
    return (lo + hi) / 2


def best_take(tts, text, prompt, audio, sr, speed, steps, takes, judge, reference):
    """Generate `takes` candidates and keep the one that sounds most like the
    reference speaker.

    Zero-shot cloning is not repeatable. Generating the same sentence three
    times from the same clip produced speaker similarities of 0.74, 0.32 and
    0.32 -- the spread between takes of one setting was larger than the spread
    between 4-second and 18-second reference clips. Averaging that away is not
    an option when the deliverable is a single file, so the fix is to draw
    several and keep the best one.
    """
    if takes <= 1 or judge is None:
        return tts.generate(text, prompt, audio, sr, speed=speed, num_steps=steps)

    from similarity import embed, similarity

    best, best_score = None, -2.0
    for _ in range(takes):
        out = tts.generate(text, prompt, audio, sr, speed=speed, num_steps=steps)
        score = similarity(reference,
                           embed(judge, np.array(out.samples, dtype=np.float32),
                                 out.sample_rate))
        if score > best_score:
            best, best_score = out, score
    print("    best of %d takes: similarity %.3f" % (takes, best_score))
    return best


def build_tts(model_dir, threads, guidance):
    import sherpa_onnx as so

    lexicon = os.path.join(model_dir, "lexicon.txt")
    if not os.path.exists(lexicon):
        raise SystemExit(f"missing {lexicon} -- run voice/bootstrap.sh first")

    config = so.OfflineTtsConfig(
        model=so.OfflineTtsModelConfig(
            zipvoice=so.OfflineTtsZipvoiceModelConfig(
                tokens=os.path.join(model_dir, "tokens.txt"),
                encoder=os.path.join(model_dir, "text_encoder.onnx"),
                decoder=os.path.join(model_dir, "fm_decoder.onnx"),
                vocoder=os.path.join(model_dir, "vocos_24khz.onnx"),
                data_dir=os.path.join(model_dir, "espeak-ng-data"),
                lexicon=lexicon,
                guidance_scale=guidance,
            ),
            num_threads=threads,
            provider="cpu",
        )
    )
    return so.OfflineTts(config)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--reference", default="voice/out/reference.wav",
                    help="clip from prep_reference.py")
    ap.add_argument("--samples", default="voice/samples.json")
    ap.add_argument("--out-dir", default="voice/out/samples")
    ap.add_argument("--model-dir", default=DEFAULT_MODEL)
    ap.add_argument("--prompt-text", default=None,
                    help="what the reference says; overrides samples.json")
    ap.add_argument("--prompt-romaja", default=None,
                    help="hand-written romanization, skips romanize.py")
    ap.add_argument("--text", default=None, help="synthesize one line and exit")
    ap.add_argument("--seconds", type=float, default=None,
                    help="target duration for --text, overriding the pace model")
    ap.add_argument("--threads", type=int, default=os.cpu_count() or 4)
    ap.add_argument("--takes", type=int, default=1,
                    help="candidates per sentence; the closest to the reference wins")
    ap.add_argument("--steps", type=int, default=16,
                    help="flow-matching steps; 8 is fast, 32 is smoother")
    ap.add_argument("--speed", type=float, default=1.0,
                    help="fixed speed, only used with --no-calibrate")
    ap.add_argument("--wps", type=float, default=NATURAL_WPS,
                    help="target words per second; 2.6 is unhurried narration")
    ap.add_argument("--guidance", type=float, default=1.5,
                    help="classifier-free guidance; higher tracks the text harder")
    ap.add_argument("--no-calibrate", action="store_true",
                    help="use --speed as given, skip the pacing search")
    ap.add_argument("--whole", action="store_true",
                    help="one pass over the whole text instead of per sentence")
    args = ap.parse_args()

    spec = json.load(open(args.samples, encoding="utf-8"))
    prompt_text = args.prompt_text or spec["prompt_text"]
    prompt = args.prompt_romaja or romanize(prompt_text)

    if any("가" <= c <= "힣" for c in prompt):
        raise SystemExit("prompt transcript still contains Hangul after romanizing")

    audio, sr = sf.read(args.reference, dtype="float32", always_2d=False)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    print(f"reference: {args.reference}  {len(audio) / sr:.1f}s @ {sr} Hz")
    print(f"prompt:    {prompt}\n")

    tts = build_tts(args.model_dir, args.threads, args.guidance)

    judge = reference = None
    if args.takes > 1:
        from similarity import extractor, embed
        judge = extractor(threads=args.threads)
        reference = embed(judge, audio, sr)
    items = ([{"id": "single", "text": args.text, "seconds": args.seconds}]
             if args.text else spec["samples"])

    # The checkpoint is Chinese/English. Korean target text is dropped token by
    # token and comes back as a fraction of a second of noise, so romanize it
    # too: espeak reads the Latin spelling and the result lands close enough to
    # Korean, in the reference voice.
    for item in items:
        if any("\uac00" <= c <= "\ud7a3" for c in item["text"]):
            item["text"] = romanize(item["text"])

    os.makedirs(args.out_dir, exist_ok=True)
    manifest = []
    for item in items:
        started = time.time()

        # Sentence by sentence, with real silence between them. One long pass
        # runs every clause together at a uniform pace, which is what makes the
        # result sound stitched rather than spoken.
        chunks = [item["text"]] if args.whole else split_sentences(item["text"])
        pieces, rate = [], 24000
        for index, chunk in enumerate(chunks):
            share = item.get("seconds")
            if share:
                share = share * pace_target(chunk, args.wps) / max(
                    1e-6, sum(pace_target(c, args.wps) for c in chunks))
            speed = (args.speed if args.no_calibrate else
                     fit_speed(tts, chunk, prompt, audio, sr, args.wps,
                               target_seconds=share))
            out = best_take(tts, chunk, prompt, audio, sr, speed, args.steps,
                            args.takes, judge, reference)
            rate = out.sample_rate
            if index:
                pieces.append(np.zeros(int(SENTENCE_PAUSE * rate), dtype=np.float32))
            pieces.append(np.array(out.samples, dtype=np.float32))

        samples = np.concatenate(pieces)
        elapsed = time.time() - started
        seconds = len(samples) / rate
        words = pace_target(item["text"], args.wps) * args.wps

        path = os.path.join(args.out_dir, f"{item['id']}.wav")
        sf.write(path, samples, rate)
        manifest.append({"id": item["id"], "text": item["text"], "path": path,
                         "seconds": round(seconds, 2),
                         "words_per_second": round(words / seconds, 2)})
        print(f"{item['id']:<12} {seconds:5.2f}s audio  {words / seconds:4.2f} w/s  "
              f"{elapsed:5.1f}s cpu  -> {path}")

    with open(os.path.join(args.out_dir, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
