from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Embeddings (OpenAI)
    openai_api_key: str = ""

    # LLM — uses OpenAI-compatible API (default: Gemini via Google AI Studio)
    llm_api_key: str = ""
    gemini_api_key: str = ""  # alias: set GEMINI_API_KEY in .env
    llm_api_base: str = "https://generativelanguage.googleapis.com/v1beta/openai/"

    @property
    def effective_llm_api_key(self) -> str:
        return self.llm_api_key or self.gemini_api_key
    llm_model: str = "gemini-2.5-flash"
    llm_mini_model: str = "gemini-2.5-flash"

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


settings = Settings()
