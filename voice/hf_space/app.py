"""Chatterbox Multilingual on a ZeroGPU Space, carrying over what the CPU
pipeline in this repo learned the hard way.

The one finding worth porting is that zero-shot cloning is not repeatable. The
same sentence from the same reference clip scored 0.74, 0.32 and 0.32 against
the speaker on the CPU pipeline -- one take sounds like the person, two do not,
and the spread between takes of one setting was larger than the spread between a
4-second and an 18-second reference. A single generation is a coin flip, so this
draws several and ranks them by speaker similarity.

That is cheap here and was not on CPU: best-of-6 cost 398 seconds there.

UNVERIFIED. Hugging Face is unreachable from the machine this was written on, so
none of it has been run. The Chatterbox call signature in particular is worth
checking against the current model card before trusting it.
"""

import numpy as np
import gradio as gr
import spaces
import torch
import torchaudio

# Chatterbox states 23; these are the ones worth offering first. Check the model
# card for the current list -- language_id codes may differ from these strings.
LANGUAGES = {
    "English": "en", "한국어": "ko", "日本語": "ja", "中文": "zh",
    "Français": "fr", "Deutsch": "de", "Español": "es", "Italiano": "it",
    "Português": "pt", "Русский": "ru", "हिन्दी": "hi", "العربية": "ar",
}

model = None
verifier = None


def load():
    """Loaded once, inside the GPU worker: ZeroGPU has no GPU at import time."""
    global model, verifier
    if model is None:
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS
        model = ChatterboxMultilingualTTS.from_pretrained(device="cuda")
    if verifier is None:
        from speechbrain.inference.speaker import EncoderClassifier
        verifier = EncoderClassifier.from_hparams(
            source="speechbrain/spkrec-ecapa-voxceleb",
            savedir="/tmp/ecapa",
            run_opts={"device": "cuda"},
        )
    return model, verifier


def embed(verifier, wav, sr):
    """Speaker embedding at the 16 kHz the verifier expects."""
    tensor = torch.as_tensor(wav, dtype=torch.float32).unsqueeze(0)
    if sr != 16000:
        tensor = torchaudio.functional.resample(tensor, sr, 16000)
    with torch.no_grad():
        return verifier.encode_batch(tensor.cuda()).squeeze()


def similarity(a, b):
    return float(torch.nn.functional.cosine_similarity(a, b, dim=-1))


@spaces.GPU(duration=180)
def synthesize(reference, text, language, takes, exaggeration, cfg_weight):
    if not reference:
        raise gr.Error("Upload 10-15 seconds of your voice first.")
    if not text.strip():
        raise gr.Error("Enter some text.")

    tts, verifier = load()

    ref_wav, ref_sr = torchaudio.load(reference)
    target = embed(verifier, ref_wav.mean(dim=0).numpy(), ref_sr)

    best, best_score, scores = None, -2.0, []
    for _ in range(int(takes)):
        wav = tts.generate(
            text,
            language_id=LANGUAGES[language],
            audio_prompt_path=reference,
            exaggeration=exaggeration,
            cfg_weight=cfg_weight,
        )
        samples = wav.squeeze(0).cpu().numpy()
        score = similarity(target, embed(verifier, samples, tts.sr))
        scores.append(score)
        if score > best_score:
            best, best_score = samples, score

    report = "  ".join(f"{s:.3f}" for s in sorted(scores, reverse=True))
    return (tts.sr, best), f"best {best_score:.3f} of {int(takes)} — all takes: {report}"


with gr.Blocks(title="Your voice, other languages") as demo:
    gr.Markdown(
        "# Your voice, other languages\n"
        "Upload 10-15 seconds of yourself speaking any language, then write "
        "text in another. Recording longer does not help: reference clips of "
        "4 to 18 seconds scored the same. Drawing more takes does."
    )
    with gr.Row():
        with gr.Column():
            reference = gr.Audio(label="Your voice (10-15 s)", type="filepath")
            language = gr.Dropdown(list(LANGUAGES), value="English", label="Output language")
            text = gr.Textbox(label="Text to speak", lines=4)
            takes = gr.Slider(1, 10, value=5, step=1, label="Takes (best one is kept)")
            with gr.Accordion("Advanced", open=False):
                exaggeration = gr.Slider(0.0, 1.0, value=0.5, label="Expressiveness")
                cfg_weight = gr.Slider(0.0, 1.0, value=0.5, label="Guidance")
            go = gr.Button("Generate", variant="primary")
        with gr.Column():
            audio = gr.Audio(label="Result")
            report = gr.Textbox(label="Speaker similarity", interactive=False)

    go.click(synthesize,
             [reference, text, language, takes, exaggeration, cfg_weight],
             [audio, report])

demo.queue().launch()
