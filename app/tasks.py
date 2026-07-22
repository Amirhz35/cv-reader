"""
Celery tasks for CV screening platform.
"""

import logging
import os
import tempfile
import time
from bson import ObjectId
from celery import shared_task
import requests
from django.core.files.storage import default_storage
from .models import CVEvaluationRequest, CVUpload, AIFailureLog
from .services.evaluation_service import CVEvaluationService
from .services.ai_client import NvidiaClient, DEFAULT_NVIDIA_MODEL  # AI client for CV evaluation

logger = logging.getLogger(__name__)


def _categorize_ai_error(message):
    """Map an error message to a short error_type for AIFailureLog."""
    msg = (message or '').lower()
    if 'timeout' in msg:
        return 'timeout'
    if 'circuit breaker' in msg:
        return 'circuit_breaker'
    if 'failed to extract text' in msg:
        return 'cv_extract_error'
    if 'json' in msg or 'missing required' in msg or 'not a valid number' in msg:
        return 'parse_error'
    if 'ai service error' in msg:
        return 'api_error'
    return 'unknown'


def _log_ai_failure(evaluation_id, error, retry_count=0, duration_ms=None, user_id=None, cv_id=None):
    """Persist an AI failure to MongoDB. Never raises - logging must not break the task."""
    try:
        AIFailureLog(
            evaluation_id=str(evaluation_id) if evaluation_id else None,
            user_id=str(user_id) if user_id else None,
            cv_id=str(cv_id) if cv_id else None,
            model=os.getenv('NVIDIA_MODEL', DEFAULT_NVIDIA_MODEL),
            error_type=_categorize_ai_error(str(error)),
            error_message=str(error)[:2000],
            retry_count=retry_count,
            duration_ms=duration_ms,
        ).save()
    except Exception as log_exc:
        logger.error(f"Failed to save AIFailureLog for {evaluation_id}: {log_exc}")


@shared_task(bind=True, max_retries=3)
def evaluate_cv_task(self, evaluation_id):
    """
    Asynchronous task to evaluate a CV against a job prompt.

    Args:
        evaluation_id (str): ObjectId of the CVEvaluationRequest document
    """
    task_started_at = time.monotonic()
    try:
        logger.info(f"Starting CV evaluation task for ID: {evaluation_id}")

        CVEvaluationRequest.objects(id=ObjectId(evaluation_id)).update_one(
            set__status=CVEvaluationRequest.STATUS_PROCESSING
        )

        evaluation = CVEvaluationRequest.objects.get(id=ObjectId(evaluation_id))

        cv_upload = CVUpload.objects.get(id=ObjectId(evaluation.cv_id))
        try:
            if cv_upload.storage_uri.startswith('http'):
                # Direct HTTP URL (legacy support)
                response = requests.get(cv_upload.storage_uri)
                response.raise_for_status()

                with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
                    temp_file.write(response.content)
                    temp_file_path = temp_file.name
            else:
                # S3/MinIO storage - download via storage API
                from django.core.files.storage import default_storage
                with default_storage.open(cv_upload.storage_uri, 'rb') as storage_file:
                    file_content = storage_file.read()

                with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
                    temp_file.write(file_content)
                    temp_file_path = temp_file.name
            # Initialize NVIDIA AI client (model comes from NVIDIA_MODEL env var or default)
            ai_client = NvidiaClient()
            evaluation_service = CVEvaluationService(ai_client)

            result = evaluation_service.evaluate_cv(
                cv_file_path=temp_file_path,
                prompt=evaluation.prompt
            )

        finally:
            if 'temp_file_path' in locals() and cv_upload.storage_uri.startswith('http'):
                try:
                    os.unlink(temp_file_path)
                except:
                    pass

        # Update evaluation with results
        if 'error' in result and result['error']:
            # If the result contains an error, mark as failed
            score = result['score'] if 'score' in result else None
            CVEvaluationRequest.objects(id=ObjectId(evaluation_id)).update_one(
                set__status=CVEvaluationRequest.STATUS_FAILED,
                set__ai_response=result,
                set__score=score,
                set__error_message=result['error']
            )
        else:
            # Successful evaluation - validate required fields
            if 'score' not in result:
                raise Exception("AI evaluation result missing 'score' field")
            
            CVEvaluationRequest.objects(id=ObjectId(evaluation_id)).update_one(
                set__status=CVEvaluationRequest.STATUS_COMPLETED,
                set__ai_response=result,
                set__score=result['score'],
                set__error_message=None  # Clear any previous error messages
            )

        logger.info(f"CV evaluation completed for ID: {evaluation_id}")
        return result

    except Exception as exc:
        logger.error(f"Error evaluating CV {evaluation_id}: {exc}")

        _log_ai_failure(
            evaluation_id=evaluation_id,
            error=exc,
            retry_count=self.request.retries,
            duration_ms=int((time.monotonic() - task_started_at) * 1000),
            user_id=getattr(locals().get('evaluation'), 'user_id', None),
            cv_id=getattr(locals().get('evaluation'), 'cv_id', None),
        )

        CVEvaluationRequest.objects(id=ObjectId(evaluation_id)).update_one(
            set__status=CVEvaluationRequest.STATUS_FAILED,
            set__error_message=str(exc)
        )

        if self.request.retries < self.max_retries:
            logger.info(f"Retrying CV evaluation task for ID: {evaluation_id}")
            raise self.retry(countdown=60 * (2 ** self.request.retries), exc=exc)

        return {'error': str(exc)}
