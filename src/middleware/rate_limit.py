"""
Rate limiting middleware using Redis sliding window.

Limits per category:
  - general: 100 req/min per user (JWT sub or IP)
  - llm: 10 req/min per user (expensive LLM queries)
  - auth: 5 req/min per IP (brute force protection)

Headers added to every response:
  X-RateLimit-Limit     — max requests in window
  X-RateLimit-Remaining — requests left
  X-RateLimit-Reset     — unix timestamp when window resets
"""
from __future__ import annotations

import time
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
RATE_LIMITS: dict[str, tuple[int, int]] = {
    # category: (max_requests, window_seconds)
    "general": (100, 60),
    "llm": (10, 60),
    "auth": (5, 60),
}

# Path → category mapping (checked in order, first match wins)
PATH_CATEGORIES: list[tuple[str, str]] = [
    ("/messages/ask", "llm"),
    ("/query/", "llm"),
    ("/auth/login", "auth"),
    ("/auth/register", "auth"),
    # Everything else falls through to "general"
]

DEFAULT_CATEGORY = "general"


def _resolve_category(path: str) -> str:
    for prefix, cat in PATH_CATEGORIES:
        if path.startswith(prefix):
            return cat
    return DEFAULT_CATEGORY


# ---------------------------------------------------------------------------
# Sliding window counter via Redis
# ---------------------------------------------------------------------------
async def _check_rate_limit(
    redis_client,
    key: str,
    max_requests: int,
    window: int,
) -> tuple[bool, int, int]:
    """
    Returns (allowed, remaining, reset_at).
    Uses Redis sorted sets for a precise sliding window.
    """
    now = time.time()
    window_start = now - window

    pipe = redis_client.pipeline()
    # Remove old entries outside the window
    pipe.zremrangebyscore(key, 0, window_start)
    # Count current entries
    pipe.zcard(key)
    # Add current request
    pipe.zadd(key, {str(now): now})
    # Set expiry on the key
    pipe.expire(key, window + 1)
    results = await pipe.execute()

    current_count = results[1]  # zcard result
    remaining = max(0, max_requests - current_count - 1)
    reset_at = int(now + window)

    allowed = current_count < max_requests
    if not allowed:
        # Remove the request we just added since it's not allowed
        await redis_client.zrem(key, str(now))

    return allowed, remaining, reset_at


# ---------------------------------------------------------------------------
# FastAPI Middleware
# ---------------------------------------------------------------------------
class RateLimitMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that applies per-user/per-IP rate limiting via Redis.
    
    Redis client is read from app.state.redis (set during lifespan).
    """

    def __init__(self, app, excluded_paths: list[str] | None = None):
        super().__init__(app)
        self.excluded_paths = excluded_paths or ["/health", "/docs", "/openapi.json"]

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path

        # Skip excluded paths
        if any(path.startswith(ep) for ep in self.excluded_paths):
            return await call_next(request)

        # Get Redis client from app state
        redis_client = getattr(request.app.state, "redis", None)
        if not redis_client:
            # Redis not available — allow request (graceful degradation)
            return await call_next(request)

        # Determine rate limit category
        category = _resolve_category(path)
        max_requests, window = RATE_LIMITS[category]

        # Extract user_id from JWT token if present
        user_id = None
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            try:
                from jose import jwt as jose_jwt
                from src.config import settings as _settings
                token = auth_header[7:]
                payload = jose_jwt.decode(
                    token, _settings.jwt_secret_key,
                    algorithms=[_settings.jwt_algorithm],
                )
                user_id = payload.get("sub")
            except Exception:
                pass

        client_ip = request.client.host if request.client else "unknown"
        identifier = f"user:{user_id}" if user_id else f"ip:{client_ip}"

        key = f"ratelimit:{category}:{identifier}"

        try:
            allowed, remaining, reset_at = await _check_rate_limit(
                redis_client, key, max_requests, window
            )
        except Exception:
            # If Redis errors, allow the request (graceful degradation)
            return await call_next(request)

        response = await call_next(request)

        # Add rate limit headers
        response.headers["X-RateLimit-Limit"] = str(max_requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_at)
        response.headers["X-RateLimit-Category"] = category

        if not allowed:
            retry_after = reset_at - int(time.time())
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit excedido",
                    "category": category,
                    "limit": max_requests,
                    "window_seconds": window,
                    "retry_after": max(retry_after, 1),
                },
                headers={
                    "Retry-After": str(max(retry_after, 1)),
                    "X-RateLimit-Limit": str(max_requests),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_at),
                },
            )

        return response
