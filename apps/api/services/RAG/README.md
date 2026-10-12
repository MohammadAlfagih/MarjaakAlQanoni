# RAG service

This service retrieves evidence from the shared Saudi Labor Law PDF and an
optional uploaded company-policy PDF. It returns `context` and `sources` for
the existing LLM service; it does not generate answers or decide compliance.

## Setup and run

Run these PowerShell commands from the repository root:

```powershell
.\venv\Scripts\python.exe -m pip install -r apps/api/requirements.txt
.\venv\Scripts\python.exe -m apps.api.services.RAG.rag --inspect
.\venv\Scripts\python.exe -m apps.api.services.RAG.rag --build
.\venv\Scripts\python.exe -m uvicorn apps.api.app.app:app --reload
```

Open http://127.0.0.1:8000/docs and use `POST /rag/search`.
The supplied PDF extracts into 245 numbered articles plus four `مكرر`
articles. Article 109 starts on PDF page 36. The current chunk settings
produce 325 chunks. Page citations use one-based PDF page numbers, which
differ from the page numbers printed in the document.

The first build downloads `intfloat/multilingual-e5-small` into `.model_cache/`
and stores law vectors in `chroma_e5_db/` beside `rag.py`. Both directories
are gitignored. Subsequent requests load the cached model and reuse it in
memory. A complete cache supports offline operation.

The index records a fingerprint of the PDF, model name, extraction version,
and chunk settings. A matching complete index makes `--build` a no-op.
For a changed or interrupted index, stop the API, back up or rename only
`apps/api/services/RAG/chroma_e5_db/`, then run `--build` again. Do not delete
the shared PDF. The API refuses missing, stale, or incomplete indexes.

## HTTP contract

`POST /rag/search` accepts multipart form data:

| Field | Type | Required |
| --- | --- | --- |
| `question` | Text, 1–2000 characters after trimming | Yes |
| `policy_file` | PDF, at most 10 MB and 40 pages | No |

```powershell
curl.exe -X POST -F "question=What are my annual leave rights?" http://127.0.0.1:8000/rag/search
curl.exe -X POST -F "question=Article 109" -F "policy_file=@company-policy.pdf;type=application/pdf" http://127.0.0.1:8000/rag/search
```

The response is:

```json
{
  "context": "[L1] ...\n\n[P1] ...",
  "sources": [
    {
      "ref": "L1",
      "kind": "law",
      "source": "labor-law.pdf",
      "article": "المادة التاسعة بعد المائة",
      "article_number": 109,
      "repeated": false,
      "page_start": 36,
      "page_end": 36,
      "chunk": 0,
      "text": "Retrieved passage..."
    }
  ]
}
```

The sample illustrates the schema, not a guaranteed result ordering.
Law references use `L1`, `L2`, etc.; policy references use `P1`, `P2`, etc.
Up to five law chunks and three policy chunks are returned. Explicit
`Article 109`, `المادة 109`, and `المادة ١٠٩` queries filter by article number.
An unknown article returns empty law evidence.

English topic questions also receive matching Arabic search terms from a small
labor-law glossary. This improves E5-small retrieval against the Arabic corpus
(for example, `annual leave` adds `الإجازة السنوية`). The original question is
preserved, article numbers are never inferred from this glossary, and policy
search uses the original question. Unrecognized topics use ordinary E5 search.

Invalid questions or policies return HTTP 422. Unavailable models/storage
and missing, stale, or incomplete indexes return HTTP 503.

## LLM integration

```python
from apps.api.services.RAG.rag import retrieve

result = retrieve("كم عدد أيام الإجازة السنوية؟")
context = result["context"]
sources = result["sources"]
# The existing LLM service receives context and generates the answer.
# Return the original sources alongside that answer.
```

`retrieve(question, policy_pdf=pdf_bytes)` also accepts a policy directly.
The LLM owner should instruct their model to treat excerpts as evidence,
cite the returned reference labels, and acknowledge insufficient evidence.
The frontend and answer-generation service are outside this implementation.

## Verification

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -v
$env:RAG_LIVE_TESTS = "1"
$env:HF_HUB_OFFLINE = "1"
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```

The regular suite checks extraction, citation metadata, validation, index
integrity, explicit article filters, and policy isolation with test vectors.
The opt-in live suite checks real E5 embeddings, Arabic/English annual-leave
retrieval, and the multipart endpoint against the built index.

## Boundaries

- Extraction layout rules target the supplied 68-page PDF. A replacement PDF
  needs extraction review; arbitrary law-PDF layouts are not supported.
- Small amendment footnotes and chapter headings are excluded from indexed
  article bodies. This is an evidence index of the supplied text, not a check
  that the document is the latest law.
- Company-policy vectors are request-local in `InMemoryVectorStore` and never
  inserted into Chroma. FastAPI may spool an upload to temporary disk while
  receiving it; this is not a guarantee that uploaded bytes never touch disk.
- Encrypted, damaged, and text-free policy PDFs are rejected. OCR is not included.
- Similarity retrieval may return irrelevant or incomplete evidence. The smoke
  checks cover representative queries; they are not a full legal evaluation.

Implementation references: [E5 model card](https://huggingface.co/intfloat/multilingual-e5-small),
[LangChain Chroma](https://docs.langchain.com/oss/python/integrations/vectorstores/chroma),
[FastAPI forms/files](https://fastapi.tiangolo.com/tutorial/request-forms-and-files/),
[PyMuPDF text extraction](https://pymupdf.readthedocs.io/en/latest/recipes-text.html).
