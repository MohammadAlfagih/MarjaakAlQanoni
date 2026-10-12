"""Opt-in real E5 checks against the existing law index; no Qwen/downloads."""

import os
import tempfile
import unittest
from pathlib import Path

from apps.api.services.RAG import rag
from apps.api.services.policies.service import PolicyService


@unittest.skipUnless(os.environ.get("RAG_LIVE_TESTS") == "1",
                     "Set RAG_LIVE_TESTS=1 to use the cached E5 model and law index")
class LiveCompanyRetrievalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Path("tmp").mkdir(exist_ok=True)
        cls.directory = tempfile.TemporaryDirectory(dir="tmp")
        cls.addClassCleanup(cls.directory.cleanup)
        cls.policies = PolicyService(Path(cls.directory.name))
        cls.policies.upload(
            "c_101", "synthetic-leave-policy.txt",
            "سياسة اختبار اصطناعية: يستحق موظفو الشركة إجازة سنوية مدفوعة الأجر مدتها 25 يوما.".encode("utf-8"),
        )

    def test_company_policy_is_added_without_replacing_law(self):
        for question in ("كم أستحق إجازة سنوية؟", "كم استحق اجازة سنوية في شركتي"):
            with self.subTest(question=question):
                law_only = rag.retrieve(question)
                policy_docs = self.policies.search("c_101", question)
                combined = rag.retrieve(question, policy_documents=policy_docs)
                law_sources = [source for source in combined["sources"] if source["kind"] == "law"]
                policy_sources = [source for source in combined["sources"] if source["kind"] == "policy"]
                self.assertEqual(law_sources, law_only["sources"])
                self.assertIn(109, [source["article_number"] for source in law_sources])
                self.assertTrue(policy_sources)
                self.assertTrue(all(source["company_id"] == "c_101" for source in policy_sources))

    def test_company_without_policies_still_gets_law(self):
        question = "كم أستحق إجازة سنوية؟"
        policy_docs = self.policies.search("c_102", question)
        self.assertEqual(policy_docs, [])
        result = rag.retrieve(question, policy_documents=policy_docs)
        self.assertTrue(result["sources"])
        self.assertTrue(all(source["kind"] == "law" for source in result["sources"]))
        self.assertIn(109, [source["article_number"] for source in result["sources"]])


if __name__ == "__main__":
    unittest.main()
