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
import sys
import time

import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from romanize import romanize  # noqa: E402

DEFAULT_MODEL = "voice/models/sherpa-onnx-zipvoice-distill-zh-en-emilia"


def build_tts(model_dir, threads):
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
    ap.add_argument("--steps", type=int, default=8,
                    help="flow-matching steps; 4 is fast, 16 is smoother")
    ap.add_argument("--speed", type=float, default=1.0)
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

    tts = build_tts(args.model_dir, args.threads)
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
        out = tts.generate(item["text"], prompt, audio, sr,
                           speed=args.speed, num_steps=args.steps)
        elapsed = time.time() - started
        seconds = len(out.samples) / out.sample_rate

        path = os.path.join(args.out_dir, f"{item['id']}.wav")
        sf.write(path, np.array(out.samples), out.sample_rate)
        manifest.append({"id": item["id"], "text": item["text"],
                         "path": path, "seconds": round(seconds, 2)})
        print(f"{item['id']:<12} {seconds:5.2f}s audio  "
              f"{elapsed:5.1f}s cpu  rtf {elapsed / seconds:.2f}  -> {path}")

    with open(os.path.join(args.out_dir, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
