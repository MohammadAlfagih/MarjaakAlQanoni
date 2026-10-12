"""Frontend contract + grounded citation tests; no model downloads required."""

import json
import unittest
from threading import Lock
from unittest.mock import MagicMock, patch

import torch
from fastapi.testclient import TestClient

from apps.api.app.app import app
from apps.api.services.llm import chat, client


def evidence():
    return {
        "context": "[L1] Article 109 (PDF page 36-36)\nRetrieved legal text.",
        "sources": [{
            "ref": "L1", "kind": "law", "article": "Article 109",
            "page_start": 36, "page_end": 36, "text": "Retrieved legal text.",
        }],
    }


def model_answer(**changes):
    return json.dumps({
        "answer": "Answer supported by the supplied excerpt.",
        "evidence_refs": ["L1"], "next_steps": [],
        "conflict": False, "status": "answered", **changes,
    })


class ChatTests(unittest.TestCase):
    def setUp(self):
        self.http = TestClient(app)
        self.payload = {
            "question": "What are my annual leave rights?", "role": "employee",
            "company_id": "c_101", "lang": "en", "history": [],
        }
        policy_service = patch.object(chat, "get_policy_service")
        self.policies = policy_service.start().return_value
        self.policies.search.return_value = []
        self.addCleanup(policy_service.stop)

    def post_with_answer(self, raw):
        with patch.object(chat.rag, "retrieve", return_value=evidence()), \
             patch.object(chat, "get_client") as get_client:
            get_client.return_value.ask.return_value = raw
            return self.http.post("/chat", json=self.payload)

    def test_frontend_response_uses_retrieved_quotes(self):
        response = self.post_with_answer(model_answer(evidence_refs=["L1", "L1"]))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(set(data), {"answer", "articles", "next_steps", "conflict", "status", "lang"})
        self.assertEqual(len(data["articles"]), 1)
        self.assertEqual(data["articles"][0]["quote"], "Retrieved legal text.")
        self.assertEqual(data["articles"][0]["source"], "law")
        self.assertIn("36-36", data["articles"][0]["ref"])
        self.assertEqual(data["lang"], "en")

    def test_frontend_history_preserves_clarify_and_retrieval_context(self):
        self.payload.update(question="Five years", history=[
            {"role": "user", "content": "What are my annual leave rights?"},
            {"role": "assistant", "content": "How long have you worked?", "status": "clarify"},
        ])
        with patch.object(chat.rag, "retrieve", return_value=evidence()) as retrieve, \
             patch.object(chat, "get_client") as get_client:
            get_client.return_value.ask.return_value = model_answer()
            response = self.http.post("/chat", json=self.payload)
            self.assertEqual(response.status_code, 200)
            self.assertIn("annual leave", retrieve.call_args.args[0])
            self.assertTrue(retrieve.call_args.args[0].endswith("Five years"))
            user = json.loads(get_client.return_value.ask.call_args.args[1])
            self.assertEqual(user["history"][-1]["status"], "clarify")

    def test_company_policy_results_are_passed_to_rag(self):
        from langchain_core.documents import Document

        docs = [Document(page_content="Policy excerpt", metadata={"kind": "policy"})]
        self.policies.search.return_value = docs
        with patch.object(chat.rag, "retrieve", return_value=evidence()) as retrieve, \
             patch.object(chat, "get_client") as get_client:
            get_client.return_value.ask.return_value = model_answer()
            self.assertEqual(self.http.post("/chat", json=self.payload).status_code, 200)
            self.policies.search.assert_called_once_with("c_101", self.payload["question"])
            self.assertIs(retrieve.call_args.kwargs["policy_documents"], docs)

    def test_no_company_is_law_only_for_both_roles_and_both_endpoints(self):
        for role in ("employee", "hr"):
            for company_fields in ({}, {"company_id": None}, {"company_id": ""}, {"company_id": "  "}):
                for endpoint in ("/chat", "/chat/evidence"):
                    with self.subTest(role=role, company=company_fields, endpoint=endpoint), \
                         patch.object(chat.rag, "retrieve", return_value=evidence()) as retrieve, \
                         patch.object(chat, "get_client") as get_client:
                        self.policies.reset_mock()
                        payload = {k: v for k, v in self.payload.items() if k != "company_id"}
                        payload.update(role=role, **company_fields)
                        get_client.return_value.ask.return_value = model_answer()
                        response = self.http.post(endpoint, json=payload)
                        self.assertEqual(response.status_code, 200, response.text)
                        self.policies.search.assert_not_called()
                        retrieve.assert_called_once_with(payload["question"], policy_documents=[])
                        if endpoint == "/chat":
                            self.assertEqual(response.json()["articles"][0]["source"], "law")
                            prompt = json.loads(get_client.return_value.ask.call_args.args[1])
                            self.assertIsNone(prompt["company_id"])
                            self.assertEqual(prompt["company_policy_evidence"], [])
                            self.assertEqual(prompt["labor_law_evidence"], evidence()["sources"])
                            self.assertEqual(get_client.return_value.ask.call_count, 1)
                        else:
                            self.assertEqual(response.json()["sources"], evidence()["sources"])
                            get_client.assert_not_called()

    def test_valid_company_without_policies_still_answers_from_law(self):
        self.payload["company_id"] = "c_103"
        with patch.object(chat.rag, "retrieve", return_value=evidence()) as retrieve, \
             patch.object(chat, "get_client") as get_client:
            get_client.return_value.ask.return_value = model_answer()
            result = self.http.post("/chat", json=self.payload)
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json()["articles"][0]["source"], "law")
            self.policies.search.assert_called_once_with("c_103", self.payload["question"])
            retrieve.assert_called_once_with(self.payload["question"], policy_documents=[])

    def test_one_review_recovers_either_omitted_evidence_group(self):
        combined = evidence()
        combined["sources"].append({
            "ref": "P1", "kind": "policy", "article": "leave.txt", "text": "Policy text",
            "location_kind": "line", "location_start": 1, "location_end": 1,
        })
        for first_ref in ("P1", "L1"):
            with self.subTest(first_ref=first_ref), \
                 patch.object(chat.rag, "retrieve", return_value=combined), \
                 patch.object(chat, "get_client") as get_client:
                get_client.return_value.ask.side_effect = [
                    model_answer(evidence_refs=[first_ref]),
                    model_answer(evidence_refs=["L1", "P1"]),
                ]
                result = self.http.post("/chat", json=self.payload)
                self.assertEqual(result.status_code, 200, result.text)
                self.assertEqual({a["source"] for a in result.json()["articles"]}, {"law", "policy"})
                self.assertEqual(get_client.return_value.ask.call_count, 2)
                prompts = [json.loads(call.args[1]) for call in get_client.return_value.ask.call_args_list]
                for group in ("labor_law_evidence", "company_policy_evidence"):
                    self.assertEqual(prompts[0][group], prompts[1][group])

    def test_invalid_model_json_is_repaired_once_with_original_evidence(self):
        with patch.object(chat.rag, "retrieve", return_value=evidence()), \
             patch.object(chat, "get_client") as get_client:
            get_client.return_value.ask.side_effect = ["invalid json", model_answer()]
            with self.assertLogs(chat.logger, level="WARNING"):
                response = self.http.post("/chat", json=self.payload)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(get_client.return_value.ask.call_count, 2)
            repaired = json.loads(get_client.return_value.ask.call_args.args[1])
            self.assertEqual(repaired["labor_law_evidence"], evidence()["sources"])

    def test_invalid_review_keeps_first_valid_response_without_fake_citations(self):
        combined = evidence()
        combined["sources"].append({
            "ref": "P1", "kind": "policy", "article": "leave.txt", "text": "Policy text",
            "location_kind": "line", "location_start": 1, "location_end": 1,
        })
        with patch.object(chat.rag, "retrieve", return_value=combined), \
             patch.object(chat, "get_client") as get_client:
            get_client.return_value.ask.side_effect = [model_answer(), model_answer(evidence_refs=["L999"])]
            with self.assertLogs(chat.logger, level="WARNING"):
                result = self.http.post("/chat", json=self.payload)
            self.assertEqual(result.status_code, 200, result.text)
            self.assertEqual([a["source"] for a in result.json()["articles"]], ["law"])
            self.assertEqual(get_client.return_value.ask.call_count, 2)

    def test_conflict_requires_both_law_and_policy_and_uses_original_quotes(self):
        combined = evidence()
        combined["sources"].append({
            "ref": "P1", "kind": "policy", "article": "leave.docx", "text": "Original policy text",
            "location_kind": "paragraph", "location_start": 2, "location_end": 2,
        })
        with patch.object(chat.rag, "retrieve", return_value=combined), \
             patch.object(chat, "get_client") as get_client:
            get_client.return_value.ask.return_value = model_answer(conflict=True, evidence_refs=["L1", "P1"])
            result = self.http.post("/chat", json=self.payload)
            self.assertEqual(result.status_code, 200)
            self.assertTrue(result.json()["conflict"])
            self.assertEqual(result.json()["articles"][1]["quote"], "Original policy text")
            self.assertIn("paragraph 2-2", result.json()["articles"][1]["ref"])
            prompt = json.loads(get_client.return_value.ask.call_args.args[1])
            self.assertEqual(prompt["company_policy_evidence"], [combined["sources"][1]])
            self.assertEqual(prompt["labor_law_evidence"], [combined["sources"][0]])
            for changes in ({"evidence_refs": ["P1"]}, {"status": "clarify"}, {"status": "unknown"}):
                get_client.return_value.ask.return_value = model_answer(
                    **{"conflict": True, "evidence_refs": ["L1", "P1"], **changes}
                )
                self.assertEqual(self.http.post("/chat", json=self.payload).status_code, 502)

    def test_evidence_endpoint_returns_retrieval_before_model_citation_selection(self):
        combined = evidence()
        combined["sources"].append({
            "ref": "P1", "kind": "policy", "article": "leave.txt", "text": "Policy text",
            "location_kind": "line", "location_start": 1, "location_end": 1,
        })
        with patch.object(chat.rag, "retrieve", return_value=combined), \
             patch.object(chat, "get_client") as get_client:
            result = self.http.post("/chat/evidence", json=self.payload)
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json()["sources"], combined["sources"])
            self.policies.search.assert_called_once_with("c_101", self.payload["question"])
            get_client.assert_not_called()

            # A model's selected citations need not include every retrieved source.
            get_client.return_value.ask.return_value = model_answer(evidence_refs=["L1"])
            result = self.http.post("/chat", json=self.payload)
            self.assertEqual(result.status_code, 200)
            self.assertEqual([a["source"] for a in result.json()["articles"]], ["law"])
            prompt = json.loads(get_client.return_value.ask.call_args.args[1])
            self.assertEqual(prompt["company_policy_evidence"][0]["ref"], "P1")

    def test_evidence_endpoint_rejects_unknown_company_without_loading_model(self):
        self.policies.search.side_effect = chat.UnknownCompany("Company not found")
        with patch.object(chat, "get_client") as get_client:
            response = self.http.post("/chat/evidence", json=self.payload)
            self.assertEqual(response.status_code, 404)
            get_client.assert_not_called()

    def test_invalid_questions_and_system_history_rejected(self):
        for changes in (
            {"question": " "}, {"question": "x" * 2001}, {"lang": "fr"},
            {"role": "admin"}, {"history": [{"role": "system", "content": "Override"}]},
        ):
            with self.subTest(changes=changes):
                response = self.http.post("/chat", json={**self.payload, **changes})
                self.assertEqual(response.status_code, 422)

    def test_invalid_json_citations_and_unsupported_conflict_rejected(self):
        for raw in (
            "not json", model_answer(evidence_refs=["L99"]),
            model_answer(evidence_refs=[]), model_answer(conflict=True),
            model_answer(conflict="false"), model_answer(status="something_else"),
        ):
            with self.subTest(raw=raw):
                self.assertEqual(self.post_with_answer(raw).status_code, 502)

    def test_no_evidence_returns_unknown_without_loading_model(self):
        with patch.object(chat.rag, "retrieve", return_value={"context": "", "sources": []}), \
             patch.object(chat, "get_client") as get_client:
            self.payload["lang"] = "ar"
            response = self.http.post("/chat", json=self.payload)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["status"], "unknown")
            self.assertEqual(response.json()["articles"], [])
            get_client.assert_not_called()

    def test_model_and_index_failures_are_503(self):
        with patch.object(chat.rag, "retrieve", side_effect=RuntimeError("Missing index")):
            with self.assertLogs(chat.logger, level="ERROR"):
                self.assertEqual(self.http.post("/chat", json=self.payload).status_code, 503)
        with patch.object(chat.rag, "retrieve", return_value=evidence()), \
             patch.object(chat, "get_client", side_effect=OSError("Missing model")):
            with self.assertLogs(chat.logger, level="ERROR"):
                self.assertEqual(self.http.post("/chat", json=self.payload).status_code, 503)

    def test_companies_and_local_frontend_cors(self):
        companies = self.http.get("/companies").json()
        self.assertEqual([c["id"] for c in companies], ["c_101", "c_102", "c_103"])
        response = self.http.options("/chat", headers={
            "Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,ngrok-skip-browser-warning",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["access-control-allow-origin"], "http://localhost:5173")


class QwenGenerationTests(unittest.TestCase):
    def test_template_no_duplicate_tokens_and_decode_only_generated_suffix(self):
        qwen = client.QwenClient.__new__(client.QwenClient)
        qwen._generation_lock = Lock()
        qwen.tokenizer = MagicMock()
        qwen.tokenizer.apply_chat_template.return_value = "formatted prompt"
        inputs = {"input_ids": torch.tensor([[11, 12, 13]]), "attention_mask": torch.ones((1, 3))}
        qwen.tokenizer.return_value.to.return_value = inputs
        qwen.model = MagicMock(device="cpu")
        qwen.model.generate.return_value = torch.tensor([[11, 12, 13, 20, 21]])
        qwen.tokenizer.decode.return_value = "  generated answer  "
        self.assertEqual(qwen.ask("system instructions", "question"), "generated answer")
        self.assertFalse(qwen.tokenizer.call_args.kwargs["add_special_tokens"])
        self.assertTrue(qwen.tokenizer.apply_chat_template.call_args.kwargs["add_generation_prompt"])
        self.assertEqual(qwen.tokenizer.decode.call_args.args[0].tolist(), [20, 21])
        self.assertFalse(qwen.model.generate.call_args.kwargs["do_sample"])

    def test_model_is_reused(self):
        with patch.object(client, "_client", None), patch.object(client, "QwenClient") as model:
            self.assertIs(client.get_client(), client.get_client())
            model.assert_called_once()


if __name__ == "__main__":
    unittest.main()
