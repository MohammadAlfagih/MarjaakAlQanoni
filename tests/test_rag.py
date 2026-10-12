"""RAG regression checks. Run: python -m unittest discover -s tests -v."""
import contextlib
import io
import math
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pymupdf
from fastapi.testclient import TestClient
from langchain_core.embeddings import Embeddings

from apps.api.app.app import app
from apps.api.services.RAG import rag


def policy_pdf(text="Company annual leave policy: employees receive 25 paid days.", pages=1):
    with pymupdf.open() as pdf:
        for _ in range(pages):
            page = pdf.new_page()
            if text:
                page.insert_text((72, 72), text)
        return pdf.tobytes()


class FakeEmbeddings(Embeddings):
    """Exercise Chroma lifecycle and isolation without downloading a model."""
    def embed_documents(self, texts):
        return [[1.0, 0.0, 0.0] for _ in texts]

    def embed_query(self, text):
        return [1.0, 0.0, 0.0]


class ExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.articles = rag.extract_articles()
        cls.chunks = rag.law_chunks()

    def test_numbering_and_repeated_articles(self):
        base = [doc.metadata["article_number"] for doc in self.articles
                if not doc.metadata["repeated"]]
        self.assertEqual(base, list(range(1, 246)))
        self.assertEqual(len(self.articles), 249)
        identifiers = [(d.metadata["article_number"], d.metadata["repeated"],
                        d.metadata["chunk"]) for d in self.chunks]
        self.assertEqual(len(identifiers), len(set(identifiers)))

    def test_article_109_readable_and_attributable(self):
        article = next(d for d in self.articles if d.metadata["article_number"] == 109)
        self.assertEqual(article.metadata["page_start"], 36)
        self.assertEqual(article.metadata["page_end"], 36)
        self.assertIn("يستحق العامل", article.page_content)
        self.assertIn("واحد وعشرين", article.page_content)
        self.assertNotIn("عدلت هذه المادة", article.page_content)
        self.assertNotIn("المادة العاشرة", article.page_content)

    def test_chunk_page_ranges_and_scalar_metadata(self):
        for chunk in self.chunks:
            self.assertLessEqual(chunk.metadata["page_start"], chunk.metadata["page_end"])
            self.assertTrue(all(isinstance(value, (str, int, bool, float))
                                for value in chunk.metadata.values()))
            self.assertEqual(chunk.page_content.count(chunk.metadata["article"]), 1)
        final = self.articles[-1]
        self.assertEqual(final.metadata["page_end"], 67)
        self.assertNotIn("www.hrsd", final.page_content)

    def test_policy_chunks_have_pages_and_chunk_numbers(self):
        chunks = rag.extract_policy(policy_pdf(pages=2))
        self.assertEqual({d.metadata["page_start"] for d in chunks}, {1, 2})
        self.assertTrue(all(d.metadata["kind"] == "policy" for d in chunks))
        self.assertTrue(all("chunk" in d.metadata for d in chunks))

    def test_invalid_scanned_and_oversized_policies(self):
        for data in (b"not a pdf", b"%PDF-broken", policy_pdf(text=""),
                     policy_pdf(pages=41), b"%PDF-" + b"x" * rag.MAX_POLICY_BYTES):
            with self.subTest(length=len(data)), self.assertRaises(ValueError):
                rag.extract_policy(data)

    def test_signature_includes_chunk_settings(self):
        original = rag.signature()
        with patch.object(rag, "CHUNK_SIZE", 700):
            self.assertNotEqual(original, rag.signature())

    def test_english_query_expansion_preserves_the_question(self):
        question = "What are my annual leave rights?"
        self.assertTrue(rag.law_query(question).startswith(question))
        self.assertIn("الإجازة السنوية", rag.law_query(question))
        self.assertEqual(rag.law_query("المادة 109"), "المادة 109")
        self.assertEqual(rag.law_query("leave me alone"), "leave me alone")


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_question_validation(self):
        for fields in ({}, {"question": " "}, {"question": "x" * 2001}):
            self.assertEqual(self.client.post("/rag/search", data=fields).status_code, 422)

    def test_missing_index_is_503(self):
        with patch.object(rag, "READY", Path("missing-index-marker.txt")):
            response = self.client.post("/rag/search", data={"question": "annual leave"})
        self.assertEqual(response.status_code, 503)

    def test_upload_errors_are_422(self):
        response = self.client.post("/rag/search", data={"question": "annual leave"},
                                    files={"policy_file": ("policy.pdf", b"%PDF-broken")})
        self.assertEqual(response.status_code, 422)


class IndexTests(unittest.TestCase):
    def test_persistent_index_article_filter_and_policy_isolation(self):
        Path("tmp").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir="tmp", ignore_cleanup_errors=True) as directory:
            db_dir = Path(directory) / "chroma"
            with patch.object(rag, "DB_DIR", db_dir), \
                 patch.object(rag, "READY", db_dir / "READY.txt"), \
                 patch.object(rag, "embeddings", return_value=FakeEmbeddings()):
                rag.store.cache_clear()
                try:
                    with contextlib.redirect_stdout(io.StringIO()):
                        rag.build_index()
                        rag.build_index()  # Idempotent: never duplicates law vectors.
                    database = rag.store()
                    before = len(database.get()["ids"])
                    for question in ("المادة 109", "المادة ١٠٩", "Article 109"):
                        result = rag.retrieve(question, policy_pdf())
                        law = [s for s in result["sources"] if s["kind"] == "law"]
                        self.assertTrue(law)
                        self.assertTrue(all(s["article_number"] == 109 for s in law))
                        self.assertTrue(all(s["page_start"] == 36 for s in law))
                        self.assertIn("[P1]", result["context"])
                        self.assertEqual(len(database.get()["ids"]), before)
                    response = TestClient(app).post("/rag/search",
                        data={"question": "Article 109"},
                        files={"policy_file": ("policy.pdf", policy_pdf(), "application/pdf")})
                    self.assertEqual(response.status_code, 200)
                    self.assertTrue(any(s["ref"] == "P1" for s in response.json()["sources"]))
                    self.assertEqual(len(database.get()["ids"]), before)
                    self.assertFalse(rag.retrieve("Article 999")["sources"])
                    database.delete(ids=[database.get()["ids"][0]])
                    with self.assertRaises(RuntimeError):
                        rag.retrieve("Article 109")
                finally:
                    rag.store.cache_clear()


@unittest.skipUnless(os.environ.get("RAG_LIVE_TESTS") == "1",
                     "Set RAG_LIVE_TESTS=1 after --build to test real E5 retrieval")
class LiveRetrievalTests(unittest.TestCase):
    def test_e5_dimensions_and_normalization(self):
        vector = rag.embeddings().embed_query("annual leave")
        self.assertEqual(len(vector), 384)
        self.assertAlmostEqual(math.sqrt(sum(v * v for v in vector)), 1.0, places=5)

    def test_arabic_and_english_annual_leave(self):
        for question in ("كم عدد أيام الإجازة السنوية؟", "What are my annual leave rights?"):
            with self.subTest(question=question):
                result = rag.retrieve(question)
                self.assertIn(109, [s["article_number"] for s in result["sources"]])
                for source in result["sources"]:
                    self.assertIn(f"[{source['ref']}]", result["context"])

    def test_explicit_article_and_policy_api_isolation(self):
        client = TestClient(app)
        database = rag.store()
        before = set(database.get(include=[])["ids"])
        for question in ("المادة ١٠٩", "Article 109"):
            response = client.post("/rag/search", data={"question": question},
                files={"policy_file": ("company-policy.pdf", policy_pdf(), "application/pdf")})
            self.assertEqual(response.status_code, 200)
            result = response.json()
            law = [s for s in result["sources"] if s["kind"] == "law"]
            self.assertTrue(law)
            self.assertTrue(all(s["article_number"] == 109 for s in law))
            self.assertTrue(all(s["page_start"] == 36 for s in law))
            self.assertTrue(any(s["ref"] == "P1" for s in result["sources"]))
        self.assertEqual(set(database.get(include=[])["ids"]), before)
        clean_response = client.post("/rag/search", data={"question": "Article 109"})
        self.assertEqual(clean_response.status_code, 200)
        self.assertTrue(all(s["kind"] == "law" for s in clean_response.json()["sources"]))


if __name__ == "__main__":
    unittest.main()
