import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from packages.config import settings

# LangSmith tracing — must be set before importing langchain
os.environ["LANGCHAIN_TRACING_V2"] = str(settings.langsmith_tracing).lower()
os.environ["LANGCHAIN_API_KEY"] = settings.langsmith_api_key
os.environ["LANGCHAIN_PROJECT"] = settings.langsmith_project


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="Enbek AI — Трудовое Право РК",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # Next.js dev (apps/web)
        "https://*.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


from apps.api.routes import ask  # noqa: E402
app.include_router(ask.router, prefix="/api/v1")
