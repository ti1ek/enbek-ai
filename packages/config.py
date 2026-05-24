from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM — OpenAI is primary; Gemini is the fallback used only when the
    # OpenAI call fails (see packages/llm.py).
    openai_api_key: str = ""
    gemini_api_key: str = ""
    gemini_api_base: str = "https://generativelanguage.googleapis.com/v1beta/openai/"

    llm_model: str = "gpt-4.1-mini"
    llm_mini_model: str = "gpt-4.1-mini"
    fallback_llm_model: str = "gemini-2.5-flash"  # Gemini model used on OpenAI failure

    # Embeddings — OpenAI only. The query vector must match the vectors already
    # indexed in Qdrant (text-embedding-3-small, 1536-dim), so there is no
    # cross-provider fallback here: switching providers would require a full re-ingest.
    embedding_model: str = "text-embedding-3-small"
    embedding_vector_size: int = 1536

    # Reranker
    cohere_api_key: str = ""

    # Doc parsing
    llama_cloud_api_key: str = ""

    # Vector DB
    qdrant_url: str = ""
    qdrant_api_key: str = ""
    qdrant_collection: str = "kz_legal"

    # LangSmith
    langsmith_api_key: str = ""
    langsmith_tracing: bool = True
    langsmith_project: str = "enbek-ai"

    # App
    environment: str = "development"
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    @property
    def is_dev(self) -> bool:
        return self.environment == "development"

    @property
    def has_fallback_llm(self) -> bool:
        return bool(self.gemini_api_key)


settings = Settings()
