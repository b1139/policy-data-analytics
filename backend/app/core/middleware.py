"""FastAPI application middlewares for request tracking and observability."""

import logging
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import request_id_ctx

logger = logging.getLogger(__name__)


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Middleware extracting or generating X-Request-ID for distributed tracing."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Process incoming request, maintaining correlation ID in context and response header.

        Args:
            request: Incoming HTTP request.
            call_next: Next request processor in chain.

        Returns:
            Response: Outgoing HTTP response with X-Request-ID header attached.
        """
        incoming_id = request.headers.get("X-Request-ID")
        request_id = (
            incoming_id.strip() if incoming_id and incoming_id.strip() else str(uuid.uuid4())
        )

        token = request_id_ctx.set(request_id)
        logger.debug(
            "Handling request %s %s [request_id=%s]",
            request.method,
            request.url.path,
            request_id,
        )

        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            logger.debug(
                "Completed %s %s -> %s [request_id=%s]",
                request.method,
                request.url.path,
                response.status_code,
                request_id,
            )
            return response
        except Exception as exc:
            logger.error(
                "Unhandled error during request %s %s [request_id=%s]: %s",
                request.method,
                request.url.path,
                request_id,
                exc,
                exc_info=True,
            )
            raise
        finally:
            request_id_ctx.reset(token)
