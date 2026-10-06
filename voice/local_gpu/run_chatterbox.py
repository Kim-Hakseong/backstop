"""Narrate a script in your own voice with Chatterbox, on a local CUDA box.

This exists because the container the rest of this repo was built in cannot
reach huggingface.co -- the egress policy rejects it -- and every Chatterbox
weight lives there. A machine with its own GPU can reach it, so the better model
runs there and the CPU pipeline in voice/ stays the fallback.

Two findings from the CPU work carry over.

Zero-shot cloning is not repeatable. The same sentence from the same reference
clip scored 0.74, 0.32 and 0.32 against the speaker -- one take sounds like the
person, two do not. A single generation is a coin flip, so this draws several
per sentence and keeps the one closest to the reference. On a 3060 that is cheap
enough to leave on.

A longer reference clip does not help, which was measured and found false the
other way round: clips of 4 to 18.6 seconds averaged 0.458 to 0.518, and the
spread between takes of one setting was wider than the spread between clip
lengths. Record 10-15 seconds somewhere quiet; spend the rest on takes.

The `seconds` field is for replacing narration in a video that is already cut.
A clip generated freely will not match the length the edit expects, so each
segment is time-stretched onto its target with WSOLA, which preserves pitch.

UNVERIFIED: written on a machine that cannot reach Hugging Face, so none of this
has been run. Check the Chatterbox call signature against the current model card.

    python run_chatterbox.py --reference my_voice.m4a --script narration.json
"""

import argparse
import json
import os
import sys
import time

import numpy as np
import soundfile as sf
import torch
import torchaudio

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from timestretch import stretch  # noqa: E402


def pick_device(requested):
    if requested != "auto":
        return requested
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def patch_torch_load(device):
    """Chatterbox loads CUDA-serialised checkpoints without a map_location.

    Harmless on CUDA; on MPS or CPU the load raises instead of falling back, so
    the default is filled in here.
    """
    if device == "cuda":
        return
    original = torch.load

    def load(*args, **kwargs):
        kwargs.setdefault("map_location", torch.device(device))
        return original(*args, **kwargs)

    torch.load = load


def load_model(device, multilingual):
    # For English, prefer the English-only checkpoint: the multilingual one
    # spreads capacity across 23 languages and English is not where it wins.
    if multilingual:
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS as Model
    else:
        from chatterbox.tts import ChatterboxTTS as Model
    return Model.from_pretrained(device=device)


def load_verifier():
    from speechbrain.inference.speaker import EncoderClassifier

    # Tiny model, and it runs while the GPU is busy generating. Keep it on CPU.
    return EncoderClassifier.from_hparams(
        source="speechbrain/spkrec-ecapa-voxceleb",
        savedir=os.path.expanduser("~/.cache/ecapa"),
        run_opts={"device": "cpu"},
    )


def embed(verifier, samples, sr):
    tensor = torch.as_tensor(np.asarray(samples, dtype=np.float32)).unsqueeze(0)
    if sr != 16000:
        tensor = torchaudio.functional.resample(tensor, sr, 16000)
    with torch.no_grad():
        return verifier.encode_batch(tensor).squeeze()


def similarity(a, b):
    return float(torch.nn.functional.cosine_similarity(a, b, dim=-1))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--reference", required=True, help="10-15 s of your voice")
    ap.add_argument("--script", required=True, help="JSON with a samples list")
    ap.add_argument("--out-dir", default="out")
    ap.add_argument("--language", default="en")
    ap.add_argument("--multilingual", action="store_true",
                    help="use the 23-language model; skip it for English")
    ap.add_argument("--takes", type=int, default=8)
    ap.add_argument("--device", default="auto",
                    choices=["auto", "cuda", "mps", "cpu"])
    ap.add_argument("--exaggeration", type=float, default=0.5,
                    help="0.3 reads flat and newsy, 0.7 performs")
    ap.add_argument("--cfg-weight", type=float, default=0.5,
                    help="lower slows the delivery down")
    ap.add_argument("--match-duration", action="store_true",
                    help="stretch each segment onto its `seconds` field")
    ap.add_argument("--stretch-limit", type=float, default=1.25,
                    help="refuse to stretch further than this either way")
    args = ap.parse_args()

    device = pick_device(args.device)
    patch_torch_load(device)
    print(f"device: {device}")
    if device == "cuda":
        print(f"gpu:    {torch.cuda.get_device_name(0)}")

    tts = load_model(device, args.multilingual)
    verifier = load_verifier()

    ref_wav, ref_sr = torchaudio.load(args.reference)
    target_voice = embed(verifier, ref_wav.mean(dim=0).numpy(), ref_sr)
    print(f"reference: {args.reference}  {ref_wav.shape[-1] / ref_sr:.1f}s\n")

    spec = json.load(open(args.script, encoding="utf-8"))
    os.makedirs(args.out_dir, exist_ok=True)

    manifest = []
    for item in spec["samples"]:
        started = time.time()
        best, best_score, scores = None, -2.0, []

        for _ in range(args.takes):
            kwargs = dict(audio_prompt_path=args.reference,
                          exaggeration=args.exaggeration,
                          cfg_weight=args.cfg_weight)
            if args.multilingual:
                kwargs["language_id"] = args.language
            wav = tts.generate(item["text"], **kwargs)

            samples = wav.squeeze(0).detach().cpu().numpy().astype(np.float32)
            score = similarity(target_voice, embed(verifier, samples, tts.sr))
            scores.append(score)
            if score > best_score:
                best, best_score = samples, score

        note = ""
        wanted = item.get("seconds")
        if args.match_duration and wanted:
            factor = wanted / (len(best) / tts.sr)
            clamped = float(np.clip(factor, 1 / args.stretch_limit, args.stretch_limit))
            best = stretch(best, clamped)
            note = f"  stretch x{clamped:.2f}"
            if abs(clamped - factor) > 0.01:
                note += f" (wanted x{factor:.2f}; rewrite this line shorter)"

        path = os.path.join(args.out_dir, f"{item['id']}.wav")
        sf.write(path, best, tts.sr)

        seconds = len(best) / tts.sr
        words = len(item["text"].split())
        manifest.append({"id": item["id"], "text": item["text"], "path": path,
                         "seconds": round(seconds, 2),
                         "target_seconds": wanted,
                         "words_per_second": round(words / seconds, 2),
                         "similarity": round(best_score, 3),
                         "all_takes": sorted((round(s, 3) for s in scores), reverse=True)})
        print(f"{item['id']:<12} {seconds:5.2f}s  {words / seconds:4.2f} w/s  "
              f"sim {best_score:.3f} of {args.takes}  ({time.time() - started:4.1f}s)"
              f"{note}")

    with open(os.path.join(args.out_dir, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)

    total = sum(m["seconds"] for m in manifest)
    worst = min(manifest, key=lambda m: m["similarity"])
    print(f"\n{len(manifest)} segments, {total:.1f}s of narration")
    print(f"weakest segment: {worst['id']} at {worst['similarity']:.3f} "
          f"-- regenerate it with more takes if it sounds off")


if __name__ == "__main__":
    main()
