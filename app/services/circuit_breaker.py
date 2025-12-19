import time
import threading
from enum import Enum
from typing import Callable, Any, Optional
import structlog

logger = structlog.get_logger()


class CircuitBreakerState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerOpenException(Exception):
    pass


class CircuitBreaker:

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        expected_exception: Exception = Exception,
        success_threshold: int = 3,
        timeout: float = 30.0,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        self.success_threshold = success_threshold
        self.timeout = timeout

        self._state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = None
        self._lock = threading.Lock()

    def call(self, func: Callable, *args, **kwargs) -> Any:
        with self._lock:
            if self._state == CircuitBreakerState.OPEN:
                if self._should_attempt_reset():
                    self._state = CircuitBreakerState.HALF_OPEN
                    logger.info("Circuit breaker transitioning to half-open")
                else:
                    raise CircuitBreakerOpenException("Circuit breaker is open")

        try:
            result = func(*args, **kwargs)

            with self._lock:
                self._on_success()

            return result

        except self.expected_exception as e:
            with self._lock:
                self._on_failure()
            raise e
        except Exception as e:
            with self._lock:
                self._on_failure()
            raise e

    def _should_attempt_reset(self) -> bool:
        if self._last_failure_time is None:
            return False
        return time.time() - self._last_failure_time >= self.recovery_timeout

    def _on_success(self):
        self._failure_count = 0

        if self._state == CircuitBreakerState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self.success_threshold:
                self._state = CircuitBreakerState.CLOSED
                self._success_count = 0
                logger.info("Circuit breaker closed - service recovered")

    def _on_failure(self):
        self._failure_count += 1
        self._last_failure_time = time.time()
        self._success_count = 0

        if self._state == CircuitBreakerState.HALF_OPEN:
            self._state = CircuitBreakerState.OPEN
            logger.warning("Circuit breaker opened due to failure in half-open state")
        elif self._failure_count >= self.failure_threshold:
            self._state = CircuitBreakerState.OPEN
            logger.warning(f"Circuit breaker opened after {self._failure_count} failures")

    @property
    def state(self) -> CircuitBreakerState:
        return self._state

    @property
    def failure_count(self) -> int:
        return self._failure_count


# Global circuit breaker instance for AI calls
ai_circuit_breaker = CircuitBreaker(
    failure_threshold=5,  # Open after 5 failures
    recovery_timeout=60,  # Wait 60 seconds before trying again
    success_threshold=3,   # Close after 3 successes in half-open
    timeout=30.0,          # 30 second timeout for AI calls
)
