"""Speech-to-text with Cohere Transcribe Arabic, inside the API process on the GPU.

load_model()                  → loads once (app.py --preload calls it at startup)
transcribe(audio_bytes, lang) → text  (lang "ar" or "en"; the model has no auto-detect)

The model is gated: accept its terms on Hugging Face and set HF_TOKEN before starting.
"""
from __future__ import annotations

import os
from pathlib import Path
from threading import Lock

MODEL_ID = os.environ.get("STT_MODEL_NAME", "CohereLabs/cohere-transcribe-arabic-07-2026")
MODEL_CACHE = Path(__file__).resolve().parent / ".model_cache"

_model = None
_processor = None
load_error: str | None = None  # set by app.py if loading at startup failed
_load_lock = Lock()
_gpu_lock = Lock()  # one transcription on the GPU at a time


def _pick_dtype(torch):
    forced = os.environ.get("STT_DTYPE")  # optional override: float32 | float16 | bfloat16
    if forced:
        return getattr(torch, forced)
    if not torch.cuda.is_available():
        return torch.float32
    # float16 on T4 (no bf16), same as Qwen; leaves room for both models in 16 GB
    return torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16


def load_model():
    global _model, _processor, load_error
    with _load_lock:
        if _model is not None:
            return
        import torch
        from transformers import AutoProcessor, CohereAsrForConditionalGeneration

        dtype = _pick_dtype(torch)
        print(f"[stt] loading {MODEL_ID} ({dtype})", flush=True)
        _processor = AutoProcessor.from_pretrained(MODEL_ID, cache_dir=str(MODEL_CACHE))
        _model = CohereAsrForConditionalGeneration.from_pretrained(
            MODEL_ID, cache_dir=str(MODEL_CACHE), device_map="auto", dtype=dtype
        )
        _model.eval()
        load_error = None
        print("[stt] ready", flush=True)


def is_loaded() -> bool:
    return _model is not None


def transcribe(audio_bytes: bytes, lang: str) -> str:
    import torch

    from .audio_utils import SAMPLE_RATE, to_16k_mono

    lang = "en" if lang == "en" else "ar"
    audio = to_16k_mono(audio_bytes)  # ValueError if unreadable / too short
    load_model()
    inputs = _processor(audio, sampling_rate=SAMPLE_RATE, return_tensors="pt", language=lang)
    inputs.to(_model.device, dtype=_model.dtype)
    with _gpu_lock, torch.inference_mode():
        out = _model.generate(**inputs, max_new_tokens=256)
    text = _processor.decode(out, skip_special_tokens=True)
    return (text[0] if isinstance(text, list) else text).strip()
