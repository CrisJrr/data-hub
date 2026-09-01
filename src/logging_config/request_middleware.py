"""
Request logging middleware — logs every API request with timing and context.
"""
import time
import uuid
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from src.logging_config import get_logger, set_correlation_id

logger = get_logger("datahub.request")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Logs method, path, status, duration, and correlation ID for every request."""

    # Paths to exclude from logging (too noisy)
    EXCLUDED_PATHS = {"/health", "/favicon.ico"}

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path

        # Skip noisy paths
        if path in self.EXCLUDED_PATHS:
            return await call_next(request)

        # Generate or use provided correlation ID
        cid = request.headers.get("x-correlation-id") or uuid.uuid4().hex[:12]
        set_correlation_id(cid)

        # Extract user info from JWT if present
        user_id = None
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            try:
                from jose import jwt as jose_jwt
                from src.config import settings
                payload = jose_jwt.decode(
                    auth_header[7:],
                    settings.jwt_secret_key,
                    algorithms=[settings.jwt_algorithm],
                )
                user_id = payload.get("sub")
            except Exception:
                pass

        client_ip = request.client.host if request.client else "unknown"

        # Log request start
        start = time.perf_counter()
        logger.info(
            "request_started",
            extra={
                "extra_data": {
                    "method": request.method,
                    "path": path,
                    "query": str(request.query_params) if request.query_params else None,
                    "client_ip": client_ip,
                    "user_id": user_id,
                    "user_agent": request.headers.get("user-agent", "-"),
                }
            },
        )

        # Process request
        status_code = 500
        error_msg = None
        try:
            response = await call_next(request)
            status_code = response.status_code
            # Inject correlation ID into response
            response.headers["x-correlation-id"] = cid
        except Exception as exc:
            error_msg = str(exc)
            raise
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)

            log_data = {
                "method": request.method,
                "path": path,
                "status": status_code,
                "duration_ms": duration_ms,
                "client_ip": client_ip,
                "user_id": user_id,
            }
            if error_msg:
                log_data["error"] = error_msg

            # Choose log level based on status
            if status_code >= 500:
                logger.error("request_completed", extra={"extra_data": log_data})
            elif status_code >= 400:
                logger.warning("request_completed", extra={"extra_data": log_data})
            else:
                logger.info("request_completed", extra={"extra_data": log_data})

        return response
