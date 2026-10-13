# voice/

Speech for `/voice`. Setup and the Colab steps are in [`apps/api/README.md`](../README.md).

| File | What it does |
|---|---|
| `router.py` | `POST /voice`, `POST /tts`, `GET /audio/{id}` |
| `stt.py` | Cohere Transcribe Arabic: `load_model()`, `transcribe(audio, lang)` |
| `chat_bridge.py` | sends the transcript through the same code as `POST /chat` |
| `tts.py` | edge-tts, else MMS-TTS: `synthesize(text, lang)` → `/audio/<id>` or `None` |
| `audio_utils.py` | browser audio → 16 kHz mono (bundled ffmpeg) |

Tests: `tests/test_voice.py` (no model download).
