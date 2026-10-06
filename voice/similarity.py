"""Score how much a generated clip sounds like the person in the reference.

Listening is the real test, but it does not scale and it drifts. A speaker
verification embedding does not care what was said or in what language -- it
maps a clip to a point that is close for the same speaker and far for a
different one -- so cosine distance between reference and output is a stable
way to compare two settings without re-listening to both.

Read the numbers as relative, not absolute. Useful as a comparison between runs;
not a threshold to certify a clone against.
"""

import numpy as np
import soundfile as sf

MODEL = "voice/models/3dspeaker_speech_campplus_sv_en_voxceleb_16k.onnx"


def extractor(model=MODEL, threads=4):
    import sherpa_onnx as so

    return so.SpeakerEmbeddingExtractor(
        so.SpeakerEmbeddingExtractorConfig(model=model, num_threads=threads,
                                           provider="cpu"))


def embed(ext, path_or_samples, sr=None):
    if isinstance(path_or_samples, str):
        samples, sr = sf.read(path_or_samples, dtype="float32", always_2d=False)
        if samples.ndim > 1:
            samples = samples.mean(axis=1)
    else:
        samples = path_or_samples
    stream = ext.create_stream()
    stream.accept_waveform(sr, samples)
    stream.input_finished()
    return np.array(ext.compute(stream), dtype=np.float32)


def similarity(a, b):
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))
