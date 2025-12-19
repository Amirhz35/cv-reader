"""
Prometheus metrics configuration for CV screening platform.
"""

from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry, generate_latest
import time

# Create a custom registry to avoid conflicts with Django's metrics
registry = CollectorRegistry()

# Request metrics
REQUEST_COUNT = Counter(
    'cv_screening_requests_total',
    'Total number of requests',
    ['method', 'endpoint', 'status'],
    registry=registry
)

REQUEST_LATENCY = Histogram(
    'cv_screening_request_duration_seconds',
    'Request duration in seconds',
    ['method', 'endpoint'],
    registry=registry
)

# CV evaluation metrics
CV_EVALUATION_COUNT = Counter(
    'cv_screening_evaluations_total',
    'Total number of CV evaluations',
    ['status'],
    registry=registry
)

CV_EVALUATION_DURATION = Histogram(
    'cv_screening_evaluation_duration_seconds',
    'CV evaluation duration in seconds',
    registry=registry
)

# File upload metrics
FILE_UPLOAD_COUNT = Counter(
    'cv_screening_file_uploads_total',
    'Total number of file uploads',
    ['file_type', 'status'],
    registry=registry
)

FILE_UPLOAD_SIZE = Histogram(
    'cv_screening_file_upload_size_bytes',
    'File upload size in bytes',
    ['file_type'],
    registry=registry
)

# Celery metrics
CELERY_TASK_COUNT = Counter(
    'cv_screening_celery_tasks_total',
    'Total number of Celery tasks',
    ['task_name', 'status'],
    registry=registry
)

CELERY_QUEUE_SIZE = Gauge(
    'cv_screening_celery_queue_size',
    'Current Celery queue size',
    registry=registry
)

# Database metrics
DB_CONNECTION_COUNT = Gauge(
    'cv_screening_db_connections_active',
    'Number of active database connections',
    ['database'],
    registry=registry
)

# AI service metrics
AI_REQUEST_COUNT = Counter(
    'cv_screening_ai_requests_total',
    'Total number of AI service requests',
    ['service', 'status'],
    registry=registry
)

AI_REQUEST_DURATION = Histogram(
    'cv_screening_ai_request_duration_seconds',
    'AI request duration in seconds',
    ['service'],
    registry=registry
)

# Circuit breaker metrics
CIRCUIT_BREAKER_STATE = Gauge(
    'cv_screening_circuit_breaker_state',
    'Circuit breaker state (0=closed, 1=open, 2=half_open)',
    ['service'],
    registry=registry
)

CIRCUIT_BREAKER_FAILURES = Counter(
    'cv_screening_circuit_breaker_failures_total',
    'Total circuit breaker failures',
    ['service'],
    registry=registry
)


def get_metrics() -> bytes:
    """Get Prometheus metrics in the correct format."""
    return generate_latest(registry)


class MetricsMiddleware:
    """
    Middleware to collect request metrics.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start_time = time.time()

        response = self.get_response(request)

        # Record request metrics
        duration = time.time() - start_time
        REQUEST_COUNT.labels(
            method=request.method,
            endpoint=request.path,
            status=response.status_code
        ).inc()

        REQUEST_LATENCY.labels(
            method=request.method,
            endpoint=request.path
        ).observe(duration)

        return response
