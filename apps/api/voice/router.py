"""Voice endpoints.

POST /voice              audio question → same JSON as /chat + transcript + audio_url
POST /tts                {text, lang} → {audio_url}  (the "Listen" button on typed answers)
GET  /audio/{file}       the spoken answer (.mp3 from edge-tts, .wav from MMS)

Flow: audio → STT (Cohere) → /chat pipeline (RAG + Qwen) → TTS (edge-tts)
"""
from __future__ import annotations

import json
import re
from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from . import chat_bridge, stt, tts

router = APIRouter(tags=["Voice"])

MAX_AUDIO_BYTES = 10_000_000  # 60 s of browser audio is well below this


@router.post("/voice")
async def voice(
    audio: UploadFile = File(...),
    role: str = Form("employee"),
    company_id: str | None = Form(None),
    lang: str = Form("ar"),
    history: str = Form("[]"),
):
    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(422, "Empty audio")
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise HTTPException(413, "Audio too large")
    try:
        history_list = json.loads(history)
    except json.JSONDecodeError:
        raise HTTPException(422, "history must be a JSON list")

    # 1) Speech → text (blocking GPU call, off the event loop)
    try:
        transcript = await run_in_threadpool(stt.transcribe, audio_bytes, lang)
    except ValueError as exc:  # unreadable / too short audio
        raise HTTPException(422, str(exc)) from exc
    except (OSError, RuntimeError, ImportError) as exc:
        raise HTTPException(
            503, "Speech model unavailable. Check HF_TOKEN, the model terms, transformers and GPU memory."
        ) from exc
    if not transcript:
        raise HTTPException(422, "No speech detected")

    # 2) Same pipeline as POST /chat
    result = await chat_bridge.answer(transcript, role, company_id, lang, history_list)

    # 3) Text → speech; None on failure (the frontend then uses the browser voice)
    audio_url = await tts.synthesize(result["answer"], result["lang"])

    return {**result, "transcript": transcript, "audio_url": audio_url}


class SpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=8000)
    lang: Literal["ar", "en"]


@router.post("/tts")
async def speak(request: SpeakRequest):
    audio_url = await tts.synthesize(request.text, request.lang)
    if audio_url is None:
        raise HTTPException(503, "Text-to-speech unavailable; see [tts] lines in the server log")
    return {"audio_url": audio_url}


@router.get("/audio/{name}")
def get_audio(name: str):
    if not re.fullmatch(r"[0-9a-f]{32}\.(mp3|wav)", name):
        raise HTTPException(404)
    path = tts.AUDIO_DIR / name
    if not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, media_type="audio/mpeg" if name.endswith(".mp3") else "audio/wav")
