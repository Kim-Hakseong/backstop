---
title: Your Voice Other Languages
emoji: 🗣️
colorFrom: indigo
colorTo: purple
sdk: gradio
sdk_version: 5.49.1
app_file: app.py
pinned: false
license: mit
short_description: Speak other languages in your own voice
---

Chatterbox Multilingual on ZeroGPU. Upload 10-15 seconds of your voice, get
that voice speaking one of 23 languages.

Each request draws several takes and keeps the one closest to your voice by
speaker embedding, because zero-shot cloning is not repeatable -- see the note
at the top of `app.py`.

Not verified: this was written on a machine that cannot reach Hugging Face.
