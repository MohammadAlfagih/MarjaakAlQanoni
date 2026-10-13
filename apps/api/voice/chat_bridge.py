"""Send a transcribed voice question through the exact same path as POST /chat."""
from __future__ import annotations

from fastapi import HTTPException
from pydantic import ValidationError

from apps.api.services.llm.chat import ChatRequest, _run, answer_question


async def answer(question: str, role: str, company_id: str | None, lang: str, history: list) -> dict:
    try:
        request = ChatRequest(
            question=question, role=role, company_id=company_id, lang=lang, history=history
        )
    except ValidationError as exc:
        raise HTTPException(422, exc.errors(include_url=False)) from exc
    result = await _run(request, answer_question)  # same errors as /chat (404/422/502/503)
    return result.model_dump()
