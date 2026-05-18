from functools import lru_cache
from supabase import create_client, Client
from packages.config import settings


@lru_cache(maxsize=1)
def get_supabase_service() -> Client:
    """Service-role client for backend operations (bypasses RLS)."""
    return create_client(settings.supabase_url, settings.supabase_service_key)


@lru_cache(maxsize=1)
def get_supabase_anon() -> Client:
    """Anon client for auth operations."""
    return create_client(settings.supabase_url, settings.supabase_anon_key)


async def log_query(
    user_id: str,
    query_text: str,
    response_text: str,
    sources: list[dict],
    pipeline: str,
    latency_ms: int,
    cost_usd: float,
) -> None:
    db = get_supabase_service()
    db.table("queries_log").insert({
        "user_id": user_id,
        "query_text": query_text,
        "response_text": response_text,
        "sources_json": sources,
        "pipeline": pipeline,
        "latency_ms": latency_ms,
        "cost_usd": cost_usd,
    }).execute()


def queries_today(user_id: str) -> int:
    db = get_supabase_service()
    result = db.rpc("queries_today", {"p_user_id": user_id}).execute()
    return result.data or 0
