#!/usr/bin/env bash
# Fetch the voice-cloning runtime. Everything here comes from PyPI and GitHub
# release assets on purpose: huggingface.co is blocked on some networks (it is
# on the sandbox this was built in), and every mainstream cloning checkpoint
# -- XTTS-v2, OpenVoice, Chatterbox, F5-TTS -- is HF-only.
set -euo pipefail

cd "$(dirname "$0")"
MODELS=models
ZIPVOICE=sherpa-onnx-zipvoice-distill-zh-en-emilia
BASE=https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models

mkdir -p "$MODELS"

if [ ! -d "$MODELS/$ZIPVOICE" ]; then
  echo "==> downloading $ZIPVOICE (about 600 MB)"
  curl -fL --retry 4 --retry-delay 2 -o "$MODELS/$ZIPVOICE.tar.bz2" "$BASE/$ZIPVOICE.tar.bz2"
  tar xjf "$MODELS/$ZIPVOICE.tar.bz2" -C "$MODELS"
  rm -f "$MODELS/$ZIPVOICE.tar.bz2"
fi

# sherpa-onnx wants `word phone phone ...`; the shipped pinyin.raw carries a
# log-probability in column two, which the lexicon loader reads as a phone and
# rejects one warning at a time -- tens of thousands of them. Strip the column.
if [ ! -f "$MODELS/$ZIPVOICE/lexicon.txt" ]; then
  echo "==> building lexicon.txt from pinyin.raw"
  awk '{printf "%s", $1; for (i = 3; i <= NF; i++) printf " %s", $i; print ""}' \
    "$MODELS/$ZIPVOICE/pinyin.raw" > "$MODELS/$ZIPVOICE/lexicon.txt"
fi

if [ ! -d .venv ]; then
  echo "==> creating .venv"
  (uv venv .venv --python 3.11 2>/dev/null) || python3 -m venv .venv
fi

echo "==> installing python packages"
if command -v uv >/dev/null 2>&1; then
  VIRTUAL_ENV=$PWD/.venv uv pip install -q sherpa-onnx soundfile numpy
else
  ./.venv/bin/pip install -q sherpa-onnx soundfile numpy
fi

cat <<'DONE'

ready. next:
  source voice/.venv/bin/activate
  python voice/prep_reference.py my_recording.wav
  python voice/synthesize.py
DONE
