"""Status repair, and history that must not leak an earlier topic into a new question."""

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from apps.api.app.app import app
from apps.api.services.llm import chat
import json

from tests.test_chat import evidence, model_answer

PAYLOAD = {"question": "كم يوم إجازتي؟", "role": "employee", "company_id": "c_102",
           "lang": "ar", "history": []}


class StatusRepairTests(unittest.TestCase):
    def ask(self, raw):
        with patch.object(chat, "get_policy_service"), \
             patch.object(chat.rag, "retrieve", return_value=evidence()), \
             patch.object(chat, "get_client") as get_client:
            get_client.return_value.ask.return_value = raw
            return TestClient(app).post("/chat", json=PAYLOAD)

    def test_unknown_with_law_refs_is_answered_with_citations(self):
        result = self.ask(model_answer(status="unknown")).json()
        self.assertEqual(result["status"], "answered")
        self.assertEqual(len(result["articles"]), 1)

    def test_unknown_without_refs_stays_unknown(self):
        result = self.ask(model_answer(status="unknown", evidence_refs=[])).json()
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["articles"], [])


class HistoryTopicTests(unittest.TestCase):
    HISTORY = [
        {"role": "user", "content": "كم يستحق الموظفين الاجازه السنويه"},
        {"role": "assistant", "content": "وفقا لنظام العمل " * 100, "status": "answered"},
    ]

    def post(self, question, history):
        with patch.object(chat, "get_policy_service"), \
             patch.object(chat.rag, "retrieve", return_value=evidence()) as retrieve, \
             patch.object(chat, "get_client") as get_client:
            get_client.return_value.ask.return_value = model_answer()
            TestClient(app).post("/chat", json={**PAYLOAD, "question": question, "history": history})
            return retrieve.call_args.args[0], json.loads(get_client.return_value.ask.call_args.args[1])

    def test_new_topic_retrieves_with_the_new_question_only(self):
        query, _ = self.post("مديري رفض يعطيني إجازة العيد. هل من حقه؟", self.HISTORY)
        self.assertEqual(query, "مديري رفض يعطيني إجازة العيد. هل من حقه؟")

    def test_previous_answers_reach_the_model_only_as_a_short_excerpt(self):
        _, prompt = self.post("سؤال جديد", self.HISTORY)
        self.assertLessEqual(len(prompt["history"][1]["content"]), 400)
        self.assertEqual(prompt["history"][0]["content"], self.HISTORY[0]["content"])


if __name__ == "__main__":
    unittest.main()
