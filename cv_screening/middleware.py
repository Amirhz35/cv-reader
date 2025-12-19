"""
Middleware for request tracking and logging.
"""

import time
import uuid
import structlog
from django.conf import settings


class RequestLoggingMiddleware:
    """
    Middleware to add request tracking and structured logging.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = str(uuid.uuid4())
        with structlog.contextvars.bound_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.path,
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            remote_addr=self._get_client_ip(request),
        ):
            structlog.get_logger().info("request_started")

            request.request_id = request_id

            start_time = time.time()

            try:
                response = self.get_response(request)

                duration = time.time() - start_time
                with structlog.contextvars.bound_contextvars(
                    status_code=response.status_code,
                    duration=f"{duration:.4f}s",
                ):
                    structlog.get_logger().info("request_completed")

                return response

            except Exception as exc:
                duration = time.time() - start_time
                with structlog.contextvars.bound_contextvars(
                    status_code=500,
                    duration=f"{duration:.4f}s",
                    error=str(exc),
                    error_type=type(exc).__name__,
                ):
                    structlog.get_logger().error("request_failed")

                raise

    def _get_client_ip(self, request):
        """Get the client's IP address."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class UserContextMiddleware:
    """
    Middleware to add user context to logging for authenticated requests.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if hasattr(request, 'user') and request.user.is_authenticated:
            with structlog.contextvars.bound_contextvars(
                user_id=str(request.user.id),
                user_email=request.user.email,
            ):
                return self.get_response(request)
        else:
            return self.get_response(request)
