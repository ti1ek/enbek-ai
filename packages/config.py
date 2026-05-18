from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM
    openai_api_key: str = ""
    gemini_api_key: str = ""

    # Reranker
    cohere_api_key: str = ""

    # Doc parsing
    llama_cloud_api_key: str = ""

    # Vector DB
    qdrant_url: str = ""
    qdrant_api_key: str = ""
    qdrant_collection: str = "kz_legal"

    # Supabase
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_key: str = ""

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
