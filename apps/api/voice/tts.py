"""Text-to-speech.

1) edge-tts (Microsoft voices, best quality) — needs internet; Microsoft blocks some
   cloud servers (Colab gets 403), so after one refusal it is skipped.
2) MMS-TTS (facebook/mms-tts-ara, facebook/mms-tts-eng) — open-source, runs inside the
   API on the GPU/CPU, no external service. License: CC-BY-NC 4.0 (fine for a demo).

synthesize(text, lang) -> "/audio/<id>.mp3|wav"  or  None (frontend uses the browser voice)
"""
from __future__ import annotations

import asyncio
import os
import re
import time
import uuid
from pathlib import Path
from threading import Lock

# apps/api/.data/audio — already git-ignored and left out of package_api.py
AUDIO_DIR = Path(__file__).resolve().parents[1] / ".data" / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)
MODEL_CACHE = Path(__file__).resolve().parent / ".model_cache"

VOICES = {
    "ar": os.getenv("TTS_VOICE_AR", "ar-SA-HamedNeural"),
    "en": os.getenv("TTS_VOICE_EN", "en-US-AndrewNeural"),
}
MMS_MODELS = {"ar": "facebook/mms-tts-ara", "en": "facebook/mms-tts-eng"}
# auto = edge-tts, then MMS | mms = MMS only | edge = edge-tts only
ENGINE = os.getenv("TTS_ENGINE", "auto").lower()
MAX_CHARS = 1500
KEEP_FILES_FOR_S = 3600

_edge_blocked = False
_mms: dict[str, tuple] = {}
_mms_lock = Lock()


async def synthesize(text: str, lang: str) -> str | None:
    global _edge_blocked
    text = (text or "").strip()[:MAX_CHARS]
    if not text:
        return None
    lang = "en" if lang == "en" else "ar"
    _cleanup_old_files()
    name = uuid.uuid4().hex

    if ENGINE in {"auto", "edge"} and not _edge_blocked:
        path = AUDIO_DIR / f"{name}.mp3"
        try:
            await asyncio.wait_for(_edge(text, lang, path), timeout=20)
            if path.is_file() and path.stat().st_size > 0:
                return f"/audio/{path.name}"
        except Exception as e:  # 403 on Colab, network down, timeout…
            print(f"[tts] edge-tts failed: {type(e).__name__}: {str(e)[:120]}", flush=True)
            if "403" in str(e):
                _edge_blocked = True
                print("[tts] edge-tts blocked on this server; using MMS-TTS from now on", flush=True)
        path.unlink(missing_ok=True)

    if ENGINE in {"auto", "mms"}:
        path = AUDIO_DIR / f"{name}.wav"
        try:
            await asyncio.to_thread(_mms_to_wav, text, lang, path)
            if path.is_file() and path.stat().st_size > 0:
                return f"/audio/{path.name}"
        except Exception as e:
            print(f"[tts] MMS-TTS failed: {type(e).__name__}: {e}", flush=True)
        path.unlink(missing_ok=True)
    return None


async def _edge(text: str, lang: str, path: Path):
    import edge_tts

    await edge_tts.Communicate(text, VOICES[lang]).save(str(path))


# ── MMS-TTS ──────────────────────────────────────────────────

def load_models():
    """Load both MMS voices once (app.py --preload calls this). ~150 MB each."""
    if ENGINE in {"auto", "mms"}:
        for lang in MMS_MODELS:
            _load_mms(lang)


def _load_mms(lang: str):
    with _mms_lock:
        if lang not in _mms:
            import torch
            from transformers import AutoTokenizer, VitsModel

            device = "cuda" if torch.cuda.is_available() else "cpu"
            model_id = MMS_MODELS[lang]
            tokenizer = AutoTokenizer.from_pretrained(model_id, cache_dir=str(MODEL_CACHE))
            model = VitsModel.from_pretrained(model_id, cache_dir=str(MODEL_CACHE)).to(device).eval()
            _mms[lang] = (tokenizer, model, Lock())
            print(f"[tts] {model_id} ready on {device}", flush=True)
        return _mms[lang]


_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
_DIACRITICS = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ]")
_EVIDENCE_LABEL = re.compile(r"[\[(]?\b[LP]\d+\b[\])]?")
_SENTENCE_END = re.compile(r"[.!?؟؛;:\n،,]+")


def speakable_chunks(text: str, lang: str, max_len: int = 120) -> list[str]:
    """MMS knows letters and spaces only: spell numbers, drop labels/diacritics, split sentences."""
    text = _EVIDENCE_LABEL.sub(" ", text.translate(_ARABIC_DIGITS))
    text = re.sub(r"\d+", lambda m: f" {_number_words(int(m.group()), lang)} ", text)
    if lang == "ar":
        text = _DIACRITICS.sub("", text)
    text = re.sub(r"[^\w\s.!?؟؛;:،,'-]", " ", text)  # brackets, quotes, symbols
    chunks, current = [], ""
    for part in _SENTENCE_END.split(text):
        part = " ".join(part.split())
        if not re.search(r"\w", part):
            continue
        if current and len(current) + len(part) + 1 > max_len:
            chunks.append(current)
            current = part
        else:
            current = f"{current} {part}".strip()
    if current:
        chunks.append(current)
    return chunks


def _number_words(n: int, lang: str) -> str:
    from num2words import num2words

    words = num2words(n, lang=lang)
    return words.replace("و ", "و") if lang == "ar" else words  # "واحد وعشرون"


def _mms_to_wav(text: str, lang: str, path: Path):
    import numpy as np
    import soundfile as sf
    import torch

    tokenizer, model, lock = _load_mms(lang)
    rate = model.config.sampling_rate
    pause = np.zeros(int(rate * 0.25), dtype=np.float32)
    pieces = []
    for chunk in speakable_chunks(text, lang):
        inputs = tokenizer(chunk, return_tensors="pt").to(model.device)
        if inputs["input_ids"].shape[1] < 2:
            continue
        with lock, torch.inference_mode():
            wave = model(**inputs).waveform[0].float().cpu().numpy()
        pieces += [wave, pause]
    if not pieces:
        raise ValueError("Nothing speakable in the text")
    sf.write(str(path), np.concatenate(pieces), rate, format="WAV")


def _cleanup_old_files():
    now = time.time()
    for f in AUDIO_DIR.glob("*.*"):
        if f.suffix in {".mp3", ".wav"} and now - f.stat().st_mtime > KEEP_FILES_FOR_S:
            f.unlink(missing_ok=True)
