from fastapi import FastAPI

from apps.api.services.RAG.rag import router as rag_router

app = FastAPI()

app.include_router(rag_router)
