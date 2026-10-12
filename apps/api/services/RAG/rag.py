"""Retrieve attributable law/policy evidence; answer generation belongs to the LLM service."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from chromadb.errors import ChromaError
import pymupdf as fitz
import torch
import torch.nn.functional as F
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter
from transformers import AutoModel, AutoTokenizer

# ==================================================
# 1. CONFIGURATION
# ==================================================

HERE = Path(__file__).resolve().parent
LAW_PDF = HERE / "labor-law.pdf"
DB_DIR = HERE / "chroma_e5_db"
READY = DB_DIR / "READY.txt"

MODEL_NAME = "intfloat/multilingual-e5-small"
MODEL_CACHE = HERE / ".model_cache"
INDEX_VERSION = 2
CHUNK_SIZE = 450
CHUNK_OVERLAP = 70
MAX_POLICY_BYTES = 10_000_000
MAX_POLICY_PAGES = 40
COLLECTION_NAME = "saudi_labor_law_e5"

# The corpus is Arabic. Add matching Arabic search terms to English topic
# questions when E5-small's cross-language ranking loses the legal topic.
# These terms expand queries; they never select articles or supply legal facts.
BILINGUAL_TERMS = (
    (r"\b(?:annual|yearly)\s+(?:leave|vacation)\b", "الإجازة السنوية"),
    (r"\bsick\s+leave\b", "الإجازة المرضية"),
    (r"\bmaternity\s+leave\b", "إجازة الوضع"),
    (r"\bpaternity\s+leave\b", "إجازة ولادة مولود"),
    (r"\bend[ -]of[ -]service\b|\bseverance\b", "مكافأة نهاية الخدمة"),
    (r"\bovertime\b", "ساعات العمل الإضافية"),
    (r"\bworking\s+hours\b|\bwork\s+hours\b", "ساعات العمل"),
    (r"\bprobation\b", "فترة التجربة"),
    (r"\btermination\b|\bdismissal\b", "إنهاء عقد العمل"),
    (r"\bresignation\b|\bresign\b", "الاستقالة"),
    (r"\bnotice\s+period\b", "مدة الإشعار"),
    (r"\bwages?\b|\bsalary\b|\bsalaries\b", "الأجور الراتب"),
    (r"\bemployment\s+contract\b", "عقد العمل"),
    (r"\b(?:work|workplace)\s+injur(?:y|ies)\b", "إصابة العمل"),
    (r"\bweekly\s+rest\b", "الراحة الأسبوعية"),
)


def law_query(question: str) -> str:
    terms = [
        term for pattern, term in BILINGUAL_TERMS if re.search(pattern, question, re.I)
    ]
    return " ".join([question, *terms])


HEADINGS = re.compile(
    r"(?m)^[ \t]*(المادة[ \t]+[^\n:]{2,100})[ \t]*:[ \t]*(?:\d{1,3})?"
)

ARTICLE_QUERY = re.compile(
    r"(?:المادة\s*(?:رقم\s*)?|\barticle\s*(?:no\.?\s*)?)(\d{1,3})(?!\d)", re.I
)

ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")

SPLITTER = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    add_start_index=True,
)

router = APIRouter(prefix="/rag", tags=["RAG"])


# ==================================================
# 2. TRANSFORMERS EMBEDDING MODEL
# ==================================================


class E5Embeddings(Embeddings):
    def __init__(self):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        try:
            self.tokenizer = AutoTokenizer.from_pretrained(
                MODEL_NAME, cache_dir=str(MODEL_CACHE), local_files_only=True
            )
            model = AutoModel.from_pretrained(
                MODEL_NAME, cache_dir=str(MODEL_CACHE), local_files_only=True
            )
        except OSError:
            self.tokenizer = AutoTokenizer.from_pretrained(
                MODEL_NAME, cache_dir=str(MODEL_CACHE)
            )
            model = AutoModel.from_pretrained(MODEL_NAME, cache_dir=str(MODEL_CACHE))
        self.model = model.to(self.device).eval()

    def encode(self, texts: list[str], prefix: str) -> list[list[float]]:

        result = []

        for start in range(0, len(texts), 8):
            batch = [f"{prefix}: {text}" for text in texts[start : start + 8]]

            inputs = self.tokenizer(
                batch,
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors="pt",
            ).to(self.device)

            with torch.inference_mode():
                outputs = self.model(**inputs).last_hidden_state

                mask = inputs["attention_mask"].unsqueeze(-1)

                pooled = (outputs * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1)

                pooled = F.normalize(pooled, p=2, dim=1)

            result.extend(pooled.cpu().tolist())

        return result

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.encode(texts, "passage")

    def embed_query(self, text: str) -> list[float]:
        return self.encode([text], "query")[0]


@lru_cache(maxsize=1)
def embeddings() -> E5Embeddings:
    return E5Embeddings()


# ==================================================
# 3. EXTRACT LEGAL ARTICLES FROM PDF
# ==================================================


def clean(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("ـ", "")
    text = re.sub(r"[\u200e\u200f\u202a-\u202e\u2066-\u2069]", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def law_page_text(page: fitz.Page) -> str:
    """Keep the supplied PDF's body, excluding small amendment notes and large headings.

    The pinned PyMuPDF 1.28.2 restores logical Arabic order in this PDF. Do not reverse
    Arabic strings: doing so would corrupt correctly extracted text and numbers.
    These font/layout rules are specific to the 68-page law PDF.
    """
    lines = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            if line["bbox"][1] >= page.rect.height - 45:
                continue
            heading = any("المادة" in span["text"] for span in line["spans"])
            text = "".join(
                span["text"]
                for span in line["spans"]
                if 10.5 <= span["size"] <= 18
                or (heading and span["text"].strip() == ":")
            )
            text = clean(text)
            if text.isdecimal() and line["bbox"][1] > page.rect.height * 0.85:
                continue
            if text and text != "والله الموفق ,,,":
                lines.append(text)
    return "\n".join(lines)


def extract_articles() -> list[Document]:

    if not LAW_PDF.is_file():
        raise FileNotFoundError(f"Missing PDF: {LAW_PDF}")

    articles = []
    current = None
    number = 0

    with fitz.open(LAW_PDF) as pdf:

        for page_no, page in enumerate(pdf, start=1):
            if page_no <= 4 or page_no == len(pdf):
                continue

            text = law_page_text(page)
            headings = list(HEADINGS.finditer(text))

            # Continue an article from the previous page
            if current:
                leading = text[: headings[0].start()] if headings else text

                if leading.strip():
                    current["segments"].append((page_no, clean(leading)))
                    current["page_end"] = page_no

            for i, match in enumerate(headings):

                if current:
                    articles.append(current)

                title = clean(match.group(1))
                repeated = "مكرر" in title

                if not repeated:
                    number += 1

                end = headings[i + 1].start() if i + 1 < len(headings) else len(text)

                current = {
                    "title": title,
                    "number": number,
                    "repeated": repeated,
                    "page_start": page_no,
                    "page_end": page_no,
                    "segments": [(page_no, clean(text[match.end() : end]))],
                }

        if current:
            articles.append(current)

    # Validation specific to your supplied PDF
    if number != 245 or len(articles) != 249:
        raise ValueError(
            f"Unexpected article count: "
            f"{number} numbered / "
            f"{len(articles)} total"
        )

    documents = []

    for article in articles:
        content = article["title"]
        page_spans = [(0, len(content), article["page_start"])]
        for page_no, body in article["segments"]:
            if body:
                start = len(content) + 1
                content += "\n" + body
                page_spans.append((start, len(content), page_no))
        documents.append(
            Document(
                page_content=content,
                metadata={
                    "kind": "law",
                    "source": "labor-law.pdf",
                    "article": article["title"],
                    "article_number": article["number"],
                    "repeated": article["repeated"],
                    "page_start": article["page_start"],
                    "page_end": article["page_end"],
                    "_page_spans": page_spans,
                },
            )
        )

    return documents


# ==================================================
# 4. CHUNK THE ARTICLES
# ==================================================


def law_chunks() -> list[Document]:

    chunks = []

    for article in extract_articles():

        parts = SPLITTER.create_documents([article.page_content])

        for i, part in enumerate(parts):
            start = part.metadata["start_index"]
            end = start + len(part.page_content)
            pages = [
                page
                for left, right, page in article.metadata["_page_spans"]
                if left < end and right > start
            ]
            metadata = {
                key: value
                for key, value in article.metadata.items()
                if key != "_page_spans"
            }
            chunks.append(
                Document(
                    page_content=(
                        part.page_content
                        if i == 0
                        else f"{article.metadata['article']}\n{part.page_content}"
                    ),
                    metadata={
                        **metadata,
                        "page_start": min(pages),
                        "page_end": max(pages),
                        "chunk": i,
                    },
                )
            )

    return chunks


# ==================================================
# 5. CHROMADB
# ==================================================


def signature() -> str:
    pdf_hash = hashlib.sha256(LAW_PDF.read_bytes()).hexdigest()

    settings = {
        "pdf": pdf_hash,
        "model": MODEL_NAME,
        "version": INDEX_VERSION,
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
    }
    return hashlib.sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest()


@lru_cache(maxsize=2)
def store(create: bool = False) -> Chroma:
    return Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=embeddings(),
        persist_directory=str(DB_DIR),
        collection_metadata={"hnsw:space": "cosine"},
        create_collection_if_not_exists=create,
    )


def check_index() -> dict:
    message = (
        "Index missing, incomplete or outdated. Run python -m "
        "apps.api.services.RAG.rag --build"
    )
    try:
        manifest = json.loads(READY.read_text(encoding="utf-8"))
        if manifest["signature"] != signature() or manifest["chunks"] <= 0:
            raise ValueError("Stale manifest")
        if not (DB_DIR / "chroma.sqlite3").is_file():
            raise ValueError("Missing database")
        return manifest
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise RuntimeError(message) from exc


# ==================================================
# 6. BUILD THE VECTOR DATABASE
# ==================================================


def build_index() -> None:

    if READY.exists():
        manifest = check_index()
        if len(store().get(include=[])["ids"]) != manifest["chunks"]:
            raise RuntimeError(
                "Index is incomplete. Back up chroma_e5_db before rebuilding."
            )
        print("Index already built")
        return

    if DB_DIR.exists() and any(DB_DIR.iterdir()):
        raise RuntimeError(
            "Old or incomplete index detected. "
            "Back up chroma_e5_db before rebuilding."
        )

    chunks = law_chunks()
    database = store(create=True)

    for start in range(0, len(chunks), 16):

        batch = chunks[start : start + 16]

        ids = [
            (
                f"law-{doc.metadata['article_number']}-"
                f"{int(doc.metadata['repeated'])}-"
                f"{doc.metadata['chunk']}"
            )
            for doc in batch
        ]

        database.add_documents(batch, ids=ids)

        print(f"Indexed " f"{min(start + 16, len(chunks))}" f"/{len(chunks)}")

    if len(database.get(include=[])["ids"]) != len(chunks):
        raise RuntimeError("Index verification failed; READY was not written")
    ready_temp = READY.with_suffix(".tmp")
    ready_temp.write_text(
        json.dumps({"signature": signature(), "chunks": len(chunks)}), encoding="utf-8"
    )
    ready_temp.replace(READY)

    print("Law index is ready")


# ==================================================
# 7. RETRIEVE LAW + OPTIONAL COMPANY POLICY
# ==================================================


def citation_location(metadata: dict, lang: str = "en") -> str:
    kind = metadata.get("location_kind", "page")
    labels = {
        "page": ("صفحة PDF", "PDF page"),
        "line": ("الأسطر", "lines"),
        "paragraph": ("الفقرة", "paragraph"),
        "table": ("الجدول", "table"),
    }
    label = labels[kind][0 if lang == "ar" else 1]
    if kind == "page":
        start, end = metadata["page_start"], metadata["page_end"]
    else:
        start, end = metadata["location_start"], metadata["location_end"]
    return f"{label} {start}-{end}"


def retrieve(
    question: str, policy_pdf: bytes | None = None,
    *, policy_documents: list[Document] | None = None,
) -> dict:

    question = question.strip()
    if not 0 < len(question) <= 2000:
        raise ValueError("Question must be 1-2000 characters")

    if policy_pdf is not None and policy_documents is not None:
        raise ValueError("Supply either a policy PDF or already retrieved policy documents")
    # Validate uploads before loading the model or searching the permanent index.
    policy_chunks = extract_policy(policy_pdf) if policy_pdf is not None else []
    manifest = check_index()
    database = store()
    if len(database.get(include=[])["ids"]) != manifest["chunks"]:
        raise RuntimeError("Law index is incomplete. Back up chroma_e5_db and rebuild.")

    # Recognize questions such as "المادة 109"
    normalized_question = question.translate(ARABIC_DIGITS)

    match = ARTICLE_QUERY.search(normalized_question)

    filter_by = {"article_number": int(match.group(1))} if match else None

    # Retrieve from persistent law database
    law_docs = database.similarity_search(law_query(question), k=5, filter=filter_by)

    # /chat supplies results from its cached per-company store, with no re-embedding.
    policy_docs = list(policy_documents or [])

    # Optional company policy: request-local only
    if policy_chunks:
        temporary_store = InMemoryVectorStore(embeddings())

        temporary_store.add_documents(policy_chunks)

        policy_docs = temporary_store.similarity_search(question, k=3)

    # Prepare structured evidence for LLM
    evidence = []
    sources = []

    for prefix, documents in (("L", law_docs), ("P", policy_docs)):
        for number, doc in enumerate(documents, start=1):
            tag = f"{prefix}{number}"

            sources.append({"ref": tag, **doc.metadata, "text": doc.page_content})

            evidence.append(
                f"[{tag}] "
                f"{doc.metadata['article']} "
                f"({citation_location(doc.metadata)})\n"
                f"{doc.page_content}"
            )

    return {"context": "\n\n".join(evidence), "sources": sources}


def extract_policy(policy_pdf: bytes) -> list[Document]:
    """Parse a request-local policy; no policy text/vectors enter Chroma."""
    if len(policy_pdf) > MAX_POLICY_BYTES or not policy_pdf.startswith(b"%PDF-"):
        raise ValueError("Upload a PDF no larger than 10 MB")
    chunks = []
    try:
        with fitz.open(stream=policy_pdf, filetype="pdf") as pdf:
            if pdf.is_encrypted or len(pdf) > MAX_POLICY_PAGES:
                raise ValueError(
                    "Encrypted PDFs and policies over 40 pages are unsupported"
                )
            for page_no, page in enumerate(pdf, start=1):
                body = clean(page.get_text("text", sort=True))
                for i, part in enumerate(SPLITTER.split_text(body)):
                    chunks.append(
                        Document(
                            page_content=part,
                            metadata={
                                "kind": "policy",
                                "source": "Uploaded policy",
                                "article": "Company policy",
                                "article_number": 0,
                                "repeated": False,
                                "page_start": page_no,
                                "page_end": page_no,
                                "chunk": i,
                            },
                        )
                    )
    except (fitz.FileDataError, fitz.EmptyFileError) as exc:
        raise ValueError("The uploaded PDF is invalid or damaged") from exc
    if not chunks:
        raise ValueError(
            "No selectable text in policy PDF; OCR is required for scanned files"
        )
    return chunks


# ==================================================
# 8. FASTAPI ROUTER
# ==================================================


@router.post("/search")
async def search(
    question: str = Form(...), policy_file: UploadFile | None = File(default=None)
):

    if not 0 < len(question.strip()) <= 2000:
        raise HTTPException(
            status_code=422, detail="Question must be 1-2000 characters"
        )

    data = None

    if policy_file is not None:
        try:
            data = await policy_file.read(MAX_POLICY_BYTES + 1)
        finally:
            await policy_file.close()

    try:
        return await run_in_threadpool(retrieve, question, data)

    except (ValueError, fitz.FileDataError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    except (OSError, ChromaError) as exc:
        raise HTTPException(
            status_code=503,
            detail="RAG storage or embedding model unavailable. Check the index and model cache.",
        ) from exc


# ==================================================
# 9. COMMAND-LINE ENTRY POINT
# ==================================================

if __name__ == "__main__":
    import sys

    if "--inspect" in sys.argv:
        articles = extract_articles()

        print(f"Found {len(articles)} articles " f"(including repeated articles)")

        print("Article 109 sample:")
        print(
            next(
                article.page_content
                for article in articles
                if article.metadata["article_number"] == 109
                and not article.metadata["repeated"]
            )
        )

    elif "--build" in sys.argv:
        build_index()

    else:
        print("Use --inspect or --build")
