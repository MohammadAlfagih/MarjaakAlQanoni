import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware

from apps.api.services.RAG.rag import router as rag_router
from apps.api.services.llm.chat import router as chat_router
from apps.api.services.llm.client import MODEL_NAME, get_client, is_loaded
from apps.api.services.policies.router import router as policy_router
from apps.api.services.policies.service import company_catalog


@asynccontextmanager
async def lifespan(app: FastAPI):
    if os.environ.get("LLM_PRELOAD") == "1":
        await run_in_threadpool(get_client)
    yield


app = FastAPI(title="Marjaak AlQanoni API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.environ.get(
            "FRONTEND_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
        ).split(",")
        if origin.strip()
    ],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "ngrok-skip-browser-warning"],
)

app.include_router(rag_router)
app.include_router(chat_router)
app.include_router(policy_router)


@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL_NAME, "llm_loaded": is_loaded(), "pid": os.getpid()}


@app.get("/companies")
def companies():
    # Demo company choices match the frontend. This is not authentication.
    return company_catalog()
