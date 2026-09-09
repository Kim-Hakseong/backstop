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


def calibrate(tts, text, prompt, audio, sr, steps, target_wps, speed, attempts=3):
    """Generate, measure the pace, and retry at a corrected speed.

    Duration responds to `speed` faster than linearly -- empirically close to
    speed**-2 -- so the correction is damped by that exponent instead of applying
    the duration ratio directly, which overshoots into a drawl.
    """
    words = max(1, len(text.split()))
    best = None
    for _ in range(attempts):
        out = tts.generate(text, prompt, audio, sr, speed=speed, num_steps=steps)
        seconds = len(out.samples) / out.sample_rate
        wps = words / seconds
        error = abs(wps - target_wps)
        if best is None or error < best[0]:
            best = (error, out, speed, wps)
        if error <= WPS_TOLERANCE:
            break
        speed = max(0.3, min(1.6, speed * (wps / target_wps) ** -0.5))
    return best[1], best[2], best[3]


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
    ap.add_argument("--threads", type=int, default=os.cpu_count() or 4)
    ap.add_argument("--steps", type=int, default=16,
                    help="flow-matching steps; 8 is fast, 32 is smoother")
    ap.add_argument("--speed", type=float, default=0.8,
                    help="starting speed; pacing is corrected from here")
    ap.add_argument("--wps", type=float, default=NATURAL_WPS,
                    help="target words per second; 2.6 is unhurried narration")
    ap.add_argument("--guidance", type=float, default=1.5,
                    help="classifier-free guidance; higher tracks the text harder")
    ap.add_argument("--no-calibrate", action="store_true",
                    help="use --speed as given, do not measure and retry")
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
    items = ([{"id": "single", "text": args.text}] if args.text
             else spec["samples"])

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
            if args.no_calibrate:
                out = tts.generate(chunk, prompt, audio, sr,
                                   speed=args.speed, num_steps=args.steps)
                wps = len(chunk.split()) / (len(out.samples) / out.sample_rate)
            else:
                out, _, wps = calibrate(tts, chunk, prompt, audio, sr,
                                        args.steps, args.wps, args.speed)
            rate = out.sample_rate
            if index:
                pieces.append(np.zeros(int(SENTENCE_PAUSE * rate), dtype=np.float32))
            pieces.append(np.array(out.samples, dtype=np.float32))

        samples = np.concatenate(pieces)
        elapsed = time.time() - started
        seconds = len(samples) / rate
        words = len(item["text"].split())

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
