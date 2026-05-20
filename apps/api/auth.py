from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from packages.config import settings

security = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """Validates Supabase JWT and returns user payload."""
    token = credentials.credentials
    try:
        # Supabase uses HS256 with the JWT secret from project settings
        # For RS256 (default in newer Supabase), verify via supabase-py
        from apps.api.db import get_supabase_service
        db = get_supabase_service()
        user_response = db.auth.get_user(token)
        user = user_response.user
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        extra = db.table("users_extra").select("tier,daily_limit").eq("id", user.id).single().execute()
        extra_data = extra.data or {}
        return {
            "id": user.id,
            "email": user.email,
            "tier": extra_data.get("tier", "free"),
            "daily_limit": extra_data.get("daily_limit", 10),
        }
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
