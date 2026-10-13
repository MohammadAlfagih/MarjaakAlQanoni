"""Adapt RAG + Qwen to the existing frontend's POST /chat JSON contract."""

from __future__ import annotations

import json
import logging
import sqlite3
from typing import Callable, Literal

from chromadb.errors import ChromaError
from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from apps.api.services.RAG import rag
from apps.api.services.llm.client import get_client
from apps.api.services.policies.service import UnknownCompany, get_service as get_policy_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Chat"])
Status = Literal["answered", "out_of_scope", "unknown", "clarify"]


class HistoryMessage(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)
    status: Status | None = None


class ChatRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    question: str = Field(min_length=1, max_length=2000)
    role: Literal["employee", "hr"]
    company_id: str | None = Field(default=None, min_length=1, max_length=100)
    lang: Literal["ar", "en"]
    history: list[HistoryMessage] = Field(default_factory=list, max_length=100)

    @field_validator("company_id", mode="before")
    @classmethod
    def normalize_company(cls, value):
        return (value.strip() or None) if isinstance(value, str) else value


class Article(BaseModel):
    ref: str
    source: Literal["law", "policy"]
    quote: str


class ChatResponse(BaseModel):
    answer: str
    articles: list[Article]
    next_steps: list[str]
    conflict: bool
    status: Status
    lang: Literal["ar", "en"]


class ModelAnswer(BaseModel):
    """Only references are model-written; quotes and source names come from RAG."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid", strict=True)
    answer: str = Field(min_length=1, max_length=8000)
    evidence_refs: list[str] = Field(max_length=8)
    next_steps: list[str] = Field(max_length=5)
    conflict: bool
    status: Status


SYSTEM_PROMPT = """
You are Marjaak AlQanoni, a Saudi Labor Law assistant.

Use only the retrieved Saudi Labor Law evidence and, when available, the selected company's policy evidence.
Do not invent article numbers, quotations, rights, deadlines, exceptions, or company rules.

First identify the request type:

1) CASE QUESTION:
The user asks about a specific employee situation.
- Answer the case using relevant law evidence.
- If company policy is available, compare only the relevant policy clause.
- If policy conflicts with the law, state the conflict and that Saudi Labor Law is the primary reference.
- If policy is unclear, say it is unclear.
- Give short practical next steps.

2) POLICY REVIEW:
The user says they created, drafted, or are reviewing a policy and asks if it complies with Saudi Labor Law.
- Review each relevant policy clause separately.
- Classify each clause in the answer as:
  Compliant, Conflicting, Unclear, or Not assessable.
- Do not judge the whole policy from one clause.
- If a clause is unclear, explain what needs clarification.
- If a clause conflicts with the law, state that Saudi Labor Law is the primary reference.

Evidence rules & Sourcing:
- Law evidence uses labels like L1, L2.
- Policy evidence uses labels like P1, P2.
- Use only evidence directly related to the question or policy clause.
- Do not copy literal quotes or mention article numbers/source details within the "answer" text. The application frontend will automatically insert and display the original texts using the labels you provide in the "evidence_refs" array.
- If law evidence is unrelated or insufficient, do not guess.
- If no company policy is supplied, do not claim to know company rules.
- Do not invent evidence labels.
- Use history only to understand follow-up questions. Answer only the current question;
  if it is about a different topic than earlier messages, ignore them and never repeat a previous answer.

Language:
- Answer in the requested language: ar = Arabic, en = English.
- Keep the answer clear, concise, and practical.

Status:
- "answered" = evidence supports the answer.
- "unknown" = evidence is insufficient or unrelated.
- A missing company policy is not a reason for "unknown": if law evidence supports the answer,
  the status is "answered" with L references.
- "clarify" = essential facts or policy wording need clarification.
- "out_of_scope" = unrelated to Saudi employment law.

Conflict:
- Set "conflict": true only when policy evidence clearly contradicts law evidence.
- When conflict is true, cite both the law and policy evidence labels.

Return ONLY a single valid JSON object, without markdown fencing, introduction, or extra keys. The keys must exactly match this format:

{
  "answer": "your answer text here without quotes or article numbers",
  "evidence_refs": ["L1", "P1"],
  "next_steps": ["step 1", "step 2"],
  "conflict": false,
  "status": "answered"
}

Example format when evidence is insufficient (do not use this as a default answer for all questions):
{"answer": "The available evidence is insufficient to answer this question.", "evidence_refs": [], "next_steps": [], "conflict": false, "status": "unknown"}
"""


def retrieval_question(request: ChatRequest) -> str:
    """Add earlier user context only when answering our clarify question.

    'Five years' after "how long have you worked?" needs the leave question to
    retrieve; an unrelated new question must not pull the previous topic's sources.
    """
    last = request.history[-1] if request.history else None
    if last is None or last.role != "assistant" or last.status != "clarify":
        return request.question
    prior = [m.content for m in request.history if m.role == "user"][-2:]
    if not prior:
        return request.question
    remaining = 2000 - len(request.question) - 1
    if remaining <= 0:
        return request.question
    return "\n".join(prior)[-remaining:] + "\n" + request.question


def parse_answer(raw: str, evidence: dict, lang: Literal["ar", "en"]) -> ChatResponse:
    """Reject invalid JSON and unknown references instead of displaying inventions."""
    # Tolerate one enclosing JSON code fence, not arbitrary prose around JSON.
    raw = raw.strip()
    if raw.startswith("```json\n") and raw.endswith("```"):
        raw = raw[len("```json\n") : -3].strip()
    try:
        answer = ModelAnswer.model_validate(json.loads(raw))
    except (ValueError, ValidationError) as exc:
        raise HTTPException(502, "The LLM returned an invalid structured answer") from exc
    sources = {source["ref"]: source for source in evidence["sources"]}
    refs = list(dict.fromkeys(answer.evidence_refs))
    if any(ref not in sources for ref in refs):
        raise HTTPException(502, "The LLM cited evidence that was not retrieved")
    status = answer.status
    if status == "unknown" and refs and not answer.conflict:
        # A small model marks law-supported answers "unknown" when the company has no
        # policy. An answer that cites retrieved evidence is answered, not unknown.
        status = "answered"
    if status == "answered" and not refs:
        raise HTTPException(502, "The LLM answered without supporting references")
    if status in {"unknown", "out_of_scope"}:
        refs = []
    kinds = {sources[ref]["kind"] for ref in refs}
    if answer.conflict and (status != "answered" or not {"law", "policy"}.issubset(kinds)):
        raise HTTPException(502, "A policy conflict requires both law and company-policy references")
    articles = []
    for ref in refs:
        source = sources[ref]
        articles.append(
            Article(
                ref=f"[{ref}] {source['article']} ({rag.citation_location(source, lang)})",
                source=source["kind"],
                quote=source["text"],
            )
        )
    return ChatResponse(
        answer=answer.answer,
        articles=articles,
        next_steps=answer.next_steps,
        conflict=answer.conflict,
        status=status,
        lang=lang,
    )


def retrieve_evidence(request: ChatRequest) -> dict:
    """Law is always searched; company selection only adds policy retrieval."""
    question = retrieval_question(request)
    policy_docs = (
        get_policy_service().search(request.company_id, question)
        if request.company_id is not None else []
    )
    evidence = rag.retrieve(question, policy_documents=policy_docs)
    return {"company_id": request.company_id, "query": question, **evidence}


def answer_question(request: ChatRequest) -> ChatResponse:
    evidence = retrieve_evidence(request)
    if not evidence["sources"]:
        return ChatResponse(
            answer=(
                "لم أجد أدلة مناسبة في نظام العمل أو لوائح الشركة للإجابة عن السؤال."
                if request.lang == "ar"
                else "I could not find supporting evidence in the law or company policies."
            ),
            articles=[], next_steps=[], conflict=False, status="unknown", lang=request.lang,
        )
    # Bounded recent conversation; prior assistant status survives clarify turns.
    history = [m.model_dump(exclude_none=True) for m in request.history[-8:]]
    for message in history:
        # Earlier answers are context only; a short excerpt stops the model copying them.
        limit = 400 if message["role"] == "assistant" else 2000
        message["content"] = message["content"][:limit]
    prompt = {
            "question": request.question,
            # Role controls frontend access/navigation, not factual generation.
            # Identical company/question/history must produce identical model input.
            "company_id": request.company_id,
            "language": request.lang,
            "history": history,
            # Law remains the baseline. Company evidence is an additional source.
            "labor_law_evidence": [
                source for source in evidence["sources"] if source["kind"] == "law"
            ],
            "company_policy_evidence": [
                source for source in evidence["sources"] if source["kind"] == "policy"
            ],
    }
    model = get_client()
    raw = model.ask(SYSTEM_PROMPT, json.dumps(prompt, ensure_ascii=False))
    try:
        result = parse_answer(raw, evidence, request.lang)
    except HTTPException as exc:
        # Small models occasionally produce invalid JSON or labels. One bounded
        # repair uses the original evidence; no citation is manufactured by code.
        repair = {**prompt, "previous_answer": raw[:8000], "revision": (
            "صحح تنسيق الرد السابق ومراجعه. أعد JSON صالحا بالمفاتيح المحددة فقط، "
            "واستخدم رموز الأدلة الموجودة فعلا. لا تضف أدلة أو أحكاما جديدة."
        )}
        logger.warning("Repairing invalid model answer: %s", exc.detail)
        return parse_answer(
            model.ask(SYSTEM_PROMPT, json.dumps(repair, ensure_ascii=False)), evidence, request.lang
        )

    supplied = {source["kind"] for source in evidence["sources"]}
    cited = {article.source for article in result.articles}
    if result.status in {"answered", "clarify"} and supplied == {"law", "policy"} and cited != supplied:
        repair = {**prompt, "previous_answer": raw[:8000], "revision": (
            "راجع الرد السابق: وصلت أدلة من نظام العمل وسياسة الشركة، لكنه لم يستشهد "
            "بالقسمين. افحص صلتهما بالسؤال. إن دعما الإجابة، وضح حكم النظام وسياسة "
            "الشركة معا وضع رموز L وP الداعمة في evidence_refs. إن لم يرتبط أحد "
            "القسمين بالسؤال فلا تضف مرجعا منه لمجرد إكمال العدد، ووضح حدود الأدلة. "
            "أعد الإجابة كاملة بصيغة JSON المطلوبة فقط."
        )}
        # Retain a structurally valid first response if the optional review is
        # malformed. This review improves coverage, not proof of legal accuracy.
        try:
            result = parse_answer(
                model.ask(SYSTEM_PROMPT, json.dumps(repair, ensure_ascii=False)), evidence, request.lang
            )
        except HTTPException:
            logger.warning("Evidence review was invalid; retaining the validated first answer")
    return result


async def _run(request: ChatRequest, operation: Callable):
    try:
        return await run_in_threadpool(operation, request)
    except HTTPException:
        raise
    except UnknownCompany as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except (OSError, RuntimeError, ChromaError, ImportError, sqlite3.Error) as exc:
        logger.exception("RAG/LLM unavailable")
        raise HTTPException(
            503, "RAG or Qwen unavailable. Check the index, dependencies, model cache and available memory."
        ) from exc


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    return await _run(request, answer_question)


@router.post("/chat/evidence")
async def chat_evidence(request: ChatRequest):
    """Inspect the exact company/law retrieval path used by /chat without Qwen."""
    return await _run(request, retrieve_evidence)
