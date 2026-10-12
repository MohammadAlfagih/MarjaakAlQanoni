"""The frontend's existing policy upload/list/delete HTTP contract."""

import logging
import sqlite3

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from apps.api.services.RAG.rag import MAX_POLICY_BYTES
from apps.api.services.policies.service import PolicyNotFound, UnknownCompany, get_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/policies", tags=["Company policies"])


class PolicyInfo(BaseModel):
    id: str
    filename: str
    size: int
    uploaded_at: str


async def _run(method: str, *args):
    try:
        return await run_in_threadpool(lambda: getattr(get_service(), method)(*args))
    except (UnknownCompany, PolicyNotFound) as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except (OSError, RuntimeError, sqlite3.Error, ImportError) as exc:
        logger.exception("Policy storage or embedding model unavailable")
        raise HTTPException(503, "Policy storage or embedding model unavailable") from exc


@router.get("", response_model=list[PolicyInfo])
async def list_policies(company_id: str):
    return await _run("list", company_id)


@router.post("", response_model=PolicyInfo, status_code=201)
async def upload_policy(company_id: str = Form(...), file: UploadFile = File(...)):
    try:
        data = await file.read(MAX_POLICY_BYTES + 1)
    finally:
        await file.close()
    return await _run("upload", company_id, file.filename or "", data)


@router.delete("/{policy_id}", status_code=204)
async def delete_policy(policy_id: str):
    await _run("delete", policy_id)
    return Response(status_code=204)
