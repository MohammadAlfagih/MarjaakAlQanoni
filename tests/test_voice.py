"""POST /voice contract: STT and TTS are faked; no model downloads or network."""

import json
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from apps.api.app.app import app
from apps.api.services.llm.chat import ChatResponse
from apps.api.voice import chat_bridge, router, stt, tts


def chat_response(**changes):
    return ChatResponse(**{
        "answer": "You get at least 21 days.", "articles": [], "next_steps": ["Ask HR"],
        "conflict": False, "status": "answered", "lang": "en", **changes,
    })


class VoiceTests(unittest.TestCase):
    def setUp(self):
        self.http = TestClient(app)
        self.form = {"role": "employee", "company_id": "c_101", "lang": "en", "history": "[]"}
        self.files = {"audio": ("question.webm", b"fake-audio", "audio/webm")}

    def post(self, **form):
        return self.http.post("/voice", data={**self.form, **form}, files=self.files)

    def test_voice_runs_the_chat_pipeline_and_returns_transcript_and_audio(self):
        with patch.object(stt, "transcribe", return_value="How many leave days?") as transcribe, \
             patch.object(chat_bridge, "answer_question", return_value=chat_response()) as answer, \
             patch.object(tts, "synthesize", AsyncMock(return_value="/audio/x.mp3")):
            result = self.post()
        self.assertEqual(result.status_code, 200)
        body = result.json()
        self.assertEqual(body["transcript"], "How many leave days?")
        self.assertEqual(body["audio_url"], "/audio/x.mp3")
        self.assertEqual(body["status"], "answered")
        transcribe.assert_called_once_with(b"fake-audio", "en")
        request = answer.call_args.args[0]
        self.assertEqual((request.question, request.company_id, request.role),
                         ("How many leave days?", "c_101", "employee"))

    def test_history_and_missing_company_are_passed_like_chat(self):
        history = [{"role": "user", "content": "leave"},
                   {"role": "assistant", "content": "Is it in your contract?", "status": "clarify"}]
        form = {**self.form, "history": json.dumps(history)}
        del form["company_id"]
        with patch.object(stt, "transcribe", return_value="yes"), \
             patch.object(chat_bridge, "answer_question", return_value=chat_response()) as answer, \
             patch.object(tts, "synthesize", AsyncMock(return_value=None)):
            result = self.http.post("/voice", data=form, files=self.files)
        self.assertEqual(result.status_code, 200)
        self.assertIsNone(result.json()["audio_url"])
        request = answer.call_args.args[0]
        self.assertIsNone(request.company_id)
        self.assertEqual(request.history[1].status, "clarify")

    def test_unreadable_audio_is_422_and_skips_the_llm(self):
        with patch.object(stt, "transcribe", side_effect=ValueError("Audio is too short")), \
             patch.object(chat_bridge, "answer_question") as answer:
            result = self.post()
        self.assertEqual(result.status_code, 422)
        answer.assert_not_called()

    def test_missing_speech_model_is_503(self):
        with patch.object(stt, "transcribe", side_effect=OSError("gated repo")):
            result = self.post()
        self.assertEqual(result.status_code, 503)

    def test_invalid_role_is_rejected_like_chat(self):
        with patch.object(stt, "transcribe", return_value="hello"), \
             patch.object(chat_bridge, "answer_question") as answer:
            result = self.post(role="admin")
        self.assertEqual(result.status_code, 422)
        answer.assert_not_called()

    def test_audio_endpoint_serves_only_generated_files(self):
        self.assertEqual(self.http.get("/audio/..%2F..%2Fapp.py").status_code, 404)
        self.assertEqual(self.http.get(f"/audio/{'0' * 32}.mp3").status_code, 404)
        tts.AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        path = tts.AUDIO_DIR / f"{'a' * 32}.mp3"
        path.write_bytes(b"ID3")
        try:
            result = self.http.get(f"/audio/{path.name}")
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.headers["content-type"], "audio/mpeg")
        finally:
            path.unlink(missing_ok=True)

    def test_speech_model_failure_at_startup_keeps_chat_running(self):
        with patch.dict("os.environ", {"LLM_PRELOAD": "1"}), \
             patch("apps.api.app.app.get_client"), \
             patch.object(stt, "load_model", side_effect=OSError("gated repo")), \
             patch.object(tts, "load_models"), \
             patch.object(stt, "load_error", None):
            with TestClient(app) as http:  # runs the startup lifespan
                health = http.get("/health").json()
        self.assertEqual(health["status"], "ok")
        self.assertFalse(health["stt_loaded"])
        self.assertIn("gated repo", health["stt_error"])

    def test_tts_endpoint_returns_audio_url_or_503(self):
        with patch.object(tts, "synthesize", AsyncMock(return_value="/audio/y.mp3")):
            ok = self.http.post("/tts", json={"text": "مرحبا", "lang": "ar"})
        self.assertEqual(ok.json(), {"audio_url": "/audio/y.mp3"})
        with patch.object(tts, "synthesize", AsyncMock(return_value=None)):
            self.assertEqual(self.http.post("/tts", json={"text": "hi", "lang": "en"}).status_code, 503)

    def test_tts_failure_returns_none_and_leaves_no_file(self):
        import asyncio

        async def broken(text, lang, path):
            path.write_bytes(b"")
            raise OSError("edge down")

        def mms_broken(text, lang, path):
            path.write_bytes(b"")
            raise OSError("no model")

        before = set(tts.AUDIO_DIR.glob("*.*"))
        with patch.object(tts, "_edge", broken), patch.object(tts, "_mms_to_wav", mms_broken):
            self.assertIsNone(asyncio.run(tts.synthesize("مرحبا", "ar")))
        self.assertEqual(set(tts.AUDIO_DIR.glob("*.*")), before)

    def test_edge_403_switches_to_mms_and_skips_edge_afterwards(self):
        import asyncio

        calls = []

        async def blocked(text, lang, path):
            calls.append("edge")
            raise OSError("403, message='Invalid response status'")

        def mms(text, lang, path):
            calls.append("mms")
            path.write_bytes(b"RIFF")

        with patch.object(tts, "_edge", blocked), patch.object(tts, "_mms_to_wav", mms), \
             patch.object(tts, "_edge_blocked", False), patch.object(tts, "ENGINE", "auto"):
            first = asyncio.run(tts.synthesize("مرحبا", "ar"))
            second = asyncio.run(tts.synthesize("مرحبا", "ar"))
        self.assertTrue(first.endswith(".wav") and second.endswith(".wav"))
        self.assertEqual(calls, ["edge", "mms", "mms"])
        for url in (first, second):
            (tts.AUDIO_DIR / url.rsplit("/", 1)[1]).unlink()

    def test_mms_text_has_numbers_spelled_and_no_labels_or_diacritics(self):
        chunks = tts.speakable_chunks("يستحقُّ العامل 21 يومًا (المادة ١٠٩) [L1]، وتزيد إلى 30.", "ar")
        text = " ".join(chunks)
        self.assertNotRegex(text, r"[0-9٠-٩()\[\]]|L1|[\u064B-\u065F]")
        self.assertIn("واحد وعشرون", text)
        self.assertIn("مائة وتسعة", text)
        self.assertEqual(tts.speakable_chunks("You get 21 days. P1", "en"), ["You get twenty-one days"])

    def test_mms_writes_a_wav_from_the_model_waveform(self):
        import types
        from threading import Lock

        import soundfile as sf
        import torch

        class Inputs(dict):
            def to(self, device):
                return self

        class FakeVits:
            config = types.SimpleNamespace(sampling_rate=16000)
            device = "cpu"

            def __call__(self, **inputs):
                return types.SimpleNamespace(waveform=torch.zeros((1, 1600)))

        def tokenizer(text, return_tensors):
            return Inputs(input_ids=torch.ones((1, 5), dtype=torch.long))

        path = tts.AUDIO_DIR / f"{'b' * 32}.wav"
        with patch.object(tts, "_load_mms", return_value=(tokenizer, FakeVits(), Lock())):
            tts._mms_to_wav("جملة أولى. جملة ثانية", "ar", path)
        try:
            data, rate = sf.read(str(path))
            self.assertEqual(rate, 16000)
            self.assertEqual(len(data), 1600 + 4000)  # one chunk (short sentences merge) + pause
        finally:
            path.unlink(missing_ok=True)

    def test_audio_endpoint_serves_wav(self):
        path = tts.AUDIO_DIR / f"{'c' * 32}.wav"
        path.write_bytes(b"RIFF")
        try:
            result = self.http.get(f"/audio/{path.name}")
            self.assertEqual(result.headers["content-type"], "audio/wav")
        finally:
            path.unlink(missing_ok=True)

    def test_health_reports_speech_model(self):
        self.assertIn("stt_loaded", self.http.get("/health").json())


if __name__ == "__main__":
    unittest.main()
